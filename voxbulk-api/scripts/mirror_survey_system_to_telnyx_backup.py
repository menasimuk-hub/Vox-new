#!/usr/bin/env python3
"""Mirror survey + system-buttoned WA templates to Telnyx backup only (slow).

Does NOT force-push Meta primary. DB draft is source of truth.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python -u scripts/mirror_survey_system_to_telnyx_backup.py --scope both --dry-run
  python -u scripts/mirror_survey_system_to_telnyx_backup.py --scope both --delay-sec 25 --batch-size 5
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
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService
from app.services.wa_template_profile_push_service import WaTemplateProfilePushService
from app.services.wa_template_sync_service import WaTemplateSyncService
from app.services.wa_template_utility_content import NO_BUTTON_KINDS

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"


def _configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
        except Exception:
            pass


def _log(msg: str) -> None:
    print(msg, flush=True)


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


def _mirror_survey(*, dry_run: bool, delay_sec: float, batch_size: int, backup_id: str) -> dict:
    with get_sessionmaker()() as db:
        work = WaTemplateSyncService.collect_survey_mirror_templates(db)
        total = len(work)
        if dry_run:
            return {
                "scope": "survey",
                "dry_run": True,
                "total": total,
                "backup_profile_id": backup_id,
                "message": f"Dry run — would mirror {total} survey template(s) to Telnyx backup",
            }

        offset = 0
        batches = 0
        content_updated = 0
        errors: list[dict] = []
        while True:
            summary = WaTemplateSyncService.mirror_to_backup_profile(
                db,
                offset=offset,
                limit=batch_size,
                connection_profile_id=backup_id,
                service_code="survey",
            )
            batches += 1
            content_updated += int(summary.get("content_updated") or 0)
            batch_errors = summary.get("errors") or []
            errors.extend(batch_errors)
            _log(
                f"  survey batch#{batches} offset={offset} "
                f"updated={summary.get('content_updated')} errors={summary.get('error_count')} "
                f"has_more={summary.get('has_more')}"
            )
            for err in batch_errors[:3]:
                _log(
                    f"    ERR {err.get('template') or err.get('label') or '?'}: "
                    f"{err.get('error') or err}"
                )
            if not summary.get("has_more"):
                break
            offset = int(summary.get("next_offset") or (offset + batch_size))
            if delay_sec > 0:
                time.sleep(delay_sec)

        return {
            "scope": "survey",
            "total": total,
            "batches": batches,
            "content_updated": content_updated,
            "error_count": len(errors),
            "errors": errors[:50],
            "backup_profile_id": backup_id,
            "ok": not errors,
        }


def _mirror_system(*, dry_run: bool, delay_sec: float, backup_id: str) -> dict:
    with get_sessionmaker()() as db:
        work = _collect_system_buttoned_survey_rows(db)
        total = len(work)
        if dry_run:
            return {
                "scope": "system_buttoned",
                "dry_run": True,
                "total": total,
                "backup_profile_id": backup_id,
                "message": f"Dry run — would push {total} system-buttoned template(s) to Telnyx backup",
            }

        pushed_ok = 0
        errors: list[dict] = []
        for idx, row in enumerate(work, start=1):
            name = str(row.name or row.id)
            try:
                result = SurveyWhatsappTemplateService.push_to_telnyx(
                    db,
                    row,
                    force_approved_update=True,
                    connection_profile_id=backup_id,
                    service_code="survey",
                )
                if result.get("ok") is False or result.get("error"):
                    err = str(result.get("error") or "push failed")
                    errors.append({"template": name, "error": err})
                    _log(f"  system [{idx}/{total}] FAIL {name}: {err}")
                else:
                    pushed_ok += 1
                    _log(f"  system [{idx}/{total}] OK {name}")
            except Exception as exc:  # noqa: BLE001 — keep job running
                errors.append({"template": name, "error": str(exc)})
                _log(f"  system [{idx}/{total}] FAIL {name}: {exc}")
            if delay_sec > 0 and idx < total:
                time.sleep(delay_sec)

        return {
            "scope": "system_buttoned",
            "total": total,
            "pushed_ok": pushed_ok,
            "error_count": len(errors),
            "errors": errors[:50],
            "backup_profile_id": backup_id,
            "ok": not errors,
        }


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="Mirror survey/system WA templates to Telnyx backup only (slow, Meta-safe)"
    )
    parser.add_argument(
        "--scope",
        choices=("survey", "system_buttoned", "both"),
        default="both",
    )
    parser.add_argument("--delay-sec", type=float, default=25.0, help="Pause between batches/rows (default 25)")
    parser.add_argument("--batch-size", type=int, default=5, help="Survey batch size (default 5)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": bool(args.dry_run),
        "scope": args.scope,
        "delay_sec": float(args.delay_sec),
        "batch_size": max(1, int(args.batch_size)),
        "sections": [],
    }

    with get_sessionmaker()() as db:
        backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(
            db, service_code="survey"
        )
    if not backup_id:
        _log("ERROR: survey Telnyx backup profile not configured")
        return 1

    report["backup_profile_id"] = backup_id
    _log(f"Telnyx backup profile: {backup_id}")
    _log(f"Scope={args.scope} delay={args.delay_sec}s batch={args.batch_size} dry_run={args.dry_run}")

    if args.scope in ("survey", "both"):
        _log("--- survey → Telnyx backup ---")
        report["sections"].append(
            _mirror_survey(
                dry_run=bool(args.dry_run),
                delay_sec=max(0.0, float(args.delay_sec)),
                batch_size=max(1, int(args.batch_size)),
                backup_id=backup_id,
            )
        )

    if args.scope in ("system_buttoned", "both"):
        _log("--- system_buttoned → Telnyx backup ---")
        report["sections"].append(
            _mirror_system(
                dry_run=bool(args.dry_run),
                delay_sec=max(0.0, float(args.delay_sec)),
                backup_id=backup_id,
            )
        )

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["ok"] = all(
        section.get("ok", True) and int(section.get("error_count") or 0) == 0
        for section in report["sections"]
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = REPORT_DIR / f"telnyx-backup-mirror-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _log(f"Report: {out_path}")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for section in report["sections"]:
            _log(
                f"  {section.get('scope')}: total={section.get('total', 'n/a')} "
                f"errors={section.get('error_count', 0)}"
            )
        _log(f"OK: {report['ok']}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
