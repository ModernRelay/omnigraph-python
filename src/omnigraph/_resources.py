"""Resource groups hung off `Omnigraph`: branches, commits, schema, graphs, cluster."""

from __future__ import annotations

import builtins
from typing import Any, cast
from urllib.parse import quote

from ._models import (
    BranchCreateOutput,
    BranchDeleteOutput,
    BranchMergeOutput,
    CommitChangesOutput,
    CommitListing,
    CommitListOutput,
    CommitOutput,
    DeploymentOutput,
    DeploymentStatusOutput,
    DiffOutput,
    GraphDiscoveryEntry,
    GraphInfo,
    MergeBaseOutput,
    SchemaOutput,
)
from ._receipts import valid_merge
from ._transport import Transport


def _seg(value: str) -> str:
    return quote(value, safe="")


def _str(value: int | None) -> str | None:
    return None if value is None else str(value)


class Branches:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def list(self, *, if_actor: str | None = None) -> builtins.list[str]:
        r = await self._t.request("GET", "/branches", if_actor=if_actor)
        return builtins.list(r["branches"])

    async def create(
        self,
        name: str,
        *,
        from_: str | None = None,
        from_commit: str | None = None,
        if_actor: str | None = None,
    ) -> BranchCreateOutput:
        """Fork `name` off `from_` (default `main`) or off a published commit.

        Raises `ConflictError` if the branch exists. After an uncertain
        outcome, inspect the branch before deciding whether to retry.
        """
        body: dict[str, Any] = {"name": name}
        if from_ is not None:
            body["from"] = from_
        if from_commit is not None:
            body["from_commit"] = from_commit
        return cast(
            BranchCreateOutput,
            await self._t.request("POST", "/branches", body=body, if_actor=if_actor),
        )

    async def merge(
        self,
        source: str,
        *,
        target: str = "main",
        as_commit: bool = False,
        delete_branch: bool = False,
        dry_run: bool = False,
        if_actor: str | None = None,
    ) -> BranchMergeOutput:
        """Merge `source` into `target`.

        Returns this merge's exact commit, or `commit: None` when already up to
        date. With `delete_branch`, a deletion can fail after a merge that
        landed; inspect `branch_deleted` and `branch_delete_error_details`.
        Never retry an uncertain merge blindly.
        """
        body: dict[str, Any] = {"source": source, "target": target}
        if as_commit:
            body["as_commit"] = True
        if delete_branch:
            body["delete_branch"] = True
        if dry_run:
            body["dry_run"] = True
        result = await self._t.request(
            "POST", "/branches/merge", body=body, if_actor=if_actor
        )
        if not valid_merge(
            result,
            source=source,
            target=target,
            as_commit=as_commit,
            delete_branch=delete_branch,
            dry_run=dry_run,
        ):
            raise self._t.invalid_response(
                "POST", "/branches/merge", "invalid merge receipt"
            )
        return cast(BranchMergeOutput, result)

    async def delete(
        self, name: str, *, if_actor: str | None = None
    ) -> BranchDeleteOutput:
        """Delete a branch. A missing branch raises `NotFoundError`."""
        return cast(
            BranchDeleteOutput,
            await self._t.request(
                "DELETE", f"/branches/{_seg(name)}", if_actor=if_actor
            ),
        )

    async def merge_base(
        self, source: str, *, target: str | None = None, if_actor: str | None = None
    ) -> MergeBaseOutput:
        return cast(
            MergeBaseOutput,
            await self._t.request(
                "GET",
                "/branches/merge-base",
                query={"source": source, "target": target},
                if_actor=if_actor,
            ),
        )

    async def diff(
        self,
        source: str,
        *,
        target: str | None = None,
        page_token: str | None = None,
        limit: int | None = None,
        if_actor: str | None = None,
    ) -> DiffOutput:
        """The net changes `source` made since its merge base with `target`."""
        return cast(
            DiffOutput,
            await self._t.request(
                "GET",
                "/branches/diff",
                query={
                    "source": source,
                    "target": target,
                    "page_token": page_token,
                    "limit": _str(limit),
                },
                if_actor=if_actor,
            ),
        )


