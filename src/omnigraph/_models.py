"""Wire models generated from spec/openapi.json. Do not edit by hand.

Regenerate with `uv run python scripts/generate.py`.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

AccessAction = Literal[
    'read',
    'export',
    'change',
    'schema_apply',
    'branch_create',
    'branch_delete',
    'branch_merge',
    'commit_publish',
    'commit_drop',
    'invoke_query',
]


class AccessOutput(TypedDict):
    """
    What the caller's own credential may do on one graph, by the graph's
    installed policy. It names actions, never the rules that allow them, and
    says nothing about any other actor.
    """

    actions: list[AccessAction]
    actor_id: NotRequired[str | None]
    branch: NotRequired[str | None]
    graph_id: str
    graph_wide: list[AccessAction]
    target_branch: NotRequired[str | None]


Applicability = Literal['machine_applicable', 'needs_review']


class BlobPreconditionFailureOutput(TypedDict):
    """
    A Blob write's `If-Match` did not hold for the cell (HTTP 412). The write
    had no effect. `current_etag` is the cell's validator when it holds a
    managed value; it is absent for a null or external value, which no tag
    matches. Distinct from [`PreconditionFailureOutput`], the graph-commit
    precondition.
    """

    current_etag: NotRequired[str | None]


class BlobRangeOutput(TypedDict):
    """
    Normalized half-open range details for an unsatisfiable managed Blob read.

    HTTP also returns `Content-Range: bytes */N`; these fields let SDKs inspect
    the failure without parsing either that header or the human-readable text.
    """

    end: int
    length: int
    start: int


BlobWriteState = Literal['managed', 'null']


BranchCreateOutput = TypedDict(
    'BranchCreateOutput',
    {
        'actor_id': NotRequired[str | None],
        'from': str,
        'from_commit_id': str,
        'name': str,
        'uri': str,
    },
)


BranchCreateRequest = TypedDict(
    'BranchCreateRequest',
    {
        'from': NotRequired[str | None],
        'from_commit': NotRequired[str | None],
        'name': str,
    },
)


class BranchDeleteOutput(TypedDict):
    actor_id: NotRequired[str | None]
    name: str
    uri: str


class BranchListOutput(TypedDict):
    branches: list[str]


BranchMergeOutcome = Literal['already_up_to_date', 'fast_forward', 'merged']


"""
`name` was forked off `from` at the commit `from_commit_id`: the
    head of `from`, or the commit a `from commit "<id>"` start named,
    which `from` wrote.
"""
BranchOutcomeOutput1 = TypedDict(
    'BranchOutcomeOutput1',
    {
        'from': str,
        'from_commit_id': str,
        'kind': Literal['created'],
        'name': str,
    },
)


class BranchOutcomeOutput2(TypedDict):
    """
    `name` was removed.
    """

    kind: Literal['deleted']
    name: str


class BranchOutcomeOutput3(TypedDict):
    """
    `source` was merged into `target`; `merge` is the three-way result,
    one of `already_up_to_date`, `fast_forward`, `merged`.
    """

    kind: Literal['merged']
    merge: BranchMergeOutcome
    source: str
    target: str


class BranchOutcomeOutput4(TypedDict):
    """
    `commit publish`: the receipt's `commit` is the now-published commit.
    """

    kind: Literal['published']


class BranchOutcomeOutput5(TypedDict):
    """
    `commit drop`: the unpublished commit `graph_commit_id` is gone.
    """

    graph_commit_id: str
    kind: Literal['dropped']


BranchOutcomeOutput = (
    BranchOutcomeOutput1
    | BranchOutcomeOutput2
    | BranchOutcomeOutput3
    | BranchOutcomeOutput4
    | BranchOutcomeOutput5
)


BranchStartRefusalReason = Literal[
    'not_retained',
    'schema_changed',
    'earlier_storage_format',
    'branch_deleted',
    'unpublished_commit',
    'unattached_snapshot',
    'unknown',
]


class ChangeBaselineOutput(TypedDict):
    """
    Terminal payload of a baseline stream: the captured snapshot commit and
    the cursor that resumes the feed immediately after it.
    """

    resume_cursor: str
    snapshot_commit_id: str


class ChangeBaselineRecord(TypedDict):
    """
    Wire envelope of the FINAL baseline stream line: `{"baseline": {...}}`,
    distinguishable from snapshot records (which carry `type`/`edge` keys).
    Emitted exactly once, only after every snapshot record — an interrupted
    stream has no terminal record and therefore no usable cursor.
    """

    baseline: ChangeBaselineOutput


class ChangeCauseOutput(TypedDict):
    """
    The commit cause of one change block, stated once.
    """

    actor_id: NotRequired[str | None]
    authored_at: int
    authored_branch: str
    graph_commit_id: str
    merged_parent_commit_id: NotRequired[str | None]
    parent_commit_id: NotRequired[str | None]


ChangeDiffRefusalReason = Literal['parentless_commit', 'schema_boundary', 'unknown']


"""
Edge endpoints as graph references. Endpoints belong to each image, so an
    endpoint-moving update has distinct before and after endpoints.
