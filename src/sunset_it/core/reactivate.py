"""``reactivate`` phase: controlled exit from freeze.

Inverse of ``lockdown``:

1. Verify the maintenance branch + a freeze tag exist.
2. Remove the README freeze banner (between the marker comments).
3. Commit the banner removal.
4. Create an annotated tag ``unfrozen-YYYY-MM-DD`` pointing at the
   commit-without-banner.

The phase **does not** delete the freeze tag — it stays as the
last known-good frozen state, useful for diff during reactivation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from sunset_it._version import __version__
from sunset_it.models.profile import Profile
from sunset_it.models.reports import ReactivateReport
from sunset_it.profiles.loader import load_profile
from sunset_it.utils.git import (
    GitError,
    add_paths,
    commit_staged,
    create_annotated_tag,
    has_branch,
    has_tag,
    is_dirty,
    is_valid_ref_name,
)

logger = structlog.get_logger()

_BANNER_MARKER_OPEN = "<!-- sunset-it:freeze-banner -->"
_BANNER_MARKER_CLOSE = "<!-- /sunset-it:freeze-banner -->"
_README_CANDIDATES = ("README.md", "Readme.md", "readme.md")


def _readme_path(repo: Path) -> Path | None:
    """Locate the README file, refusing to follow symlinks out of the repo.

    POLYLENS allégé v0.2.1 (Kimi P0): a malicious or accidental symlink
    pointing to a file outside the repo (e.g. ``/etc/passwd``) would be
    overwritten by ``_strip_freeze_banner``'s ``write_text``. Resolve and
    verify containment before returning.
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
            # Symlink escapes the repo — refuse.
            continue
        return candidate
    return None


def _strip_freeze_banner(readme: Path) -> bool:
    """Remove the freeze-banner block. True if anything was removed."""
    content = readme.read_text(encoding="utf-8")
    open_idx = content.find(_BANNER_MARKER_OPEN)
    if open_idx == -1:
        return False
    # POLYLENS v0.2.2 (Gemini P2): only search the close marker AFTER the
    # open marker. A stray close marker earlier in the file would
    # previously short-circuit and leave the real banner intact.
    close_idx = content.find(_BANNER_MARKER_CLOSE, open_idx)
    if close_idx == -1:
        return False
    # Remove the block including any trailing blank line so the README
    # doesn't end up with an awkward double-blank gap.
    end = close_idx + len(_BANNER_MARKER_CLOSE)
    # Eat trailing newlines after the close marker so we don't leave
    # an empty section.
    while end < len(content) and content[end] == "\n":
        end += 1
    new = content[:open_idx] + content[end:]
    readme.write_text(new, encoding="utf-8")
    return True


