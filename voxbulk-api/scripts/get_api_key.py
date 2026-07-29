#!/usr/bin/env python3
"""NEVER run in production.

Local debug helper: prints a Telnyx API key *fingerprint* from sqlite ``dev.db``.
Does not print the full secret. Prefer Admin → Integrations for real credentials.
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path


def _fingerprint(api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
    tail = api_key[-4:] if len(api_key) >= 4 else "????"
    return f"sha256:{digest}…{tail}"


def main() -> int:
    db_path = Path(__file__).resolve().parents[1] / "dev.db"
    if not db_path.is_file():
        print(f"No local sqlite db at {db_path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(db_path))
    try:
        result = conn.execute(
            'SELECT value FROM settings WHERE key="telnyx_api_key" LIMIT 1'
        ).fetchone()
    finally:
        conn.close()
    if not result or not result[0]:
        print("No Telnyx API key found")
        return 1
    print(f"Telnyx API key fingerprint: {_fingerprint(str(result[0]))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
