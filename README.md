# omnigraph

Async Python client for the [Omnigraph](https://github.com/ModernRelay/omnigraph) HTTP API,
generated from `omnigraph-server` **0.16.0** (HTTP contract **0.14**). It mirrors the TypeScript SDK
[`@modernrelay/omnigraph`](https://github.com/ModernRelay/omnigraph-ts): the same routes, the
same contract checks, and the same error model, with Python names.

```sh
pip install omnigraph
```

## Connect and query

```python
from omnigraph import Omnigraph

async with Omnigraph("http://127.0.0.1:8080", graph_id="knowledge", token=TOKEN) as og:
    result = await og.query(
        "query find($name: String) { match { $p: Person { name: $name } } return { $p.name, $p.age } }",
        params={"name": "Alice"},
    )
    print(result["rows"], result["graph_commit_id"])
```

`base_url` is the server root, including any proxy prefix. Select a graph with `graph_id` or
`og.graph("beta")`, which shares the connection pool. Results are the server's JSON as
`TypedDict`s generated from the server's OpenAPI document; field names are the wire names.
Rows omit null-valued fields.

Every request carries `Omnigraph-Http-Api: 0.14`, every response is checked for it, and a
`HEAD /healthz` discovery precedes each data request. The client follows no redirects and
never retries.

## Versions

The package's major.minor is the `omnigraph-server` release it is generated from and tested
against: `omnigraph` 0.14.x is built from server 0.14. The patch number is the SDK's own, for
fixes that change nothing on the wire, so `omnigraph` 0.14.1 does not mean server 0.14.1.
`SERVER_VERSION` names the exact server release.

The HTTP contract is a separate, slower-moving number: `HTTP_API_CONTRACT` is read from the
pinned server's OpenAPI document, and the client refuses a server that speaks another one.
Server releases that keep the wire contract keep its value, so a newer server on the same
contract accepts this client; routes and fields added in a later release need that release.
Pin `omnigraph>=0.14,<0.15` to follow SDK fixes for one server minor.

## Write and verify

```python
changed = await og.mutate(
    "query rename($old: String, $name: String) { update Person set { name: $name } where name = $old }",
    params={"old": "Alice", "name": "Alicia"},
    if_graph_commit=result["graph_commit_id"],
)
```

A successful mutation returns its commit receipt; `commit: None` is a successful no-op. With
`if_graph_commit` the conditional route refuses a moved head with `PreconditionFailedError`.

Branches, merges, and unpublished commits:

```python
await og.branches.create("review")
await og.mutate(insert_query, params=..., branch="review")
merged = await og.branches.merge("review", delete_branch=True)
```

Merge and mutation receipts are validated; a receipt that does not name the requested
operation raises `ApiContractError`.

`og.branches.list_detailed()` adds `details` to the listing: for each branch the credential
may read, its head commit, the branch and commit it started from, and when it was created and
last moved (server 0.15+).

## Ranked reads, settings, and parameters

A read ordered by `nearest`, `bm25` or `rrf()` reports how it ranked its rows:

```python
read = await og.query(
    "query near($v: Vector(2)) { match { $s: Spot } return { $s.slug, nearest($s.at, $v) as dist } "
    "order { nearest($s.at, $v) } limit 10 }",
    params={"v": [0.1, 0.2]},
)
read[
    "ranking"
]  # {"by": "nearest", "order": "ascending", "exhaustive": True, "score_columns": ["dist"]}
```

`query`, `mutate` and `branches.merge` take `settings`, the request's session settings (for
example `{"change_lineage": "verify"}`). A resource budget above the server's ceiling is refused
with `BadRequestError`. A `U64` parameter carries its whole range, up to `2**64 - 1`; Python
integers are sent exactly.

## Streams, loads, feeds, and blobs

```python
# NDJSON, not buffered
async for row in og.export(type_names=["Person"]):
    ...
# One commit, up to 32 MiB
await og.load_ndjson(ndjson_text, branch="main", mode="merge")
# One bounded feed page
page = await og.changes.poll(start="beginning", limit=100)
# A snapshot, then {"baseline": ...}
async for record in og.changes.baseline():
    ...
await og.blobs.put(b"...", entity="node", type="Doc", id="d1", property="body")
await og.queries.invoke("people", params={"name": "Ada"})
```

Ordinary JSON requests are limited to 1 MiB by the server; bulk loads go through
`load_ndjson`.

## Recorded operations

A cluster server started with `OMNIGRAPH_OPERATION_ROUTES=true` runs `optimize` on a graph's
`main` while it serves, as a recorded operation tracked by an id the caller chose (server
0.16+; every route needs the `maintain` action on `main`):

```python
from omnigraph import new_operation_id

op_id = new_operation_id()  # keep it: after a lost response, look it up, never resubmit
await og.operations.optimize(op_id, datasets=["node:Person"], max_gate_hold_ms=30_000)
async with asyncio.timeout(600):
    done = await og.operations.wait(op_id)
state = done["operation"]["state"]  # terminal: is_terminal(state)
await og.operations.cancel(op_id)
```

`get` and `wait` answer `lookup: "unknown"` for an id the record does not hold; that does not
prove the operation never ran. `wait` polls only the lookup and lets any error end the wait.
A succeeded run may still have deferred or failed datasets: read
`operation["outcome"]["datasets"]`. The record's types (`Operation`, `OperationResult`) are
written by hand from the server's record, which the OpenAPI document leaves open.

A merge with `dry_run=True` is a read: a lost answer is not `outcome_unknown`, while a reply
that contradicts the dry run is.

## Errors

Every error is an `OmnigraphError` subclass chosen by status and `code` (`ConflictError`,
`PreconditionFailedError`, `PayloadTooLargeError`, `GraphUnavailableError`, ...). Each carries:

- `disposition`: the server's `effects` (`none`, `partial`, `unknown`) and next `action`;
- `request_dispatched`: whether the request may have reached the server;
- `outcome_unknown`: a write may have taken effect — reconcile before retrying. The server's
  word decides on any route, reads included; only a reply without one falls back to the route.

A code's class refines its status's: `NotAdmittedError` is the `ForbiddenError` for an OIDC
identity the server does not admit (signing in again will not help; the operator must admit
it), and `GraphUnavailableError` is the `ServiceUnavailableError` for a graph that is not
served. `WriterFencedError` is the `ConflictError` for a branch another process claimed
(`writer_fenced` names the epochs; nothing was written). Error details are properties: `ConflictError.merge_conflicts`, `.key_conflict`,
`.read_set_conflict`, `PreconditionFailedError.precondition_failure`,
`PayloadTooLargeError.resource_limit`, `GoneError.change_feed_gap`, and so on.

A graph with no applied policy refuses every action, reads included, with `ForbiddenError`
(server 0.16; `OMNIGRAPH_ALLOW_READS_WITHOUT_POLICY=1` restores reads for static tokens).

The token never appears in a `repr` or an error message.

## Cluster deployments

`og.cluster.plan/apply/status/get_deployment` submit and observe captured deployment bundles.
Bundles are opaque here, as in the TypeScript SDK; for operator work use
`omnigraph cluster plan/apply --target NAME --config DIR`.

## Development

```sh
uv sync
uv run pytest                      # unit tests (mocked transport)
OMNIGRAPH_TEST_SERVER=1 OMNIGRAPH_BIN_DIR=/path/to/v0.16.0 uv run pytest tests/test_e2e.py
uv run python scripts/generate.py --check   # generated files match spec/openapi.json
uv run mypy && uv run ruff check . && uv run ruff format --check .
```

`spec/openapi.json` is the pinned server release's document (`scripts/sync_spec.py` fetches it
for the version in `[tool.omnigraph]`); `scripts/generate.py` regenerates `_models.py` and
`_version.py` from it.
