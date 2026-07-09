#!/usr/bin/env python3
"""Bump interview WA template version suffix, rename in-place (same row id), dual-profile push.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python scripts/rename_and_push_interview_wa_templates.py --dry-run
  python scripts/rename_and_push_interview_wa_templates.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.data.interview_whatsapp_template_catalog import INTERVIEW_WA_TEMPLATE_KEYS
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.interview_whatsapp_template_service import InterviewWhatsappTemplateService
from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

_VERSION_RE = re.compile(r"_v(\d+)$", re.I)


def bump_template_version(current_name: str) -> str:
    clean = str(current_name or "").strip().lower()
    m = _VERSION_RE.search(clean)
    if m:
        n = int(m.group(1)) + 1
        return _VERSION_RE.sub(f"_v{n}", clean)
    return f"{clean}_v2"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename + push interview WA templates")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": bool(args.dry_run),
        "renames": [],
        "pushes": [],
        "ok": True,
    }

    with get_sessionmaker()() as db:
        primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(
            db, service_code="ai_interview"
        ) or WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code="survey")
        backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(
            db, service_code="ai_interview"
        ) or WaTemplateProfilePushService.resolve_backup_connection_profile_id(db, service_code="survey")
        report["profiles"] = {"primary": primary_id, "backup": backup_id}

        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.sales_template_key.in_(list(INTERVIEW_WA_TEMPLATE_KEYS))
                )
            ).scalars().all()
        )
        rows.sort(key=lambda r: str(r.sales_template_key or ""))

        for row in rows:
            old_name = str(row.name or "").strip()
            new_name = bump_template_version(old_name)
            entry = {
                "id": row.id,
                "sales_template_key": row.sales_template_key,
                "old_name": old_name,
                "new_name": new_name,
            }
            if old_name.lower() == new_name.lower():
                entry["skipped"] = "already at target name"
                report["renames"].append(entry)
                continue
            if args.dry_run:
                entry["dry_run"] = True
                report["renames"].append(entry)
                continue
            try:
                InterviewWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
                db.refresh(row)
                entry["renamed"] = True
            except Exception as exc:  # noqa: BLE001
                entry["error"] = str(exc)
                report["ok"] = False
            report["renames"].append(entry)

        if not args.dry_run:
            db.commit()
            rows = list(
                db.execute(
                    select(TelnyxWhatsappTemplate).where(
                        TelnyxWhatsappTemplate.sales_template_key.in_(list(INTERVIEW_WA_TEMPLATE_KEYS))
                    )
                ).scalars().all()
            )

        if not primary_id or not backup_id:
            report["ok"] = False
            report["error"] = "Missing primary or backup connection profile"
            print(json.dumps(report, indent=2) if args.json else report)
            return 1

        for row in rows:
            push_entry = {
                "id": row.id,
                "sales_template_key": row.sales_template_key,
                "name": row.name,
            }
            if args.dry_run:
                push_entry["dry_run"] = True
                report["pushes"].append(push_entry)
                continue
            result = WaTemplateProfilePushService.push_template_to_both_profiles(
                db,
                survey_row=row,
                service_code="ai_interview",
                primary_profile_id=primary_id,
                backup_profile_id=backup_id,
                dry_run=False,
            )
            push_entry["result"] = result
            if not result.get("ok"):
                report["ok"] = False
            report["pushes"].append(push_entry)
            time.sleep(0.5)

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for r in report["renames"]:
            print(f"RENAME {r.get('sales_template_key')}: {r.get('old_name')} -> {r.get('new_name')} {r.get('error','')}")
        for p in report["pushes"]:
            name = p.get("name")
            ok = (p.get("result") or {}).get("ok", p.get("dry_run"))
            print(f"PUSH {p.get('sales_template_key')} ({name}): {ok}")
        print("OK" if report["ok"] else "FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
