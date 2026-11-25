"""Typed errors. Catch the class you care about; every class carries the
server's `disposition` when the server sent one."""

from __future__ import annotations

from typing import Any, cast

import httpx

from ._models import (
    BlobRangeOutput,
    ChangeDiffRefusalOutput,
    ChangeFeedGapOutput,
    DispositionOutput,
    ErrorCode,
    ErrorOutput,
    ExternalBlobSourceOutput,
    FullTextIndexRebuildRequiredOutput,
    KeyConflictOutput,
    MergeConflictOutput,
    PreconditionFailureOutput,
    PublishedDatasetVersionConflictOutput,
    ReadSetConflictOutput,
    RecoveryRequiredOutput,
    ResourceLimitOutput,
    WriterFencedOutput,
)


class OmnigraphError(Exception):
    """Base class. `status` is 0 when no HTTP response was received.

    `request_dispatched` says whether the request may have reached the
    server; `outcome_unknown` says a write may have taken effect, so the
    caller must reconcile before deciding to retry.
    """

    status: int
    code: ErrorCode | None
    request_id: str | None
    method: str
    url: str
    body: ErrorOutput | None
    request_dispatched: bool
    outcome_unknown: bool

    def __init__(
        self,
        message: str,
        *,
        status: int = 0,
        method: str,
        url: str,
        code: ErrorCode | None = None,
        request_id: str | None = None,
        body: ErrorOutput | None = None,
        response: httpx.Response | None = None,
        request_dispatched: bool = False,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.request_id = request_id
        self.method = method
        self.url = url
        self.body = body
        self.response = response
        self.request_dispatched = request_dispatched
        self.outcome_unknown = outcome_unknown

    @property
    def disposition(self) -> DispositionOutput | None:
        """What the server did and what to do next; absent after transport loss."""
        return self.body.get("disposition") if self.body else None

    @property
    def retry_after(self) -> str | None:
        """Server guidance for caller-bounded retries of refused requests."""
        return self.response.headers.get("Retry-After") if self.response else None

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(status={self.status}, code={self.code!r}, "
            f"message={self.message!r})"
        )


class BadRequestError(OmnigraphError):
    pass


class UnauthorizedError(OmnigraphError):
    pass


class ForbiddenError(OmnigraphError):
    pass


class NotAdmittedError(ForbiddenError):
    """The OIDC token is valid, but the server admits no principal for its
    subject (`not_admitted`). Signing in again cannot help; the server's
    operator must admit the identity."""


class NotFoundError(OmnigraphError):
    pass


class MethodNotAllowedError(OmnigraphError):
    pass


class RequestTimeoutError(OmnigraphError):
    pass


class UnsupportedMediaTypeError(OmnigraphError):
    pass


class ConflictError(OmnigraphError):
    @property
    def merge_conflicts(self) -> list[MergeConflictOutput]:
        return list(self.body.get("merge_conflicts") or []) if self.body else []

    @property
    def key_conflict(self) -> KeyConflictOutput | None:
        return self.body.get("key_conflict") if self.body else None

    @property
    def read_set_conflict(self) -> ReadSetConflictOutput | None:
        """A concurrent commit changed what this write read; read again first."""
        return self.body.get("read_set_conflict") if self.body else None

    @property
    def published_dataset_version_conflict(
        self,
    ) -> PublishedDatasetVersionConflictOutput | None:
        if not self.body:
            return None
        return self.body.get("published_dataset_version_conflict")

    @property
    def change_diff_refusal(self) -> ChangeDiffRefusalOutput | None:
        return self.body.get("change_diff_refusal") if self.body else None

    @property
    def full_text_index_rebuild_required(
        self,
    ) -> FullTextIndexRebuildRequiredOutput | None:
        """This conflict needs operator maintenance, not a retry."""
        if not self.body:
            return None
        return self.body.get("full_text_index_rebuild_required")


class WriterFencedError(ConflictError):
    """The branch's writer epoch refused this publish or claim
    (`writer_fenced`): another process claimed the branch. Nothing was
    written. `writer_fenced` names the epochs."""

    @property
    def writer_fenced(self) -> WriterFencedOutput | None:
        return self.body.get("writer_fenced") if self.body else None


class GoneError(OmnigraphError):
    """Retained change history is unavailable; recover through a baseline."""

    @property
    def change_feed_gap(self) -> ChangeFeedGapOutput | None:
        return self.body.get("change_feed_gap") if self.body else None


class PreconditionFailedError(OmnigraphError):
    """A stale graph-head precondition, an actor mismatch, or a failed Blob If-Match."""

    @property
    def precondition_failure(self) -> PreconditionFailureOutput | None:
        return self.body.get("precondition_failure") if self.body else None


class PayloadTooLargeError(OmnigraphError):
    @property
    def resource_limit(self) -> ResourceLimitOutput | None:
        return self.body.get("resource_limit") if self.body else None


class RangeNotSatisfiableError(OmnigraphError):
    @property
    def blob_range(self) -> BlobRangeOutput | None:
        return self.body.get("blob_range") if self.body else None


class FailedDependencyError(OmnigraphError):
    @property
    def external_blob_source(self) -> ExternalBlobSourceOutput | None:
        return self.body.get("external_blob_source") if self.body else None


class TooManyRequestsError(OmnigraphError):
    pass


class InternalServerError(OmnigraphError):
    pass


class ServiceUnavailableError(OmnigraphError):
    @property
    def recovery_required(self) -> RecoveryRequiredOutput | None:
        return self.body.get("recovery_required") if self.body else None


class GraphUnavailableError(ServiceUnavailableError):
    pass


class NetworkError(OmnigraphError):
    """The transport failed, or the response body was interrupted or invalid."""


class ApiContractError(OmnigraphError):
    """Discovery failed, or a response lacked the expected HTTP contract header."""


class ConfigurationError(OmnigraphError):
    """Invalid client configuration; no request was sent."""


_BY_STATUS: dict[int, type[OmnigraphError]] = {
    400: BadRequestError,
    401: UnauthorizedError,
    403: ForbiddenError,
    404: NotFoundError,
    405: MethodNotAllowedError,
    408: RequestTimeoutError,
    409: ConflictError,
    410: GoneError,
    412: PreconditionFailedError,
    413: PayloadTooLargeError,
    415: UnsupportedMediaTypeError,
    416: RangeNotSatisfiableError,
    424: FailedDependencyError,
    429: TooManyRequestsError,
    500: InternalServerError,
    503: ServiceUnavailableError,
}

_BY_CODE: dict[str, type[OmnigraphError]] = {
    "bad_request": BadRequestError,
    "api_contract_mismatch": ApiContractError,
    "service_unavailable": ServiceUnavailableError,
    "graph_unavailable": GraphUnavailableError,
    "unauthorized": UnauthorizedError,
    "forbidden": ForbiddenError,
    "not_admitted": NotAdmittedError,
    "not_found": NotFoundError,
    "method_not_allowed": MethodNotAllowedError,
    "conflict": ConflictError,
    "too_many_requests": TooManyRequestsError,
    "internal": InternalServerError,
    "actor_mismatch": PreconditionFailedError,
    "outcome_unknown": InternalServerError,
    "precondition_failed": PreconditionFailedError,
    "recovery_required": ServiceUnavailableError,
    "external_blob_source": FailedDependencyError,
    "change_feed_gap": GoneError,
    "request_timeout": RequestTimeoutError,
    "branch_start_refusal": ConflictError,
    "unattached_cannot_publish": ConflictError,
    "writer_fenced": WriterFencedError,
    "payload_too_large": PayloadTooLargeError,
    "unsupported_media_type": UnsupportedMediaTypeError,
    "range_not_satisfiable": RangeNotSatisfiableError,
    "cancelled": BadRequestError,
    "deadline_exceeded": BadRequestError,
    "result_too_large": PayloadTooLargeError,
}


def error_class(status: int, code: str | None) -> type[OmnigraphError]:
    """The status picks the class; a code's class replaces it when it refines
    it (a subclass, such as `GraphUnavailableError` for a 503 or
    `NotAdmittedError` for a 403). A code alone decides only when the status
    has no class of its own."""
    if code == "api_contract_mismatch":
        return ApiContractError
    by_status = _BY_STATUS.get(status)
    by_code = _BY_CODE.get(code) if code else None
    if by_status is None:
        return by_code or InternalServerError
    if by_code is not None and issubclass(by_code, by_status):
        return by_code
    return by_status


def error_body(parsed: Any) -> ErrorOutput | None:
    """The parsed body when it is the server's error envelope, else `None`."""
    if not isinstance(parsed, dict):
        return None
    disposition = parsed.get("disposition")
    if not (
        isinstance(parsed.get("error"), str)
        and isinstance(parsed.get("code"), str)
        and isinstance(disposition, dict)
        and isinstance(disposition.get("effects"), str)
        and isinstance(disposition.get("action"), str)
    ):
        return None
    return cast(ErrorOutput, parsed)


def server_outcome_unknown(parsed: Any) -> bool | None:
    """Whether an error reply says a write may have taken effect, on any
    route. Code `outcome_unknown` always does, whatever its disposition reads
    (a recorded-operation lookup can leave a settlement write in doubt), and
    a valid disposition otherwise decides. `None` when the reply says
    neither, so the route decides."""
    if isinstance(parsed, dict) and parsed.get("code") == "outcome_unknown":
        return True
    body = error_body(parsed)
    return None if body is None else body["disposition"]["effects"] != "none"


def from_response(
    response: httpx.Response,
    parsed: Any,
    *,
    method: str,
    url: str,
    may_write: bool,
) -> OmnigraphError:
    """The error for a non-success reply. `parsed` is its JSON, if any;
    `may_write` is the route's answer, used only when the reply does not say."""
    body = error_body(parsed)
    code = body["code"] if body else None
    cls = error_class(response.status_code, code)
    unknown = server_outcome_unknown(parsed)
    return cls(
        body["error"] if body else f"HTTP {response.status_code}",
        status=response.status_code,
        method=method,
        url=url,
        code=code,
        request_id=response.headers.get("X-Request-Id"),
        body=body,
        response=response,
        request_dispatched=True,
        outcome_unknown=may_write if unknown is None else unknown,
    )
