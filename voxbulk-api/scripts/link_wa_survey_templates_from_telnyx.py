#!/usr/bin/env python3
"""Link local survey WA template rows to existing Telnyx/Meta templates by name."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_utility_rewrite_service import _find_template_row
from app.services.survey_whatsapp_template_service import (
    SYNC_IN_SYNC,
    SurveyWhatsappTemplateService,
    _resolve_push_language,
    _try_link_existing_remote_template,
)
from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService


def _failed_names_from_report(phase: int) -> list[str]:
    reports = sorted((ROOT / "seed-data" / "wa-survey" / "migration-reports").glob(f"migration-phase{phase}-*.json"))
    if not reports:
        raise SystemExit(f"No migration-phase{phase}-*.json report found")
    payload = json.loads(reports[-1].read_text(encoding="utf-8"))
    report = payload.get("report") or {}
    return [
        str(r.get("template_name") or "").strip()
        for r in (report.get("results") or [])
        if not r.get("ok")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Link survey templates to existing Telnyx/Meta rows")
    parser.add_argument("--from-report-phase", type=int, choices=[1, 2, 3, 4])
    parser.add_argument("--template-name", action="append", default=[])
    args = parser.parse_args()

    names = [n.strip() for n in args.template_name if str(n or "").strip()]
    if args.from_report_phase:
        names.extend(_failed_names_from_report(args.from_report_phase))
    names = list(dict.fromkeys(names))
    if not names:
        parser.error("Provide --template-name and/or --from-report-phase")

    ok = 0
    fail = 0
    with get_sessionmaker()() as db:
        waba_items = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(db, filter_waba_id=True)
        all_items = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(db, filter_waba_id=False)
        for name in names:
            row = _find_template_row(db, name)
            if row is None:
                print(f"MISS {name}: not in DB")
                fail += 1
                continue
            lang, lang_error = _resolve_push_language(db, row)
            if lang_error:
                print(f"FAIL {name}: {lang_error}")
                fail += 1
                continue
            result = _try_link_existing_remote_template(db, row, language=lang, remote_items=waba_items)
            if result is None:
                result = _try_link_existing_remote_template(db, row, language=lang, remote_items=all_items)
            if result is None:
                print(f"FAIL {name}: not found on Telnyx/Meta")
                fail += 1
                continue
            row.last_push_error = None
            row.local_sync_status = SYNC_IN_SYNC
            db.add(row)
            db.commit()
            db.refresh(row)
            SurveyWhatsappTemplateService.refresh_telnyx_status(db, row)
            print(f"OK  {name}: linked status={row.status}")
            ok += 1

    print(f"Done: {ok} linked, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
