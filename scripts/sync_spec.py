"""Replace spec/openapi.json with the one from the pinned server release.

uv run python scripts/sync_spec.py
"""

from __future__ import annotations

import sys
import urllib.request

from generate import SPEC, server_version


def main() -> None:
    tag = f"v{server_version()}"
    url = f"https://raw.githubusercontent.com/ModernRelay/omnigraph/{tag}/openapi.json"
    with urllib.request.urlopen(url, timeout=60) as resp:
        SPEC.write_bytes(resp.read())
    print(f"spec/openapi.json <- {url}", file=sys.stderr)


if __name__ == "__main__":
    main()
