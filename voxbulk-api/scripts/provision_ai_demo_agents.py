#!/usr/bin/env python3
"""Duplicate mapped AI Demo region agents into dedicated Telnyx + Admin Agents.

Does NOT mutate interview assistants — creates new Telnyx assistants and remaps
demo_platform_settings.agent_by_region_json.

Usage (from voxbulk-api):
  PYTHONPATH=. .venv/bin/python scripts/provision_ai_demo_agents.py --dry-run
  PYTHONPATH=. .venv/bin/python scripts/provision_ai_demo_agents.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.ai_demo_service import AiDemoError, AiDemoService


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision dedicated AI Demo Telnyx agents")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    db = get_sessionmaker()()
    try:
        kb = AiDemoService.upsert_knowledge_bases(db)
        print("KB upsert:", json.dumps(kb))
        out = AiDemoService.duplicate_region_agents_for_demo(db, dry_run=args.dry_run)
        print(json.dumps(out, indent=2, default=str))
        return 0
    except AiDemoError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
