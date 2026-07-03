#!/usr/bin/env python3
"""Live DB progress for a WA UTILITY migration phase (works while migrate script runs)."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_utility_rewrite_service import _already_submitted_utility_migration
from scripts.migrate_wa_templates_utility import MIGRATION_PHASES


def _survey_names_for_phase(db, phase: int) -> list[str]:
    cfg = MIGRATION_PHASES[phase - 1]
    if cfg["kind"] != "survey":
        raise SystemExit(f"Phase {phase} is not a survey phase")
    names: list[str] = []
    for slug in cfg["industries"]:
        industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
        if industry is None:
            continue
        type_ids = list(db.scalars(select(SurveyType.id).where(SurveyType.industry_id == industry.id)))
        if not type_ids:
            continue
        rows = db.execute(
            select(TelnyxWhatsappTemplate.name, TelnyxWhatsappTemplate.updated_at)
            .where(
                TelnyxWhatsappTemplate.survey_type_id.in_(type_ids),
                TelnyxWhatsappTemplate.step_role == "abc_choice",
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
            .order_by(TelnyxWhatsappTemplate.name)
        ).all()
        names.extend(str(name) for name, _ in rows if name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch WA migration phase progress via DB")
    parser.add_argument("--phase", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    print(f"Watching phase {args.phase} (Ctrl+C to stop). Refresh every {args.interval}s.\n")
    last_line = ""
    while True:
        with get_sessionmaker()() as db:
            names = _survey_names_for_phase(db, args.phase)
            rows = list(
                db.execute(select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name.in_(names))).scalars()
            )
            total = len(names)
            utility = sum(1 for r in rows if str(r.category or "").upper() == "UTILITY")
            on_meta = sum(1 for r in rows if _already_submitted_utility_migration(r))
            errors = sum(1 for r in rows if str(r.last_push_error or "").strip())
            latest = max((r.updated_at for r in rows if r.updated_at), default=None)
            latest_name = None
            if latest:
                for r in rows:
                    if r.updated_at == latest:
                        latest_name = r.name
                        break

        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = (
            f"[{ts}] phase {args.phase}: {on_meta}/{total} on Meta | "
            f"{utility}/{total} UTILITY in DB | errors={errors} | last={latest_name or '—'}"
        )
        if line != last_line:
            print(line, flush=True)
            last_line = line
        time.sleep(max(1.0, float(args.interval)))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped watching.")
        raise SystemExit(0)