def reactivate(
    repo: Path,
    reason: str,
    branch_from: str = "maintenance",
    unfreeze_tag_name: str | None = None,
    profile_name: str = "solo-frozen",
    profile: Profile | None = None,
    profile_overrides_dir: Path | None = None,
    allow_dirty: bool = False,
    require_maintenance_branch: bool = True,
) -> ReactivateReport:
    """Exit a freeze with a documented reason and an unfreeze tag.

    POLYLENS v0.2.1 (Kimi+Qwen P2): ``require_maintenance_branch`` is
    True by default — reactivating a repo that was never frozen via
    sunset-it lockdown is almost always operator error. Set False
    only if you intentionally want the unfreeze tag without a branch
    (e.g. recovering from a manual freeze).
    """
    repo = repo.resolve()
    if profile is None:
        profile = load_profile(profile_name, profile_overrides_dir)
    timestamp = datetime.now(UTC)
    final_unfreeze = unfreeze_tag_name or f"unfrozen-{timestamp:%Y-%m-%d}"
    actions: list[str] = []
    skipped: list[str] = []

    # Atomic ref-name validation (same pattern as lockdown).
    if not is_valid_ref_name(final_unfreeze):
        skipped.append(f"invalid_unfreeze_tag_name: {final_unfreeze!r}")
        return ReactivateReport(
            timestamp=timestamp,
            sunset_it_version=__version__,
            repo_path=repo,
            profile_name=profile.name,
            reason=reason,
            unfreeze_tag=None,
            branch_used=branch_from,
            banner_removed=False,
            actions_taken=actions,
            actions_skipped=skipped,
        )

    if not allow_dirty:
        try:
            if is_dirty(repo):
                skipped.append(
                    "working_tree_dirty: refusing to reactivate until "
                    "git status is clean (use --allow-dirty to override)"
                )
                return ReactivateReport(
                    timestamp=timestamp,
                    sunset_it_version=__version__,
                    repo_path=repo,
                    profile_name=profile.name,
                    reason=reason,
                    unfreeze_tag=None,
                    branch_used=branch_from,
                    banner_removed=False,
                    actions_taken=actions,
                    actions_skipped=skipped,
                )
        except GitError as e:
            skipped.append(f"git_status_failed: {e}")
            return ReactivateReport(
                timestamp=timestamp,
                sunset_it_version=__version__,
                repo_path=repo,
                profile_name=profile.name,
                reason=reason,
                unfreeze_tag=None,
                branch_used=branch_from,
                banner_removed=False,
                actions_taken=actions,
                actions_skipped=skipped,
            )

    # Maintenance branch guard. By default this is a hard prerequisite —
    # reactivating without a maintenance branch usually means the repo
    # was never frozen via sunset-it and the operator is confused.
    try:
        branch_exists = has_branch(repo, branch_from)
    except GitError as e:
        skipped.append(f"branch_lookup_failed: {e}")
        branch_exists = None  # unknown — fail closed below

    if branch_exists:
        actions.append(f"maintenance_branch_present: {branch_from}")
    elif require_maintenance_branch:
        skipped.append(
            f"maintenance_branch_missing: {branch_from} "
            "(set require_maintenance_branch=False to override)"
        )
        return ReactivateReport(
            timestamp=timestamp,
            sunset_it_version=__version__,
            repo_path=repo,
            profile_name=profile.name,
            reason=reason,
            unfreeze_tag=None,
            branch_used=branch_from,
            banner_removed=False,
            actions_taken=actions,
            actions_skipped=skipped,
        )
    else:
        skipped.append(f"maintenance_branch_missing: {branch_from} (allowed)")

    banner_removed = False
    readme = _readme_path(repo)
    if readme is None:
        skipped.append("readme_not_found")
    else:
        try:
            removed = _strip_freeze_banner(readme)
            if removed:
                banner_removed = True
                actions.append(f"banner_removed: {readme.name}")
                try:
                    add_paths(repo, readme.name)
                    commit_staged(
                        repo,
                        f"chore(sunset-it): reactivate — {reason[:60]}",
                    )
                    actions.append("banner_removal_committed")
                except GitError as e:
                    skipped.append(f"banner_removal_commit_failed: {e}")
            else:
                skipped.append(f"banner_absent: {readme.name}")
        except OSError as e:
            skipped.append(f"banner_strip_failed: {e}")

    # Create the unfreeze tag — but only if banner removal succeeded
    # OR there was no banner to begin with (project never frozen
    # via sunset-it). We still tag in the second case so consumers
    # have a marker.
    unfreeze_tag_created: str | None = None
    try:
        if has_tag(repo, final_unfreeze):
            skipped.append(f"unfreeze_tag_already_exists: {final_unfreeze}")
        else:
            create_annotated_tag(
                repo,
                final_unfreeze,
                f"sunset-it reactivate: {reason}",
            )
            unfreeze_tag_created = final_unfreeze
            actions.append(f"unfreeze_tag_created: {final_unfreeze}")
    except GitError as e:
        skipped.append(f"unfreeze_tag_failed: {e}")

    report = ReactivateReport(
        timestamp=timestamp,
        sunset_it_version=__version__,
        repo_path=repo,
        profile_name=profile.name,
        reason=reason,
        unfreeze_tag=unfreeze_tag_created,
        branch_used=branch_from,
        banner_removed=banner_removed,
        actions_taken=sorted(actions),
        actions_skipped=sorted(skipped),
    )
    logger.info(
        "reactivate_done",
        # POLYLENS v0.2.2 (Gemini P2): basename, not absolute path, to
        # avoid leaking the operator's home dir layout in shared logs.
        repo=repo.name,
        profile=profile.name,
        unfreeze_tag=unfreeze_tag_created,
        banner_removed=banner_removed,
        reason=reason[:80],
    )
    return report
