"""Resource groups hung off `Omnigraph`: branches, commits, schema, graphs, cluster."""

from __future__ import annotations

import builtins
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, cast
from urllib.parse import quote

import httpx

from ._models import (
    BlobWriteOutput,
    BranchCreateOutput,
    BranchDeleteOutput,
    BranchMergeOutput,
    ChangeFeedOutput,
    ChangeOutput,
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
    QueriesCatalogOutput,
    ReadOutput,
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


async def _ndjson(response: httpx.Response) -> AsyncIterator[Any]:
    """Parse an NDJSON body line by line as it arrives."""
    async for line in response.aiter_lines():
        if line.strip():
            yield json.loads(line)


class Queries:
    """The graph's server-side stored queries (its `queries:` registry)."""

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def list(self, *, if_actor: str | None = None) -> QueriesCatalogOutput:
        """Every stored query with its typed parameters."""
        return cast(
            QueriesCatalogOutput,
            await self._t.request("GET", "/queries", if_actor=if_actor),
        )

    async def invoke(
        self,
        name: str,
        *,
        params: dict[str, Any] | None = None,
        branch: str | None = None,
        snapshot: str | None = None,
        expect_mutation: bool | None = None,
        if_graph_commit: str | None = None,
        if_actor: str | None = None,
    ) -> ReadOutput | ChangeOutput:
        """Invoke a stored query by name. An unknown name and one the caller may
        not invoke both raise `NotFoundError`. `expect_mutation` asserts the
        stored query's kind; `if_graph_commit` selects the conditional route."""
        body: dict[str, Any] = {}
        for key, value in (
            ("params", params),
            ("branch", branch),
            ("snapshot", snapshot),
            ("expect_mutation", expect_mutation),
        ):
            if value is not None:
                body[key] = value
        path = f"/queries/{_seg(name)}"
        headers = None
        if if_graph_commit is not None:
            path += "/if-graph-commit"
            headers = {"Omnigraph-If-Graph-Commit": if_graph_commit}
        return cast(
            "ReadOutput | ChangeOutput",
            await self._t.request(
                "POST", path, body=body, headers=headers, if_actor=if_actor
            ),
        )


class Changes:
    """The change feed of a branch."""

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def poll(
        self,
        *,
        branch: str | None = None,
        cursor: str | None = None,
        start: str | None = None,
        page_token: str | None = None,
        limit: int | None = None,
        kind: Sequence[str] | None = None,
        type: Sequence[str] | None = None,
        op: Sequence[str] | None = None,
        if_actor: str | None = None,
    ) -> ChangeFeedOutput:
        """One bounded feed page. Follow `next_page_token` within the poll and
        persist `cursor` only from its terminal page. A `GoneError` means the
        history is no longer retained: take a new baseline."""
        return cast(
            ChangeFeedOutput,
            await self._t.request(
                "GET",
                "/changes",
                query={
                    "branch": branch,
                    "cursor": cursor,
                    "start": start,
                    "page_token": page_token,
                    "limit": _str(limit),
                    "kind": kind,
                    "type": type,
                    "op": op,
                },
                if_actor=if_actor,
            ),
        )

    async def baseline(
        self,
        *,
        branch: str | None = None,
        kind: Sequence[str] | None = None,
        type: Sequence[str] | None = None,
        op: Sequence[str] | None = None,
        if_actor: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a pinned snapshot of entities, then one final `{"baseline":
        ...}` record carrying the cursor that resumes the feed. The terminal
        record is yielded only after the stream ended completely."""
        body: dict[str, Any] = {}
        for key, value in (
            ("branch", branch),
            ("kind", kind),
            ("type", type),
            ("op", op),
        ):
            if value is not None:
                body[key] = list(value) if not isinstance(value, str) else value
        async with self._t.stream(
            "POST", "/changes/baseline", body=body, if_actor=if_actor
        ) as response:
            terminal: dict[str, Any] | None = None
            async for record in _ndjson(response):
                if terminal is not None:
                    raise ValueError(
                        "change baseline has records after its terminal record"
                    )
                if isinstance(record, dict) and "baseline" in record:
                    inner = record["baseline"]
                    if not (
                        isinstance(inner, dict)
                        and isinstance(inner.get("snapshot_commit_id"), str)
                        and isinstance(inner.get("resume_cursor"), str)
                    ):
                        raise ValueError(
                            "change baseline has an invalid terminal record"
                        )
                    terminal = record
                else:
                    yield record
            if terminal is None:
                raise ValueError("change baseline ended without a terminal record")
            yield terminal


class Blobs:
    """Blob cell reads and atomic writes, addressed by logical identity."""

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    @staticmethod
    def _selector(
        entity: str, type: str, id: str, property: str, branch: str | None
    ) -> dict[str, str | None]:
        return {
            "entity": entity,
            "type": type,
            "id": id,
            "property": property,
            "branch": branch,
        }

    async def put(
        self,
        data: bytes,
        *,
        entity: str,
        type: str,
        id: str,
        property: str,
        branch: str | None = None,
        if_match: str | None = None,
        if_actor: str | None = None,
    ) -> BlobWriteOutput:
        """Replace one Blob value (at most 32 MiB) as one graph commit."""
        return cast(
            BlobWriteOutput,
            await self._t.request(
                "PUT",
                "/blob",
                content=data,
                content_type="application/octet-stream",
                query=self._selector(entity, type, id, property, branch),
                headers={"If-Match": if_match} if if_match is not None else None,
                if_actor=if_actor,
            ),
        )

    async def clear(
        self,
        *,
        entity: str,
        type: str,
        id: str,
        property: str,
        branch: str | None = None,
        if_match: str | None = None,
        if_actor: str | None = None,
    ) -> BlobWriteOutput:
        """Set a nullable Blob value to null; an existing null answers `commit: None`."""
        return cast(
            BlobWriteOutput,
            await self._t.request(
                "DELETE",
                "/blob",
                query=self._selector(entity, type, id, property, branch),
                headers={"If-Match": if_match} if if_match is not None else None,
                if_actor=if_actor,
            ),
        )

    async def get(
        self,
        *,
        entity: str,
        type: str,
        id: str,
        property: str,
        branch: str | None = None,
        snapshot: str | None = None,
        if_none_match: str | None = None,
        range: str | None = None,
        if_actor: str | None = None,
    ) -> httpx.Response:
        """The managed bytes (200/206), an external `Location` (302, never
        followed), or not-modified (304). Inspect `status_code` first."""
        query = self._selector(entity, type, id, property, branch)
        query["snapshot"] = snapshot
        headers = {"Accept": "application/octet-stream"}
        if if_none_match is not None:
            headers["If-None-Match"] = if_none_match
        if range is not None:
            headers["Range"] = range
        return await self._t.send(
            "GET",
            "/blob",
            query=query,
            headers=headers,
            accepted_statuses=(302, 304),
            if_actor=if_actor,
        )

    async def stat(
        self,
        *,
        entity: str,
        type: str,
        id: str,
        property: str,
        branch: str | None = None,
        snapshot: str | None = None,
        if_none_match: str | None = None,
        if_actor: str | None = None,
    ) -> httpx.Response:
        """HEAD metadata without the bytes; 302 and 304 as for `get`."""
        query = self._selector(entity, type, id, property, branch)
        query["snapshot"] = snapshot
        headers = {"Accept": "application/octet-stream"}
        if if_none_match is not None:
            headers["If-None-Match"] = if_none_match
        return await self._t.send(
            "HEAD",
            "/blob",
            query=query,
            headers=headers,
            accepted_statuses=(302, 304),
            if_actor=if_actor,
        )
