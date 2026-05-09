"""``lockdown`` phase: tag + branch + README banner + lockfile freeze.

This is the only phase that intentionally writes to the repo.
Idempotence: if the tag or branch already exists, the phase reports
"skipped" without raising. The README banner is added once and
detected by a marker comment — re-running won't duplicate.

Determinism: tag name defaults to ``freeze-YYYY-MM-DD``; the date is
the only wallclock dependency. The phase requires a clean working
tree by default to guarantee the tagged state is meaningful.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import structlog

from sunset_it._version import __version__
from sunset_it.models.profile import Profile
from sunset_it.models.reports import LockdownReport
from sunset_it.profiles.loader import load_profile

# POLYLENS external (Kimi P2): single source of truth for banner markers.
from sunset_it.utils.banner import (
    BANNER_MARKER_CLOSE as _BANNER_MARKER_CLOSE,
)
from sunset_it.utils.banner import (
    BANNER_MARKER_OPEN as _BANNER_MARKER_OPEN,
)
from sunset_it.utils.banner import (
    README_CANDIDATES as _README_CANDIDATES,
)
from sunset_it.utils.git import (
    GitError,
    add_paths,
    commit_staged,
    create_annotated_tag,
    create_branch_from_head,
    current_sha,
    has_branch,
    has_tag,
    is_dirty,
    is_valid_ref_name,
    reset_paths,
)

logger = structlog.get_logger()


def _default_tag_name(timestamp: datetime) -> str:
    return f"freeze-{timestamp:%Y-%m-%d}"


def _readme_path(repo: Path) -> Path | None:
    """Locate the README, refusing to follow symlinks that escape the repo.

    POLYLENS external audit (Kimi+Gemini P0): lockdown was previously
    missing the symlink-guard that ``reactivate._readme_path`` already
    applies. A README symlinked to ``/etc/passwd`` or ``~/.ssh/config``
    would have its banner write hit the symlink target. Same fix as
    reactivate: resolve, verify the resolved target stays inside the
    repo, refuse otherwise.
    """
    repo_resolved = repo.resolve()
    for name in _README_CANDIDATES:
        candidate = repo / name
        if not candidate.is_file():
            continue
        try:
            target = candidate.resolve(strict=True)
        except OSError:
            continue
        try:
            target.relative_to(repo_resolved)
        except ValueError:
            continue
        return candidate
    return None


def _build_banner(tag: str, branch: str, profile_name: str, timestamp: datetime) -> str:
    return (
        f"{_BANNER_MARKER_OPEN}\n"
        f"> **🥶 Frozen as of {timestamp:%Y-%m-%d}**\n"
        f"> \n"
        f"> Last known-good tag: `{tag}` · "
        f"maintenance branch: `{branch}` · "
        f"profile: `{profile_name}`. "
        f"See [`docs/SUNSET_NOTICE.md`](docs/SUNSET_NOTICE.md) and "
        f"[`docs/RUNBOOK.md`](docs/RUNBOOK.md) for the reactivation policy.\n"
        f"{_BANNER_MARKER_CLOSE}\n\n"
    )


def _add_readme_banner(
    readme: Path,
    tag: str,
    branch: str,
    profile_name: str,
    timestamp: datetime,
) -> Literal["written", "already_present"]:
    content = readme.read_text(encoding="utf-8")
    if _BANNER_MARKER_OPEN in content:
        return "already_present"
    banner = _build_banner(tag, branch, profile_name, timestamp)
    # Insert AFTER the first H1 if there is one, otherwise at the very top.
    h1_match = re.match(r"^(# [^\n]*\n)", content)
    if h1_match is not None:
        new = content[: h1_match.end()] + "\n" + banner + content[h1_match.end():]
    else:
        new = banner + content
    # POLYLENS external (Gemini P1): atomic write — tmp + replace, so a
    # SIGINT/SIGKILL between truncate and write doesn't corrupt the
    # README. PID suffix avoids collisions when two invocations race
    # (further mitigated by the Gemini P2 fix).
    import os
    tmp = readme.with_suffix(readme.suffix + f".sunset-tmp.{os.getpid()}")
    tmp.write_text(new, encoding="utf-8")
    tmp.replace(readme)
    return "written"


def lockdown(
    repo: Path,
    tag_name: str | None = None,
    branch_name: str = "maintenance",
    profile_name: str = "solo-frozen",
    profile: Profile | None = None,
    update_readme_banner: bool = True,
    allow_dirty: bool = False,
) -> LockdownReport:
    """Apply the freeze: annotated tag + maintenance branch + README banner.

    Args:
        repo: project root.
        tag_name: defaults to ``freeze-YYYY-MM-DD``.
        branch_name: maintenance branch (created at HEAD).
        profile_name: profile to load.
        profile: pre-loaded Profile (test injection).
        update_readme_banner: insert the banner if absent.
        allow_dirty: skip the clean-working-tree precondition.

    Returns:
        ``LockdownReport`` describing every action taken/skipped.
    """
    repo = repo.resolve()
    if profile is None:
        profile = load_profile(profile_name)

    timestamp = datetime.now(UTC)
    actions: list[str] = []
    skipped: list[str] = []

    # Spec attack v0.1.2 (Codex P1): validate tag_name + branch_name as
    # git refs BEFORE any mutation. The previous version mutated the
    # README, then attempted to create the tag, then noticed the tag was
    # invalid — leaving a partial state (banner committed but no tag).
    # Now we abort atomically before touching anything.
    final_tag_candidate = tag_name or _default_tag_name(timestamp)
    invalid_refs: list[str] = []
    if not is_valid_ref_name(final_tag_candidate):
        invalid_refs.append(f"invalid_tag_name: {final_tag_candidate!r}")
    if not is_valid_ref_name(branch_name):
        invalid_refs.append(f"invalid_branch_name: {branch_name!r}")
    if invalid_refs:
        skipped.extend(invalid_refs)
        return LockdownReport(
            timestamp=timestamp,
            sunset_it_version=__version__,
            repo_path=repo,
            profile_name=profile.name,
            actions_taken=actions,
            actions_skipped=skipped,
        )

    if not allow_dirty:
        try:
            if is_dirty(repo):
                skipped.append(
                    "working_tree_dirty: refusing to lockdown until "
                    "git status is clean (use --allow-dirty to override)"
                )
                return LockdownReport(
                    timestamp=timestamp,
                    sunset_it_version=__version__,
                    repo_path=repo,
                    profile_name=profile.name,
                    actions_taken=actions,
                    actions_skipped=skipped,
                )
        except GitError as e:
            skipped.append(f"git_status_failed: {e}")
            return LockdownReport(
                timestamp=timestamp,
                sunset_it_version=__version__,
                repo_path=repo,
                profile_name=profile.name,
                actions_taken=actions,
                actions_skipped=skipped,
            )

    final_tag = final_tag_candidate

    # Spec attack v0.1.1 (Gemini P1): the previous order was
    # tag → branch → README banner. The banner write left the working
    # tree dirty AFTER the tag had already been created, so the tag
    # pointed at a state that did NOT include the banner. Re-running
    # then required a manual ``git commit`` to make the second pass
    # idempotent — the test suite was patching that gap, hiding the
    # bug.
    #
    # New order: write the banner → stage + commit it → tag the
    # commit-with-banner → branch off that commit. The freeze tag now
    # truly points at the project state advertised by the banner.
    readme_banner_added = False
    banner_committed = False
    if update_readme_banner:
        readme = _readme_path(repo)
        if readme is None:
            skipped.append("readme_not_found")
        else:
            # POLYLENS v0.2.3 (Kimi P1): capture the pre-banner README
            # bytes so we can restore them if the commit fails. Without
            # this, a failed ``commit_staged`` leaves the working tree
            # dirty + a staged change with no commit, forcing the user
            # to clean up by hand.
            import contextlib
            original_readme: str | None = None
            with contextlib.suppress(OSError):
                original_readme = readme.read_text(encoding="utf-8")

            try:
                outcome = _add_readme_banner(
                    readme,
                    final_tag,
                    branch_name,
                    profile.name,
                    timestamp,
                )
                if outcome == "written":
                    readme_banner_added = True
                    actions.append(f"readme_banner_added: {readme.name}")
                    try:
                        add_paths(repo, readme.name)
                        commit_staged(
                            repo,
                            f"chore(sunset-it): add freeze banner for {final_tag}",
                        )
                        banner_committed = True
                        actions.append("readme_banner_committed")
                    except GitError as e:
                        skipped.append(f"readme_banner_commit_failed: {e}")
                        # Roll back to a clean state. Best-effort: if the
                        # restore itself fails we still record the failure
                        # but don't raise, because the lockdown report
                        # remains the source of truth for the operator.
                        rolled_back = False
                        try:
                            reset_paths(repo, readme.name)
                            rolled_back = True
                        except GitError as reset_e:
                            skipped.append(
                                f"readme_banner_unstage_failed: {reset_e}"
                            )
                        if original_readme is not None:
                            try:
                                readme.write_text(
                                    original_readme, encoding="utf-8"
                                )
                                rolled_back = True
                            except OSError as write_e:
                                skipped.append(
                                    f"readme_banner_restore_failed: {write_e}"
                                )
                        if rolled_back:
                            actions.append("readme_banner_rolled_back")
                            readme_banner_added = False
                else:
                    skipped.append(f"readme_banner_already_present: {readme.name}")
            except OSError as e:
                skipped.append(f"readme_banner_failed: {e}")

    tag_created: str | None = None
    try:
        if has_tag(repo, final_tag):
            skipped.append(f"tag_already_exists: {final_tag}")
        else:
            sha = current_sha(repo)
            create_annotated_tag(
                repo,
                final_tag,
                f"sunset-it freeze: {final_tag} at {sha} (profile {profile.name})",
            )
            tag_created = final_tag
            actions.append(f"tag_created: {final_tag}")
    except GitError as e:
        skipped.append(f"tag_failed: {e}")

    branch_created: str | None = None
    try:
        if has_branch(repo, branch_name):
            skipped.append(f"branch_already_exists: {branch_name}")
        else:
            create_branch_from_head(repo, branch_name)
            branch_created = branch_name
            actions.append(f"branch_created: {branch_name}")
    except GitError as e:
        skipped.append(f"branch_failed: {e}")

    # Suppress the unused-but-recorded marker; banner_committed is part
    # of the report data flow even when False. Lint catches this if we
    # don't reference it.
    _ = banner_committed

    report = LockdownReport(
        timestamp=timestamp,
        sunset_it_version=__version__,
        repo_path=repo,
        profile_name=profile.name,
        tag_created=tag_created,
        branch_created=branch_created,
        readme_banner_added=readme_banner_added,
        actions_taken=actions,
        actions_skipped=skipped,
    )
    logger.info(
        "lockdown_done",
        # POLYLENS v0.2.3: basename, not absolute path (Gemini P2 extended).
        repo=repo.name,
        tag=tag_created,
        branch=branch_created,
        banner=readme_banner_added,
    )
    return report