"""
ChangeEndpointsOutput = TypedDict(
    'ChangeEndpointsOutput',
    {
        'from': str,
        'to': str,
    },
)


class ChangeFeedGapOutput(TypedDict):
    """
    A change continuation can no longer be reconstructed from retained history
    (HTTP 410), sent with [`ErrorCode::ChangeFeedGap`]. Recovery is the
    baseline handshake; retrying the same cursor cannot succeed.
    """

    cursor: NotRequired[str | None]
    first_unreadable_commit_id: str


class ChangeImageOutput(TypedDict):
    """
    One exact logical entity image, decoded with the commit-era schema.
    """

    endpoints: NotRequired[ChangeEndpointsOutput | None]
    properties: Any


ChangeOp = Literal['insert', 'update', 'delete']


class ChangeTypeOutput(TypedDict):
    """
    Graph-scoped type identity. `id` is opaque: it survives a supported rename
    and changes after drop/re-add. It is not a type-name selector or path.
    """

    id: str
    name: str


CommitKind = Literal['published', 'unpublished', 'unattached']


CommitListing = Literal['history', 'unpublished', 'unattached']


class CommitOutput(TypedDict):
    actor_id: NotRequired[str | None]
    created_at: int
    graph_branch: NotRequired[str | None]
    graph_commit_id: str
    graph_manifest_version: int
    kind: CommitKind
    merged_parent_commit_id: NotRequired[str | None]
    parent_commit_id: NotRequired[str | None]
    published: NotRequired[bool]
    root_commit_id: NotRequired[str | None]


class DeploymentOutput(TypedDict):
    active: bool
    deployment: dict[str, Any]
    in_progress: bool


class DeploymentRequest(TypedDict):
    deployment: dict[str, Any]
    deployment_id: str


class DeploymentStatusOutput(TypedDict):
    active: bool
    in_progress: bool
    status: dict[str, Any]


DispositionAction = Literal['fix', 'refresh', 'retry', 'recover', 'reconcile']


DispositionEffects = Literal['none', 'partial', 'unknown']


class DispositionOutput(TypedDict):
    """
    What a refused or failed request did and what its caller should do next.
    A server states it on every error response, computed where that knowledge
    is; a client that lost the response knows less, and says so.
    """

    action: DispositionAction
    effects: DispositionEffects


EntityKind = Literal['node', 'edge']


ErrorCode = Literal[
    'unauthorized',
    'forbidden',
    'bad_request',
    'api_contract_mismatch',
    'actor_mismatch',
    'outcome_unknown',
    'precondition_failed',
    'recovery_required',
    'external_blob_source',
    'change_feed_gap',
    'not_found',
    'method_not_allowed',
    'request_timeout',
    'conflict',
    'branch_start_refusal',
    'unattached_cannot_publish',
    'payload_too_large',
    'unsupported_media_type',
    'range_not_satisfiable',
    'too_many_requests',
    'service_unavailable',
    'graph_unavailable',
    'internal',
    'cancelled',
    'deadline_exceeded',
    'result_too_large',
]


class ExportRequest(TypedDict):
    branch: NotRequired[str | None]
    type_names: NotRequired[list[str]]


class ExternalBlobSourceOutput(TypedDict):
    """
    Structured details for an allowed external Blob source that could not be
    probed or read, sent with [`ErrorCode::ExternalBlobSource`].
    """

    reason: str
    uri: str


class FullTextIndexRebuildRequiredOutput(TypedDict):
    """
    A selected full-text index cannot safely serve the current analyzer (HTTP 409).
    This is not a retryable write conflict: an operator must rebuild the live
    branch's indexes. Historical snapshots stay unchanged; branch old content
    and rebuild that branch to search it.
    """

    index: str
    reason: str


class FullTextIndexRequiredOutput(TypedDict):
    """
    A full-text call read a declared full-text index that has no segment at
    the query's snapshot (HTTP 409), so no segment carries its analyzer. This
    is not a retryable conflict: an operator builds the branch's index
    (`omnigraph optimize` on main, `omnigraph rebuild-full-text-indexes
    --branch` elsewhere). Historical snapshots stay unchanged.
    """

    index: str


GraphAvailability = Literal['loading', 'ready', 'transitioning', 'blocked', 'stopping']


GraphAvailabilityAction = Literal[
    'none',
    'wait_for_startup',
    'wait_for_transition',
    'apply_correction_or_restart',
    'wait_for_restart',
]


class GraphBatchDeclarationOutput(TypedDict):
    """
    One logical declaration touched by a graph-batch load.

    This deliberately carries the accepted-schema name, not a backing dataset
    selector, path, or Lance identity.
    """

    entities_loaded: int
    name: str


class GraphDiscoveryEntry(TypedDict):
    """
    A graph's existence, without storage, schema, data, or serving metadata.
    """

    display_name: str
    graph_id: str


class GraphDiscoveryOutput(TypedDict):
    """
    Authenticated minimal inventory from `GET /graphs/discovery`.
    """

    graphs: list[GraphDiscoveryEntry]


GraphStartupFailure = Literal[
    'invalid_configuration',
    'invalid_policy',
    'invalid_external_blob_policy',
    'open_failed',
    'invalid_stored_queries',
]


class HealthOutput(TypedDict):
    internal_schema_version: int
    source_version: NotRequired[str | None]
    status: str
    version: str


class InvokeStoredQueryRequest(TypedDict):
    """
    Body for `POST /queries/{name}` — invokes the server-side stored query
    named in the path. The query source and name come from the registry,
    never the body; only the runtime inputs are supplied here.
    """

    branch: NotRequired[str | None]
    expect_mutation: NotRequired[bool | None]
    params: NotRequired[Any]
    snapshot: NotRequired[str | None]


class KeyConflictOutput(TypedDict):
    """
    A strict insert rejected because `entity_id` already names an entity in the
    selected node or edge type. The refused write changed nothing; an earlier
    step of the same request, such as the branch a load forks, may already have
    published, which the error's `disposition` states. Partial or ambiguous
    attempts surface `recovery_required` instead.
    """

    entity_id: NotRequired[str | None]
    entity_kind: EntityKind
    type_name: str


LoadEmbeddingGeneration = Literal['unsupported']


LoadMode = Literal['overwrite', 'append', 'merge']


class LoadSliceExecutedOutput(TypedDict):
    """
    What one slice of a `CsvSource` measured: a byte range of the capture
    parsed whole by one partition.
    """

    elapsed_compute_ns: int
    end_ns: int
    partition: int
    rows: int
    slice: int
    start_ns: int


class MergeBaseOutput(TypedDict):
    """
    The commit a merge of `source` into `target` would classify against, and
    the two heads it was computed from.
    """

    merge_base: CommitOutput
    source: str
    source_commit_id: str
    target: str
    target_commit_id: str


MergeConflictKind = Literal[
    'divergent_insert',
    'divergent_update',
    'delete_vs_update',
    'orphan_edge',
    'unique_violation',
    'cardinality_violation',
    'value_constraint_violation',
]


class MergeConflictOutput(TypedDict):
    entity_id: NotRequired[str | None]
    entity_kind: EntityKind
    kind: MergeConflictKind
    message: str
    type_name: str


ParamKind = Literal[
    'string',
    'bool',
    'int',
    'bigint',
    'float',
    'date',
    'datetime',
    'blob',
    'vector',
    'list',
]


class PlanRequest(TypedDict):
    deployment: dict[str, Any]


class PositionOutput(TypedDict):
    """
    A source position: 1-based line and column (in characters) and the byte
    offset.
    """

    byte: int
    column: int
    line: int


class PreconditionFailureOutput(TypedDict):
    """
    Structured details for a caller write-precondition failure: HTTP 412, a
    mutation carried `Omnigraph-If-Graph-Commit: <commit_id>`, and the branch
    head no longer matches that id. The write had no effect; the caller re-reads
    the branch and decides again. `actual` is `None` on a branch with no commits.
    """

    actual: NotRequired[str | None]
    expected: str


class PublishedDatasetVersionConflictOutput(TypedDict):
    """
    Structured details for a publisher-level OCC failure. Surfaces alongside
    HTTP 409 when a write was rejected because the caller's pre-write view of
    one backing dataset's published version was stale relative to the current
    head. The expected/actual fields tell the client which dataset to refresh.
    """

    actual_published_dataset_version: int
    entity_kind: EntityKind
    expected_published_dataset_version: int
    type_name: str


class ReadPageOutput(TypedDict):
    """
    The page state a `branch diff` answer carries: the exact commits it
    compares, and the token `after page "<token>"` continues it with, absent
    on its last page.
    """

    base_commit_id: NotRequired[str | None]
    from_commit_id: NotRequired[str | None]
    next_page_token: NotRequired[str | None]
    to_commit_id: NotRequired[str | None]


class ReadSetConflictOutput(TypedDict):
    """
    Structured authority mismatch for a prepared write. Values are
    strings because members include optional graph commit ids and future
    authority tokens, not only numeric published dataset versions.
    """

    actual: NotRequired[str | None]
    expected: NotRequired[str | None]
    member: str


class ReadTargetOutput(TypedDict):
    branch: NotRequired[str | None]
    snapshot: NotRequired[str | None]


class ReadinessOutput(TypedDict):
    """
    The readiness witness of one replica (`GET /readyz`, RFC 0049): whether
    it is serving or draining, the applied revision it booted from, and how
    many graphs it does and does not serve. Unauthenticated, so it carries
    no graph id: those stay behind `GET /graphs`.
    """

    blocked_graph_count: int
    booted_serving_digest: NotRequired[str | None]
    loading_graph_count: int
    ready: bool
    ready_graph_count: int
    served_graph_count: int
    shutdown_grace_seconds: int
    state_cas: NotRequired[str | None]
    state_revision: int
    status: str


class RecoveryRequiredOutput(TypedDict):
    operation_id: str


class ResourceLimitOutput(TypedDict):
    """
    A write rejected before durable recovery ownership because its bounded
    physical plan exceeded an explicit entity, byte, or transaction-chain ceiling.
    """

    actual: int
    limit: int
    resource: str


class SettingsRequest(TypedDict):
    """
    The `settings` field of a request: one optional value per `request`-scope
    setting of the definition, applied to the request's session before the
    source's own `set` lines, so a `set` line in the request's text overrides
    the field. An absent field is empty. A `process` setting has no field
    here, so `{"stage_write_concurrency": 64}` is refused as an unknown field.
    """

    ann_nprobes: NotRequired[int]
    engine: NotRequired[Literal['v2']]
    history_release_bytes: NotRequired[int]
    load_source_max_bytes: NotRequired[int]
    merge_lineage: NotRequired[Literal['off', 'on', 'verify']]
    query_memory_bytes: NotRequired[int]
    traversal_work_limit: NotRequired[int]
    write_max_bytes: NotRequired[int]


class SnapshotDatasetOutput(TypedDict):
    dataset_path: str
    entity_count: int
    entity_kind: EntityKind
    native_dataset_branch: NotRequired[str | None]
    published_dataset_version: int
    type_name: str


class SnapshotOutput(TypedDict):
    datasets: list[SnapshotDatasetOutput]
    graph_branch: str
    graph_manifest_version: int
    internal_schema_version: int


class SystemColumnsOutput(TypedDict):
    """
    A graph's system column spellings (see `SchemaOutput::system_columns`).
    """

    dst: str
    id: str
    src: str


class TextEditOutput(TypedDict):
    """
    A UTF-8 byte range in the original source, with an exclusive end.
    """

    end: int
    replacement: str
    start: int


class BlobSelectorOutput(TypedDict):
    """
    One logical graph Blob cell.
    """

    entity: EntityKind
    id: str
    property: str
    type: str


class BlobWriteOutput(TypedDict):
    """
    Receipt of a Blob put or clear.

    A put leaves managed bytes, with their `size` and `etag`; a clear leaves
    null, with neither. The `etag` is the one a read at `commit` reports.
    """

    actor_id: NotRequired[str | None]
    branch: str
    commit: CommitOutput | None
    etag: NotRequired[str | None]
    kind: BlobWriteState
    selector: BlobSelectorOutput
    size: NotRequired[int | None]


class BranchMergeRequest(TypedDict):
    as_commit: NotRequired[bool]
    delete_branch: NotRequired[bool]
    dry_run: NotRequired[bool]
    settings: NotRequired[SettingsRequest | None]
    source: str
    target: NotRequired[str | None]


class BranchStartRefusalOutput(TypedDict):
    """
    A branch create refused at the graph commit `from_commit` named; nothing
    was created.
    """

    branch: NotRequired[str | None]
    graph_commit_id: str
    reason: BranchStartRefusalReason
    type_name: NotRequired[str | None]


class ChangeBaselineRequest(TypedDict):
    """
    Body for the change baseline handshake.
    """

    branch: NotRequired[str | None]
    kind: NotRequired[list[EntityKind]]
    op: NotRequired[list[ChangeOp]]
    type: NotRequired[list[str]]


class ChangeDiffRefusalOutput(TypedDict):
    """
    A well-formed entity-diff request this commit cannot satisfy (HTTP 409).
    """

    graph_commit_id: str
    reason: ChangeDiffRefusalReason
    type_name: NotRequired[str | None]


class ChangeErrorOutput(TypedDict):
    """
    Error envelope for the read-only change surfaces (`…/changes`,
    `…/changes/baseline`, `…/commits/{commit_id}/changes`): a wire-compatible
    projection of [`ErrorOutput`] restricted to the graph-vocabulary details
    those routes can produce after their error projection. The write-path
    conflict shapes (key / published-dataset-version / merge / read-set) are
    structurally absent because change routes cannot produce them. Servers
    serialize [`ErrorOutput`]; every field a change route can populate appears
    here with the same name and meaning, and absent optionals are wire-compatible.
    """

    change_diff_refusal: NotRequired[ChangeDiffRefusalOutput | None]
    change_feed_gap: NotRequired[ChangeFeedGapOutput | None]
    code: ErrorCode
    disposition: DispositionOutput
    error: str
    recovery_required: NotRequired[RecoveryRequiredOutput | None]
    resource_limit: NotRequired[ResourceLimitOutput | None]


class ChangeRequest(TypedDict):
    branch: NotRequired[str | None]
    name: NotRequired[str | None]
    params: NotRequired[Any]
    query: str
    settings: NotRequired[SettingsRequest | None]


class CommitListOutput(TypedDict):
    commits: list[CommitOutput]
    head_commit_id: NotRequired[str | None]
    next_page_token: NotRequired[str | None]


class EntityChangeOutput(TypedDict):
    """
    One entity change. Cause is stated once on the enclosing block, never here.
    An insert carries only `after`, an update exact `before` and `after`, a
    delete only `before`.
    """

    after: NotRequired[ChangeImageOutput | None]
    before: NotRequired[ChangeImageOutput | None]
    id: str
    kind: EntityKind
    op: ChangeOp
    type: ChangeTypeOutput


class GraphBatchLoadOutput(TypedDict):
    """
    Terminal result for the raw graph-level NDJSON load surface.
    """

    actor_id: NotRequired[str | None]
    base_branch: NotRequired[str | None]
    branch: str
    branch_created: bool
    commit: NotRequired[CommitOutput | None]
    edges: list[GraphBatchDeclarationOutput]
    embedding_generation: LoadEmbeddingGeneration | None
    mode: LoadMode
    nodes: list[GraphBatchDeclarationOutput]
    total_entities: int


class GraphInfo(TypedDict):
    """
    One entry in the response from `GET /graphs`. Cluster operators
    consume this list to discover which graphs the server is currently
    serving. This legacy metadata includes the storage `uri`; identity-only
    existence discovery uses [`GraphDiscoveryEntry`] instead.
    """

    action: GraphAvailabilityAction
    failure: NotRequired[GraphStartupFailure | None]
    graph_id: str
    read_available: bool
    state: GraphAvailability
    uri: str
    write_available: bool


class GraphListOutput(TypedDict):
    """
    Response from `GET /graphs`. Lists every graph registered with the
    server in alphabetical order by `graph_id` (sorted server-side so
    clients get deterministic output across requests).
    """

    graphs: list[GraphInfo]


class IngestOutput(TypedDict):
    actor_id: NotRequired[str | None]
    base_branch: NotRequired[str | None]
    branch: str
    branch_created: bool
    commit: NotRequired[CommitOutput | None]
    edges: list[GraphBatchDeclarationOutput]
    embedding_generation: LoadEmbeddingGeneration | None
    mode: LoadMode
    nodes: list[GraphBatchDeclarationOutput]
    total_entities: int
    uri: str


IngestRequest = TypedDict(
    'IngestRequest',
    {
        'branch': NotRequired[str | None],
        'data': str,
        'from': NotRequired[str | None],
        'mode': NotRequired[LoadMode | None],
    },
)


class LoadOperatorExecutedOutput(TypedDict):
    """
    What one operator of an executed load plan did.
    """

    elapsed_compute_ns: int
    id: int
    node: str
    operator: str
    partitions: NotRequired[int]
    rows: int
    slices: NotRequired[list[LoadSliceExecutedOutput]]
    wall_ns: int


class ParamDescriptor(TypedDict):
    """
    One declared parameter of a stored query, projected for the catalog.
    """

    item_kind: NotRequired[ParamKind | None]
    kind: ParamKind
    name: str
    nullable: bool
    vector_dim: NotRequired[int | None]


class QueryCatalogEntry(TypedDict):
    """
    One entry in the stored-query catalog (`GET /queries`).
    """

    description: NotRequired[str | None]
    instruction: NotRequired[str | None]
    mutation: bool
    name: str
    params: list[ParamDescriptor]
    tool_name: str


class QueryRequest(TypedDict):
    """
    Inline read-query request for `POST /query`.

    Mutations are rejected with 400 — use `POST /mutate` for write queries.
    Field names are deliberately short (`query`, `name`) to match the GQ
    keyword and the CLI `-e` flag.
    """

    branch: NotRequired[str | None]
    name: NotRequired[str | None]
    params: NotRequired[Any]
    query: str
    settings: NotRequired[SettingsRequest | None]
    snapshot: NotRequired[str | None]


class ReadOutput(TypedDict):
    columns: NotRequired[list[str]]
    graph_commit_id: NotRequired[str | None]
    page: NotRequired[ReadPageOutput | None]
    query_name: str
    row_count: int
    rows: Any
    target: ReadTargetOutput


class SchemaOutput(TypedDict):
    catalogue_source: NotRequired[str | None]
    schema_source: str
    system_columns: NotRequired[SystemColumnsOutput | None]


class SuggestionOutput(TypedDict):
    """
    Non-overlapping edits against the original request source.
    """

    applicability: Applicability
    edits: list[TextEditOutput]


class ChangeBlockOutput(TypedDict):
    """
    One commit block inside a feed page.
    """

    cause: ChangeCauseOutput
    changes: list[EntityChangeOutput]


class ChangeFeedOutput(TypedDict):
    """
    One bounded feed poll result.
    """

    blocks: list[ChangeBlockOutput]
    caught_up: NotRequired[bool | None]
    cursor: NotRequired[str | None]
    next_page_token: NotRequired[str | None]


class CommitChangesOutput(TypedDict):
    """
    One bounded page of the finite commit entity diff.
    """

    cause: ChangeCauseOutput
    changes: list[EntityChangeOutput]
    next_page_token: NotRequired[str | None]


class DiagnosticOutput(TypedDict):
    """
    The diagnostics contract for a refused query (RFC 0047): a stable code
    (`Q…` parse, `T…` typecheck); where the failure is, as a source position
    or as the stage and expression when it is post-parse; what was expected or
    violated; and one concrete fix, absent when `expected` names the decision.
    Rides `ErrorOutput.diagnostic` as an additive detail because
    [`ErrorCode`] is a closed compatibility contract.
    """

    code: str
    expected: str
    expression: NotRequired[str | None]
    fix: NotRequired[str | None]
    position: NotRequired[PositionOutput | None]
    stage: NotRequired[str | None]
    suggestion: NotRequired[SuggestionOutput | None]


class DiffOutput(TypedDict):
    """
    One bounded page of a graph diff: the net entity changes between two
    resolved commits, in the commit diff's entity shape and order. There is no
    cause: a range has no single author.
    """

    base_commit_id: NotRequired[str | None]
    changes: list[EntityChangeOutput]
    from_commit_id: str
    next_page_token: NotRequired[str | None]
    to_commit_id: str


class ErrorOutput(TypedDict):
    blob_precondition_failure: NotRequired[BlobPreconditionFailureOutput | None]
    blob_range: NotRequired[BlobRangeOutput | None]
    branch_start_refusal: NotRequired[BranchStartRefusalOutput | None]
    change_diff_refusal: NotRequired[ChangeDiffRefusalOutput | None]
    change_feed_gap: NotRequired[ChangeFeedGapOutput | None]
    code: ErrorCode
    diagnostic: NotRequired[DiagnosticOutput | None]
    disposition: DispositionOutput
    error: str
    external_blob_source: NotRequired[ExternalBlobSourceOutput | None]
    full_text_index_rebuild_required: NotRequired[
        FullTextIndexRebuildRequiredOutput | None
    ]
    full_text_index_required: NotRequired[FullTextIndexRequiredOutput | None]
    key_conflict: NotRequired[KeyConflictOutput | None]
    merge_conflicts: NotRequired[list[MergeConflictOutput]]
    precondition_failure: NotRequired[PreconditionFailureOutput | None]
    published_dataset_version_conflict: NotRequired[
        PublishedDatasetVersionConflictOutput | None
    ]
    read_set_conflict: NotRequired[ReadSetConflictOutput | None]
    recovery_required: NotRequired[RecoveryRequiredOutput | None]
    resource_limit: NotRequired[ResourceLimitOutput | None]


class LoadExecutedOutput(TypedDict):
    """
    What a `load csv` statement's plan measured as it ran, beside the
    statement's [`ChangeOutput`]: the source partitions and bytes it read, the
    count its sink staged, and what each operator did. Absent for an append
    or merge load, which the keyed adapters run, and for every other change.
    """

    operators: list[LoadOperatorExecutedOutput]
    partitions: int
    rows: int
    source_bytes: int


class QueriesCatalogOutput(TypedDict):
    """
    Response for `GET /queries`: every stored query in a graph's
    registry, each with typed parameters.
    """

    queries: list[QueryCatalogEntry]


class BranchMergeOutput(TypedDict):
    actor_id: NotRequired[str | None]
    branch_delete_error_details: NotRequired[ErrorOutput | None]
    branch_deleted: NotRequired[bool | None]
    commit: CommitOutput | None
    dry_run: NotRequired[bool]
    outcome: BranchMergeOutcome
    source: str
    target: str


class ChangeOutput(TypedDict):
    actor_id: NotRequired[str | None]
    affected_edges: int
    affected_nodes: int
    branch: str
    commit: CommitOutput | None
    executed: NotRequired[LoadExecutedOutput | None]
    outcome: NotRequired[BranchOutcomeOutput | None]
    query_name: str


InvokeStoredQueryOutput = ReadOutput | ChangeOutput
