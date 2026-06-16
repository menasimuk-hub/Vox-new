#!/usr/bin/env python3
"""Deduplicate voxbulk-api/.env and drop template placeholder values.

When a Smart Agent template was appended to .env, duplicate keys like
DATABASE_URL=mysql+pymysql://USER:PASS@... can override real credentials.
The last duplicate in the file wins — placeholders at the bottom break login.

Usage:
  cd voxbulk-api
  python scripts/sanitize_production_env.py --check
  python scripts/sanitize_production_env.py --write
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

COMMENT_OR_BLANK = re.compile(r"^\s*(#|$)")
KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

PLACEHOLDER_MARKERS = (
    "CHANGE_ME",
    "://USER:",
    "://USER@",
    ":PASS@",
    "PASSWORD@",
    "your-bootstrap-token",
)

PREFERRED_PREFIXES: dict[str, tuple[str, ...]] = {
    "DATABASE_URL": ("mysql+pymysql://sql_voxbulk:",),
    "ABUU_DATABASE_URL": ("mysql+pymysql://sql_abuu:",),
}


def _is_placeholder(value: str) -> bool:
    upper = value.upper()
    return any(marker.upper() in upper for marker in PLACEHOLDER_MARKERS)


def _score_value(key: str, value: str) -> int:
    if _is_placeholder(value):
        return -100
    score = 0
    for prefix in PREFERRED_PREFIXES.get(key, ()):
        if value.startswith(prefix):
            score += 50
    if key.endswith("_URL") and value.startswith("mysql+pymysql://"):
        score += 10
    if key in {"JWT_SECRET_KEY", "ENCRYPTION_KEY"} and len(value) >= 16:
        score += 5
    return score


def dedupe_env(lines: list[str]) -> tuple[list[str], list[str]]:
    """Keep one assignment per key using the highest-scoring value; preserve comments/order."""
    best: dict[str, str] = {}
    warnings: list[str] = []

    for raw in lines:
        m = KEY_LINE.match(raw)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if key in best and best[key] != value:
            warnings.append(f"duplicate {key} (will keep best value)")
        prev_score = _score_value(key, best.get(key, ""))
        new_score = _score_value(key, value)
        if key not in best or new_score >= prev_score:
            best[key] = value

    out: list[str] = []
    emitted: set[str] = set()
    for raw in lines:
        m = KEY_LINE.match(raw)
        if not m:
            out.append(raw)
            continue
        key = m.group(1)
        if key in emitted:
            continue
        out.append(f"{key}={best[key]}")
        emitted.add(key)

    return out, warnings


def validate_keyed(keyed: dict[str, str]) -> list[str]:
    errors: list[str] = []
    db = keyed.get("DATABASE_URL", "")
    if not db:
        errors.append("DATABASE_URL missing")
    elif _is_placeholder(db) or ":USER:" in db.upper():
        errors.append("DATABASE_URL still contains placeholder USER/PASS — set real sql_voxbulk credentials")
    abuu = keyed.get("ABUU_DATABASE_URL", "")
    if abuu and (_is_placeholder(abuu) or ":PASS@" in abuu.upper()):
        errors.append("ABUU_DATABASE_URL still contains placeholder PASS")
    enc = keyed.get("ENCRYPTION_KEY", "")
    if enc and "CHANGE_ME" in enc:
        errors.append("ENCRYPTION_KEY still CHANGE_ME — restore production Fernet key")
    jwt = keyed.get("JWT_SECRET_KEY", "")
    if jwt and "CHANGE_ME" in jwt:
        errors.append("JWT_SECRET_KEY still CHANGE_ME — restore production value")
    return errors


def keyed_from_lines(lines: list[str]) -> dict[str, str]:
    keyed: dict[str, str] = {}
    for raw in lines:
        m = KEY_LINE.match(raw)
        if m:
            keyed[m.group(1)] = m.group(2)
    return keyed


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize duplicate/placeholder .env entries")
    parser.add_argument("--env", type=Path, default=ENV_PATH, help="Path to .env file")
    parser.add_argument("--check", action="store_true", help="Report issues only, do not write")
    parser.add_argument("--write", action="store_true", help="Write sanitized .env")
    args = parser.parse_args()

    env_path: Path = args.env
    if not env_path.is_file():
        print(f"Missing {env_path}", file=sys.stderr)
        return 1

    original = env_path.read_text(encoding="utf-8")
    lines = original.splitlines()
    new_lines, warnings = dedupe_env(lines)
    keyed = keyed_from_lines(new_lines)
    errors = validate_keyed(keyed)

    print(f"File: {env_path}")
    for w in warnings:
        print(f"  warn: {w}")
    for e in errors:
        print(f"  ERROR: {e}", file=sys.stderr)

    db = keyed.get("DATABASE_URL", "")
    if db:
        safe = db.split("@")[-1] if "@" in db else "(hidden)"
        print(f"  DATABASE_URL -> ...@{safe}")

    if errors:
        return 1

    if args.check and not args.write:
        if warnings:
            print("Fix recommended: run with --write after backup")
            return 1
        print("OK — no placeholder duplicates detected")
        return 0

    if args.write:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = env_path.parent / f"{env_path.name}.bak.{ts}"
        backup.write_text(original, encoding="utf-8")
        env_path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
        print(f"Wrote sanitized .env (backup: {backup.name})")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
