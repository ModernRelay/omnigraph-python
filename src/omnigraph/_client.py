"""The `Omnigraph` client."""

from __future__ import annotations

import types
from typing import Any, Self, cast

import httpx

from ._models import (
    AccessOutput,
    ChangeOutput,
    HealthOutput,
    ReadinessOutput,
    ReadOutput,
    SnapshotOutput,
)
from ._receipts import valid_mutation_receipt
from ._resources import Branches, Cluster, Commits, Graphs, Schema
from ._transport import Transport


def _gq_body(
    query: str,
    *,
    name: str | None,
    params: dict[str, Any] | None,
    branch: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"query": query}
    if name is not None:
        body["name"] = name
    if params is not None:
        body["params"] = params
    if branch is not None:
        body["branch"] = branch
    return body


class Omnigraph:
    """Async client for one `omnigraph-server`, optionally scoped to a graph.

    ```python
    async with Omnigraph("http://127.0.0.1:8080", graph_id="knowledge", token=...) as og:
        result = await og.query("query q() { match { $p: Person } return { $p.name } }")
    ```

    `base_url` is the server root, including any proxy prefix. The client sends
    `Omnigraph-Http-Api: 0.14` on every request, checks it on every response,
    probes `HEAD /healthz` before data requests, follows no redirects, and never
    retries.
    """

    def __init__(
        self,
        base_url: str,
        *,
        graph_id: str | None = None,
        token: str | None = None,
        timeout: float | httpx.Timeout = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        client = httpx.AsyncClient(
            timeout=timeout, follow_redirects=False, transport=transport
        )
        self._init(
            Transport(
                base_url,
                token=token,
                graph_id=graph_id,
                client=client,
                owns_client=True,
            )
        )

    def _init(self, transport: Transport) -> None:
        self._t = transport
        self.branches = Branches(transport)
        self.commits = Commits(transport)
        self.schema = Schema(transport)
        self.graphs = Graphs(transport)
        self.cluster = Cluster(transport)

    @property
    def base_url(self) -> str:
        return self._t.base_url

    @property
    def graph_id(self) -> str | None:
        return self._t.graph_id

    def graph(self, graph_id: str) -> Omnigraph:
        """A client for another graph on the same server, sharing this client's
        connection pool and credential. Close the original, not this one."""
        scoped = object.__new__(Omnigraph)
        scoped._init(self._t.scoped(graph_id))
        return scoped

    async def aclose(self) -> None:
        await self._t.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"Omnigraph(base_url={self.base_url!r}, graph_id={self.graph_id!r})"

    # -- probes --------------------------------------------------------------

    async def health(self) -> HealthOutput:
        """Liveness. Unauthenticated."""
        return cast(HealthOutput, await self._t.request("GET", "/healthz"))

    async def readiness(self) -> ReadinessOutput:
        """Readiness. Both 200 and 503 return availability counts; check `ready`."""
        return cast(
            ReadinessOutput,
            await self._t.request("GET", "/readyz", accepted_statuses=(503,)),
        )

    # -- graph-scoped ----------------------------------------------------------

    async def access(
        self,
        *,
        branch: str | None = None,
        target_branch: str | None = None,
        if_actor: str | None = None,
    ) -> AccessOutput:
        """The actions this credential may take, without exposing policy rules."""
        return cast(
            AccessOutput,
            await self._t.request(
                "GET",
                "/access",
                query={"branch": branch, "target_branch": target_branch},
                if_actor=if_actor,
            ),
        )

    async def query(
        self,
        query: str,
        *,
        name: str | None = None,
        params: dict[str, Any] | None = None,
        branch: str | None = None,
        snapshot: str | None = None,
        if_actor: str | None = None,
    ) -> ReadOutput:
        """Run a GQ read (`POST /query`). `params` keys match `$name` slots."""
        body = _gq_body(query, name=name, params=params, branch=branch)
        if snapshot is not None:
            body["snapshot"] = snapshot
        return cast(
            ReadOutput,
            await self._t.request("POST", "/query", body=body, if_actor=if_actor),
        )

    async def mutate(
        self,
        query: str,
        *,
        name: str | None = None,
        params: dict[str, Any] | None = None,
        branch: str | None = None,
        if_graph_commit: str | None = None,
        if_actor: str | None = None,
    ) -> ChangeOutput:
        """Run a GQ mutation (`POST /mutate`); its statements publish as one commit.

        With `if_graph_commit` (a read's `graph_commit_id`) the dedicated
        conditional route refuses a moved head with `PreconditionFailedError`;
        it is never downgraded to an unconditional write. `commit: None` is a
        successful no-op. A branch statement (`branch create|delete|merge …`)
        names its own branches: send it without `name`, `params`, `branch`.
        """
        body = _gq_body(query, name=name, params=params, branch=branch)
        if if_graph_commit is not None:
            return cast(
                ChangeOutput,
                await self._t.request(
                    "POST",
                    "/mutate/if-graph-commit",
                    body=body,
                    headers={"Omnigraph-If-Graph-Commit": if_graph_commit},
                    if_actor=if_actor,
                ),
            )
        result = await self._t.request("POST", "/mutate", body=body, if_actor=if_actor)
        if not valid_mutation_receipt(result):
            raise self._t.invalid_response(
                "POST", "/mutate", "invalid branch merge receipt"
            )
        return cast(ChangeOutput, result)

    async def snapshot(
        self, *, branch: str | None = None, if_actor: str | None = None
    ) -> SnapshotOutput:
        """The latest commit's snapshot on a branch."""
        return cast(
            SnapshotOutput,
            await self._t.request(
                "GET", "/snapshot", query={"branch": branch}, if_actor=if_actor
            ),
        )