class Commits:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def list(
        self,
        *,
        branch: str | None = None,
        listing: CommitListing | None = None,
        limit: int | None = None,
        page_token: str | None = None,
        if_actor: str | None = None,
    ) -> CommitListOutput:
        """Commits, most recent first. Unpublished and unattached listings are not paged."""
        return cast(
            CommitListOutput,
            await self._t.request(
                "GET",
                "/commits",
                query={
                    "branch": branch,
                    "listing": listing,
                    "limit": _str(limit),
                    "page_token": page_token,
                },
                if_actor=if_actor,
            ),
        )

    async def retrieve(
        self, commit_id: str, *, if_actor: str | None = None
    ) -> CommitOutput:
        return cast(
            CommitOutput,
            await self._t.request(
                "GET", f"/commits/{_seg(commit_id)}", if_actor=if_actor
            ),
        )

    async def publish(
        self, commit_id: str, *, if_actor: str | None = None
    ) -> CommitOutput:
        """Publish an unpublished commit onto its recorded target branch.

        Never replay automatically after a lost response; a repeat publish of
        a published commit answers the same receipt.
        """
        return cast(
            CommitOutput,
            await self._t.request(
                "POST", f"/commits/{_seg(commit_id)}/publish", if_actor=if_actor
            ),
        )

    async def drop(self, commit_id: str, *, if_actor: str | None = None) -> None:
        """Drop an unpublished commit or an unattached chain."""
        path = f"/commits/{_seg(commit_id)}"
        response = await self._t.send("DELETE", path, if_actor=if_actor)
        if response.status_code != 204:
            raise self._t.invalid_response(
                "DELETE", path, "commit drop did not return 204", response.status_code
            )

    async def changes(
        self,
        commit_id: str,
        *,
        page_token: str | None = None,
        limit: int | None = None,
        if_actor: str | None = None,
    ) -> CommitChangesOutput:
        """One page of entity changes relative to the commit's first parent."""
        return cast(
            CommitChangesOutput,
            await self._t.request(
                "GET",
                f"/commits/{_seg(commit_id)}/changes",
                query={"page_token": page_token, "limit": _str(limit)},
                if_actor=if_actor,
            ),
        )


class Schema:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def get(self, *, if_actor: str | None = None) -> SchemaOutput:
        """The graph's current schema source (the default branch's)."""
        return cast(
            SchemaOutput, await self._t.request("GET", "/schema", if_actor=if_actor)
        )


class Graphs:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def list(self, *, if_actor: str | None = None) -> builtins.list[GraphInfo]:
        """Every registered graph. Closed by default: needs a `graph_list` grant."""
        r = await self._t.request("GET", "/graphs", if_actor=if_actor)
        return cast(builtins.list[GraphInfo], r["graphs"])

    async def discover(
        self, *, if_actor: str | None = None
    ) -> builtins.list[GraphDiscoveryEntry]:
        """Graph identities visible to this credential, without runtime metadata."""
        r = await self._t.request("GET", "/graphs/discovery", if_actor=if_actor)
        return cast(builtins.list[GraphDiscoveryEntry], r["graphs"])


class Cluster:
    """Cluster deployments. Deployment documents are opaque and keep their exact
    wire keys; for normal operator work use `omnigraph cluster plan/apply`."""

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def plan(
        self, deployment: dict[str, Any], *, if_actor: str | None = None
    ) -> dict[str, Any]:
        """Preview a captured deployment without applying it."""
        return cast(
            dict[str, Any],
            await self._t.request(
                "POST",
                "/cluster/plan",
                body={"deployment": deployment},
                if_actor=if_actor,
            ),
        )

    async def apply(
        self,
        deployment_id: str,
        deployment: dict[str, Any],
        *,
        if_actor: str | None = None,
    ) -> DeploymentOutput:
        """Durable acceptance, not activation. Keep `deployment_id` and observe
        with `get_deployment()`; never resubmit because a response was lost."""
        return cast(
            DeploymentOutput,
            await self._t.request(
                "POST",
                "/cluster/deployments",
                body={"deployment_id": deployment_id, "deployment": deployment},
                if_actor=if_actor,
                accepted_statuses=(202,),
            ),
        )

    async def status(self, *, if_actor: str | None = None) -> DeploymentStatusOutput:
        return cast(
            DeploymentStatusOutput,
            await self._t.request("GET", "/cluster/deployments", if_actor=if_actor),
        )

    async def get_deployment(
        self, deployment_id: str, *, if_actor: str | None = None
    ) -> DeploymentOutput:
        return cast(
            DeploymentOutput,
            await self._t.request(
                "GET", f"/cluster/deployments/{_seg(deployment_id)}", if_actor=if_actor
            ),
        )
