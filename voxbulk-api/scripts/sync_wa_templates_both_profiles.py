#!/usr/bin/env python3
"""Push local DB WhatsApp templates to primary (Meta default) and Telnyx backup.

No renames — uses existing DB names (was_*, cfs_*, system names).

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/sync_wa_templates_both_profiles.py --dry-run
  python scripts/sync_wa_templates_both_profiles.py --scope customer_feedback
  python scripts/sync_wa_templates_both_profiles.py --scope survey --batch-size 10
  python scripts/sync_wa_templates_both_profiles.py --scope all --batch-size 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.feedback_telnyx_push_service import push_feedback_platform_batch
from app.services.wa_template_profile_push_service import WaTemplateProfilePushService
from app.services.wa_template_sync_service import WaTemplateSyncService
from app.services.wa_template_utility_content import NO_BUTTON_KINDS

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"


def _collect_system_buttoned_survey_rows(db) -> list[TelnyxWhatsappTemplate]:
    system_type_ids = {
        str(row.id)
        for row in db.execute(
            select(SurveyType).where(SurveyType.system_template_kind.is_not(None))
        ).scalars()
    }
    if not system_type_ids:
        return []
    rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
    out: list[TelnyxWhatsappTemplate] = []
    for row in rows:
        st_id = str(getattr(row, "survey_type_id", None) or "")
        if st_id not in system_type_ids:
            continue
        st = db.get(SurveyType, st_id)
        kind = str(getattr(st, "system_template_kind", None) or "").strip().lower()
        if kind in NO_BUTTON_KINDS:
            continue
        if not str(row.draft_components_json or "").strip():
            continue
        out.append(row)
    out.sort(key=lambda r: str(r.name or r.id))
    return out


def _push_survey_scope(db, *, batch_size: int, dry_run: bool, primary_id: str, backup_id: str) -> dict:
    work = WaTemplateSyncService.collect_survey_mirror_templates(db)
    pushed = 0
    errors: list[dict] = []
    for row in work:
        result = WaTemplateProfilePushService.push_template_to_both_profiles(
            db,
            survey_row=row,
            service_code="survey",
            primary_profile_id=primary_id,
            backup_profile_id=backup_id,
            dry_run=dry_run,
        )
        if result.get("ok"):
            pushed += 1
        else:
            errors.extend(result.get("errors") or [{"template": row.name, "error": result.get("error")}])
        if not dry_run:
            time.sleep(0.5)
    return {"scope": "survey", "total": len(work), "pushed_ok": pushed, "error_count": len(errors), "errors": errors[:50]}


def _push_system_buttoned_scope(db, *, dry_run: bool, primary_id: str, backup_id: str) -> dict:
    work = _collect_system_buttoned_survey_rows(db)
    pushed = 0
    errors: list[dict] = []
    for row in work:
        result = WaTemplateProfilePushService.push_template_to_both_profiles(
            db,
            survey_row=row,
            service_code="survey",
            primary_profile_id=primary_id,
            backup_profile_id=backup_id,
            dry_run=dry_run,
        )
        if result.get("ok"):
            pushed += 1
        else:
            errors.extend(result.get("errors") or [{"template": row.name, "error": result.get("error")}])
        if not dry_run:
            time.sleep(0.5)
    return {
        "scope": "system_buttoned",
        "total": len(work),
        "pushed_ok": pushed,
        "error_count": len(errors),
        "errors": errors[:50],
    }


def _push_feedback_scope(db, *, batch_size: int, dry_run: bool, primary_id: str, backup_id: str) -> dict:
    if dry_run:
        total = db.execute(select(FeedbackWaTemplate)).scalars().all()
        return {
            "scope": "customer_feedback",
            "total": len(list(total)),
            "pushed_ok": len(list(total)),
            "dry_run": True,
            "message": "Dry run — counted feedback rows only",
        }

    primary_errors: list[dict] = []
    backup_errors: list[dict] = []
    offset = 0
    primary_batches = 0
    while True:
        summary = push_feedback_platform_batch(
            db,
            offset=offset,
            limit=batch_size,
            force_push=True,
            connection_profile_id=primary_id,
            service_code="customer_feedback",
        )
        primary_batches += 1
        primary_errors.extend(summary.get("errors") or [])
        if not summary.get("has_more"):
            break
        offset = int(summary.get("next_offset") or 0)

    offset = 0
    backup_batches = 0
    while True:
        summary = push_feedback_platform_batch(
            db,
            offset=offset,
            limit=batch_size,
            force_push=True,
            connection_profile_id=backup_id,
            service_code="customer_feedback",
        )
        backup_batches += 1
        backup_errors.extend(summary.get("errors") or [])
        if not summary.get("has_more"):
            break
        offset = int(summary.get("next_offset") or 0)

    return {
        "scope": "customer_feedback",
        "primary_batches": primary_batches,
        "backup_batches": backup_batches,
        "error_count": len(primary_errors) + len(backup_errors),
        "errors": (primary_errors + backup_errors)[:50],
        "ok": not primary_errors and not backup_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync WA templates to Meta primary + Telnyx backup")
    parser.add_argument(
        "--scope",
        choices=("all", "survey", "customer_feedback", "system_buttoned"),
        default="all",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Print full report JSON")
    args = parser.parse_args()

    report: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": bool(args.dry_run),
        "scope": args.scope,
        "sections": [],
    }

    with get_sessionmaker()() as db:
        primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code="survey")
        backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(db, service_code="survey")
        cf_primary = WaTemplateProfilePushService.resolve_primary_connection_profile_id(
            db, service_code="customer_feedback"
        )
        cf_backup = WaTemplateProfilePushService.resolve_backup_connection_profile_id(
            db, service_code="customer_feedback"
        )
        report["profiles"] = {
            "survey_primary": primary_id,
            "survey_backup": backup_id,
            "feedback_primary": cf_primary or primary_id,
            "feedback_backup": cf_backup or backup_id,
        }

        if args.scope in ("all", "survey"):
            if not primary_id or not backup_id:
                print("ERROR: survey primary/backup profiles not configured", file=sys.stderr)
                return 1
            report["sections"].append(
                _push_survey_scope(
                    db,
                    batch_size=max(1, args.batch_size),
                    dry_run=bool(args.dry_run),
                    primary_id=primary_id,
                    backup_id=backup_id,
                )
            )

        if args.scope in ("all", "system_buttoned"):
            if not primary_id or not backup_id:
                print("ERROR: survey primary/backup profiles not configured", file=sys.stderr)
                return 1
            report["sections"].append(
                _push_system_buttoned_scope(
                    db,
                    dry_run=bool(args.dry_run),
                    primary_id=primary_id,
                    backup_id=backup_id,
                )
            )

        if args.scope in ("all", "customer_feedback"):
            p_id = cf_primary or primary_id
            b_id = cf_backup or backup_id
            if not p_id or not b_id:
                print("ERROR: customer feedback primary/backup profiles not configured", file=sys.stderr)
                return 1
            report["sections"].append(
                _push_feedback_scope(
                    db,
                    batch_size=max(1, min(args.batch_size, 50)),
                    dry_run=bool(args.dry_run),
                    primary_id=p_id,
                    backup_id=b_id,
                )
            )

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["ok"] = all(section.get("error_count", 0) == 0 for section in report["sections"])

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = REPORT_DIR / f"dual-profile-sync-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Report: {out_path}")
        for section in report["sections"]:
            print(
                f"  {section.get('scope')}: total={section.get('total', 'n/a')} "
                f"errors={section.get('error_count', 0)}"
            )
        print(f"OK: {report['ok']}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
