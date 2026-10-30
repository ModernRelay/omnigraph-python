"""HTTP transport: contract header, discovery, graph scoping, error mapping.

Mirrors `transport.ts` in `@modernrelay/omnigraph` 0.14. No request is ever
retried and no redirect is followed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from ._errors import (
    ApiContractError,
    ConfigurationError,
    NetworkError,
    OmnigraphError,
    error_body,
    from_response,
)
from ._version import HTTP_API_CONTRACT, HTTP_API_CONTRACT_HEADER

#: Public probes and metadata never receive the bearer credential.
_PUBLIC_PATHS = frozenset(
    {"/healthz", "/readyz", "/.well-known/oauth-protected-resource"}
)
_OAUTH_PREFIX = "/.well-known/oauth-protected-resource"
#: POST routes that only read.
_READ_ONLY_POSTS = frozenset(
    {"/query", "/export", "/changes/baseline", "/cluster/plan"}
)
_DISCOVERY_TIMEOUT = 5.0

Query = Mapping[str, str | Sequence[str] | None]


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith(_OAUTH_PREFIX + "/")


def _is_root(path: str) -> bool:
    return (
        _is_public(path)
        or path in ("/graphs", "/graphs/discovery")
        or path.startswith("/cluster/")
    )


def may_write(method: str, path: str) -> bool:
    return method not in ("GET", "HEAD") and path not in _READ_ONLY_POSTS


class Transport:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None,
        graph_id: str | None,
        client: httpx.AsyncClient,
        owns_client: bool,
    ) -> None:
        root = httpx.URL(base_url)
        if (
            root.scheme not in ("http", "https")
            or not root.host
            or root.userinfo
            or root.query
            or root.fragment
        ):
            raise ConfigurationError(
                "base_url must be an HTTP(S) server root without credentials, "
                "query, or fragment",
                method="HEAD",
                url="<invalid-server-root>",
            )
        self.base_url = str(root).rstrip("/")
        self.graph_id = graph_id
        self._token = token
        self._client = client
        self._owns_client = owns_client

    def scoped(self, graph_id: str) -> Transport:
        """A transport for another graph on the same server, sharing this one's
        connection pool. Closing it does not close the pool."""
        return Transport(
            self.base_url,
            token=self._token,
            graph_id=graph_id,
            client=self._client,
            owns_client=False,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def url(self, path: str) -> str:
        if not path.startswith("/"):
            raise ValueError(f"transport path must start with '/': {path!r}")
        if self.graph_id is not None and not _is_root(path):
            path = f"/graphs/{quote(self.graph_id, safe='')}{path}"
        return self.base_url + path

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        query: Query | None = None,
        headers: Mapping[str, str] | None = None,
        if_actor: str | None = None,
        accepted_statuses: Sequence[int] = (),
    ) -> Any:
        """Send one request and return its parsed JSON body. A missing or
        invalid body never acknowledges a write."""
        response = await self.send(
            method,
            path,
            body=body,
            query=query,
            headers=headers,
            if_actor=if_actor,
            accepted_statuses=accepted_statuses,
        )
        try:
            if not response.content:
                raise ValueError("missing JSON response body")
            return json.loads(response.content)
        except ValueError:
            raise NetworkError(
                "response body was interrupted or invalid; "
                "do not automatically repeat writes",
                status=response.status_code,
                method=method,
                url=self.url(path),
                response=response,
                request_dispatched=True,
                outcome_unknown=may_write(method, path),
            ) from None

    async def send(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        query: Query | None = None,
        headers: Mapping[str, str] | None = None,
        if_actor: str | None = None,
        accepted_statuses: Sequence[int] = (),
    ) -> httpx.Response:
        if self.graph_id is None and not _is_root(path):
            raise ConfigurationError(
                f"graph_id is required for graph-scoped operations (attempted "
                f"{method} {path}). Pass graph_id= to Omnigraph(...) or use "
                f"client.graph(id).",
                method=method,
                url=self.base_url + path,
            )
        url = self.url(path)
        if not _is_public(path):
            await self._discover()
        sent: dict[str, str] = dict(headers or {})
        sent[HTTP_API_CONTRACT_HEADER] = HTTP_API_CONTRACT
        if not _is_public(path):
            if if_actor is not None:
                sent["Omnigraph-If-Actor"] = if_actor
            if self._token:
                sent["Authorization"] = f"Bearer {self._token}"
        sent.setdefault("Accept", "application/json, application/x-ndjson")
        content: bytes | None = None
        if body is not None:
            content = json.dumps(body).encode()
            sent.setdefault("Content-Type", "application/json")
        params = {k: v for k, v in (query or {}).items() if v is not None}
        writes = may_write(method, path)
        try:
            response = await self._client.request(
                method, url, content=content, headers=sent, params=params
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise NetworkError(
                f"could not connect to the server: {e}",
                method=method,
                url=url,
            ) from e
        except httpx.TransportError as e:
            raise NetworkError(
                "HTTP transport failed after dispatch; reconcile writes before retrying",
                method=method,
                url=url,
                request_dispatched=True,
                outcome_unknown=writes,
            ) from e
        if not path.startswith(_OAUTH_PREFIX) and response.headers.get_list(
            HTTP_API_CONTRACT_HEADER
        ) != [HTTP_API_CONTRACT]:
            raise ApiContractError(
                f"response must carry exactly one {HTTP_API_CONTRACT_HEADER}: "
                f"{HTTP_API_CONTRACT}; reconcile writes before retrying",
                status=response.status_code,
                method=method,
                url=url,
                code="api_contract_mismatch",
                response=response,
                request_dispatched=True,
                outcome_unknown=writes,
            )
        if not response.is_success and response.status_code not in accepted_statuses:
            try:
                parsed: Any = json.loads(response.content)
            except ValueError:
                # A status alone does not prove a write failed when its
                # response is truncated or malformed.
                parsed = None
            raise from_response(
                response, error_body(parsed), method=method, url=url, may_write=writes
            )
        return response

    def invalid_response(
        self, method: str, path: str, message: str, status: int = 200
    ) -> ApiContractError:
        return ApiContractError(
            f"{message}; effects are unknown; reconcile before retrying",
            status=status,
            method=method,
            url=self.url(path),
            request_dispatched=True,
            outcome_unknown=may_write(method, path),
        )

    async def _discover(self) -> None:
        url = self.base_url + "/healthz"
        try:
            response = await self._client.head(
                url,
                headers={HTTP_API_CONTRACT_HEADER: HTTP_API_CONTRACT},
                timeout=_DISCOVERY_TIMEOUT,
            )
            ok = response.is_success and response.headers.get_list(
                HTTP_API_CONTRACT_HEADER
            ) == [HTTP_API_CONTRACT]
            status = response.status_code
        except (httpx.HTTPError, OmnigraphError):
            ok, status = False, 0
        if not ok:
            raise ApiContractError(
                f"server discovery failed (connection, TLS, status, or API "
                f"contract); expected {HTTP_API_CONTRACT_HEADER}: "
                f"{HTTP_API_CONTRACT}; the data request was not sent",
                status=status,
                method="HEAD",
                url=url,
                code="api_contract_mismatch",
            )
