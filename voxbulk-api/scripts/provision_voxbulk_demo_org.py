#!/usr/bin/env python3
"""Ensure the shared AI Demo org 'Voxbulk Demo' exists with logo + seed data.

Usage (from voxbulk-api, project venv):
  python -m scripts.provision_voxbulk_demo_org
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.ai_demo_org_service import AiDemoOrgService


def main() -> None:
    Session = get_sessionmaker()
    db = Session()
    try:
        result = AiDemoOrgService.ensure_demo_org(db)
        print(json.dumps(result, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
