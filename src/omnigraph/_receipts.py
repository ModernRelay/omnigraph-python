"""Receipt validation: a write is acknowledged only by a receipt that names it."""

from __future__ import annotations

from ._models import BranchMergeOutput, ChangeOutput, CommitOutput


def _merge_receipt(
    outcome: str, commit: CommitOutput | None, target: str, actor: str | None
) -> bool:
    if outcome == "already_up_to_date":
        return commit is None
    return (
        outcome in ("fast_forward", "merged")
        and commit is not None
        and bool(commit.get("graph_commit_id"))
        and isinstance(commit.get("graph_manifest_version"), int)
        and commit["graph_manifest_version"] > 0
        and (commit.get("graph_branch") or "main") == target
        and bool(commit.get("parent_commit_id"))
        and bool(commit.get("merged_parent_commit_id"))
        and commit.get("actor_id") == actor
    )


def valid_merge(
    output: BranchMergeOutput,
    *,
    source: str,
    target: str,
    as_commit: bool,
    delete_branch: bool,
    dry_run: bool,
) -> bool:
    if not isinstance(output, dict):
        return False
    if output.get("source") != source or output.get("target") != target:
        return False
    commit = output.get("commit")
    if dry_run:
        if not (
            output.get("dry_run") is True
            and commit is None
            and output.get("outcome")
            in ("already_up_to_date", "fast_forward", "merged")
        ):
            return False
    else:
        if output.get("dry_run") is True or not _merge_receipt(
            output["outcome"], commit, output["target"], output.get("actor_id")
        ):
            return False
        if commit is not None:
            if as_commit:
                if (
                    commit.get("kind") != "unpublished"
                    or commit.get("published") is not False
                ):
                    return False
            elif commit.get("kind") != "published" or commit.get("published") is False:
                return False
    deleted = output.get("branch_deleted")
    details = output.get("branch_delete_error_details")
    if not delete_branch:
        return deleted is None and details is None
    return (deleted is True and details is None) or (
        deleted is False and details is not None and bool(details.get("error"))
    )


def valid_mutation_receipt(output: ChangeOutput) -> bool:
    if not isinstance(output, dict):
        return False
    outcome = output.get("outcome")
    if not outcome or outcome.get("kind") != "merged":
        return True
    return _merge_receipt(
        outcome["merge"],  # type: ignore[typeddict-item]
        output.get("commit"),
        outcome["target"],  # type: ignore[typeddict-item]
        output.get("actor_id"),
    )
