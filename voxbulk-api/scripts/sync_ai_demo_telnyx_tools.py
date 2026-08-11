#!/usr/bin/env python3
"""Sync AI Demo webhook tools onto all dedicated AI Demo Telnyx assistants.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/sync_ai_demo_telnyx_tools.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.ai_demo_telnyx_tools import sync_tools_for_all_ai_demo_agents


def main() -> int:
    db = get_sessionmaker()()
    try:
        out = sync_tools_for_all_ai_demo_agents(db)
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("ok") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
