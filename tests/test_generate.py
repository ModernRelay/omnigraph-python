"""The generator reads the HTTP contract from the spec, not the release number."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate


def _op(*values: str) -> dict[str, Any]:
    return {
        "parameters": [
            {"name": "graph_id", "in": "path", "schema": {"type": "string"}},
            {
                "name": "Omnigraph-Http-Api",
                "in": "header",
                "schema": {"type": "string", "enum": list(values)},
            },
        ]
    }


def test_contract_is_the_header_enum_not_the_release() -> None:
    spec = {
        "info": {"version": "0.16.0"},
        "paths": {"/a": {"get": _op("0.14")}, "/b": {"post": _op("0.14")}},
    }
    assert generate.http_api_contract(spec) == "0.14"


@pytest.mark.parametrize(
    "paths",
    [
        {"/a": {"get": _op("0.14")}, "/b": {"get": _op("0.15")}},
        {"/a": {"get": _op("0.14", "0.15")}},
        {"/a": {"get": {"parameters": []}}},
    ],
)
def test_contract_must_be_one_value(paths: dict[str, Any]) -> None:
    with pytest.raises(SystemExit):
        generate.http_api_contract({"paths": paths})


def test_pinned_spec_contract_matches_generated_version() -> None:
    from omnigraph import HTTP_API_CONTRACT

    spec = json.loads(generate.SPEC.read_text())
    assert generate.http_api_contract(spec) == HTTP_API_CONTRACT
