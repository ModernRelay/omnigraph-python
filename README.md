# omnigraph

Async Python client for the [Omnigraph](https://github.com/ModernRelay/omnigraph) HTTP API,
contract **0.14**. It mirrors the TypeScript SDK
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

The package's major.minor is the HTTP contract it speaks: `omnigraph` 0.14.x talks to
`omnigraph-server` 0.14.x and refuses any other contract. The patch number is the SDK's own,
for fixes that change nothing on the wire, so `omnigraph` 0.14.1 does not mean server 0.14.1.
Upgrade the server and this package together when the minor changes, and pin
`omnigraph>=0.14,<0.15` to follow SDK fixes for one contract.

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

## Errors

Every error is an `OmnigraphError` subclass chosen by status and `code` (`ConflictError`,
`PreconditionFailedError`, `PayloadTooLargeError`, `GraphUnavailableError`, ...). Each carries:

- `disposition`: the server's `effects` (`none`, `partial`, `unknown`) and next `action`;
- `request_dispatched`: whether the request may have reached the server;
- `outcome_unknown`: a write may have taken effect — reconcile before retrying.

The token never appears in a `repr` or an error message.

## Cluster deployments

`og.cluster.plan/apply/status/get_deployment` submit and observe captured deployment bundles.
Bundles are opaque here, as in the TypeScript SDK; for operator work use
`omnigraph cluster plan/apply --target NAME --config DIR`.

## Development

```sh
uv sync
uv run pytest                      # unit tests (mocked transport)
OMNIGRAPH_TEST_SERVER=1 OMNIGRAPH_BIN_DIR=/path/to/v0.14.0 uv run pytest tests/test_e2e.py
uv run python scripts/generate.py --check   # generated files match spec/openapi.json
uv run mypy && uv run ruff check . && uv run ruff format --check .
```

`spec/openapi.json` is the pinned server release's document (`scripts/sync_spec.py` fetches it
for the version in `[tool.omnigraph]`); `scripts/generate.py` regenerates `_models.py` and
`_version.py` from it.
