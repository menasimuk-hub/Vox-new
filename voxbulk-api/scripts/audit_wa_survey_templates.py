#!/usr/bin/env python3
"""Audit and repair all WA Survey WhatsApp templates — sync Telnyx, fix drafts, push, refresh status.

Checks every template linked to WA Survey survey types:
  1. Sync remote templates from Telnyx/Meta
  2. Repair invalid draft BODY examples
  3. Push local changes / first-time sync to Telnyx
  4. Refresh PENDING / APPROVED approval status from Telnyx

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/audit_wa_survey_templates.py
  python scripts/audit_wa_survey_templates.py --dry-run
  python scripts/audit_wa_survey_templates.py --industry-slug hospitality_food
  python scripts/audit_wa_survey_templates.py --push-only
  python scripts/audit_wa_survey_templates.py --skip-sync
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import (
    SYNC_DRAFT,
    SYNC_ERROR,
    SYNC_LOCAL_CHANGES,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _dumps,
    _example_values_for_storage,
    _loads,
    _normalize_draft_components,
    _refresh_local_sync_status,
    telnyx_sync_ui_label,
)

repair_mod = importlib.util.spec_from_file_location(
    "repair_wa_survey_template_drafts",
    ROOT / "scripts" / "repair_wa_survey_template_drafts.py",
)
if repair_mod is None or repair_mod.loader is None:
    raise SystemExit("Could not load repair_wa_survey_template_drafts.py")
repair = importlib.util.module_from_spec(repair_mod)
repair_mod.loader.exec_module(repair)
_body_example_invalid = repair._body_example_invalid
_reset_draft_from_remote = repair._reset_draft_from_remote


def _iter_survey_templates(db, *, industry_slug: str | None = None) -> list[TelnyxWhatsappTemplate]:
    stmt = (
        select(TelnyxWhatsappTemplate)
        .where(TelnyxWhatsappTemplate.survey_type_id.isnot(None))
        .order_by(TelnyxWhatsappTemplate.name)
    )
    if industry_slug:
        from app.models.industry import Industry

        slug = industry_slug.strip().lower()
        industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
        if industry is None:
            raise SystemExit(f"Industry not found for slug={slug!r}")
        type_ids = list(db.scalars(select(SurveyType.id).where(SurveyType.industry_id == industry.id)))
        if not type_ids:
            return []
        stmt = stmt.where(TelnyxWhatsappTemplate.survey_type_id.in_(type_ids))
    return list(db.execute(stmt).scalars())


def _repair_draft(row: TelnyxWhatsappTemplate) -> bool:
    draft = _loads(row.draft_components_json)
    if not isinstance(draft, list) or not draft:
        return False
    normalized = _normalize_draft_components(draft)
    changed = json.dumps(normalized, sort_keys=True) != json.dumps(draft, sort_keys=True)
    had_invalid = _body_example_invalid(draft)
    if not changed and not had_invalid:
        return False
    row.draft_components_json = _dumps(normalized)
    row.example_values_json = _dumps(_example_values_for_storage(normalized))
    row.local_sync_status = _refresh_local_sync_status(row)
    return True


def _needs_push(row: TelnyxWhatsappTemplate) -> bool:
    status = str(row.local_sync_status or "").strip().lower()
    if status in {SYNC_DRAFT, SYNC_LOCAL_CHANGES, SYNC_ERROR}:
        return True
    record_id = str(row.telnyx_record_id or "").strip()
    if not record_id or record_id.startswith("local-"):
        return True
    label = telnyx_sync_ui_label(row).lower()
    return "not synced" in label or "out of sync" in label or "sync failed" in label


def _needs_status_refresh(row: TelnyxWhatsappTemplate) -> bool:
    remote_status = str(row.status or "").strip().upper()
    if remote_status in {"PENDING", "APPROVED"}:
        return True
    label = telnyx_sync_ui_label(row).lower()
    return "pending approval" in label


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit/repair/push all WA Survey templates")
    parser.add_argument("--dry-run", action="store_true", help="Report actions only — no writes or Telnyx calls")
    parser.add_argument("--industry-slug", default="", help="Limit to one industry slug")
    parser.add_argument("--skip-sync", action="store_true", help="Skip Telnyx import sync step")
    parser.add_argument("--push-only", action="store_true", help="Only push/refresh — skip draft repair")
    parser.add_argument(
        "--reset-from-remote",
        action="store_true",
        help="Reset broken APPROVED drafts from stored remote components before push",
    )
    args = parser.parse_args()

    summary = {
        "templates_scanned": 0,
        "sync_from_telnyx": None,
        "drafts_repaired": 0,
        "drafts_reset": 0,
        "pushed_ok": 0,
        "push_failed": 0,
        "status_refreshed": 0,
        "status_refresh_failed": 0,
        "skipped_push": 0,
        "errors": [],
    }

    with get_sessionmaker()() as db:
        if not args.skip_sync and not args.dry_run:
            print("Syncing templates from Telnyx…")
            sync_result = SurveyWhatsappTemplateService.sync_from_telnyx(db)
            summary["sync_from_telnyx"] = sync_result
            print(sync_result.get("message") or sync_result)
        elif args.skip_sync:
            print("Skipping Telnyx import sync (--skip-sync).")

        rows = _iter_survey_templates(db, industry_slug=args.industry_slug.strip() or None)
        summary["templates_scanned"] = len(rows)
        print(f"\nScanning {len(rows)} WA Survey template(s)…")

        for row in rows:
            label = row.display_name or row.name
            print(f"\n— {row.name} ({label})")

            if not args.push_only:
                row_repaired = False
                if args.reset_from_remote:
                    if args.dry_run:
                        print("  [dry-run] would reset draft from remote")
                    elif _reset_draft_from_remote(row):
                        summary["drafts_reset"] += 1
                        row_repaired = True
                        print("  reset draft from remote components")
                        db.add(row)
                elif _repair_draft(row):
                    if args.dry_run:
                        print("  [dry-run] would repair draft BODY examples")
                    else:
                        summary["drafts_repaired"] += 1
                        row_repaired = True
                        print("  repaired draft BODY examples")
                        db.add(row)
                if row_repaired and not args.dry_run:
                    db.commit()

            should_push = _needs_push(row)
            should_refresh = _needs_status_refresh(row)

            if should_push:
                if args.dry_run:
                    print("  [dry-run] would push to Telnyx")
                    continue
                try:
                    result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                    summary["pushed_ok"] += 1
                    msg = result.get("sync_message") or result.get("message") or "Pushed"
                    print(f"  push OK: {msg}")
                except SurveyWhatsappTemplateError as exc:
                    summary["push_failed"] += 1
                    summary["errors"].append(f"{row.name}: push — {exc}")
                    print(f"  push FAIL: {exc}")
            elif should_refresh:
                record_id = str(row.telnyx_record_id or "").strip()
                if not record_id or record_id.startswith("local-"):
                    summary["skipped_push"] += 1
                    print("  skip refresh — not synced to Telnyx yet")
                    continue
                if args.dry_run:
                    print("  [dry-run] would refresh Telnyx/Meta status")
                    continue
                try:
                    result = SurveyWhatsappTemplateService.refresh_telnyx_status(db, row)
                    summary["status_refreshed"] += 1
                    print(f"  status refresh OK: {result.get('message') or result.get('approval_status')}")
                except SurveyWhatsappTemplateError as exc:
                    summary["status_refresh_failed"] += 1
                    summary["errors"].append(f"{row.name}: refresh — {exc}")
                    print(f"  status refresh FAIL: {exc}")
            else:
                summary["skipped_push"] += 1
                ui = telnyx_sync_ui_label(row)
                print(f"  OK — {ui} (local={row.local_sync_status})")

        if not args.dry_run:
            db.commit()

    print("\n=== Audit summary ===")
    print(f"Templates scanned:     {summary['templates_scanned']}")
    print(f"Drafts repaired:       {summary['drafts_repaired']}")
    print(f"Drafts reset:          {summary['drafts_reset']}")
    print(f"Pushed OK:             {summary['pushed_ok']}")
    print(f"Push failed:           {summary['push_failed']}")
    print(f"Status refreshed:      {summary['status_refreshed']}")
    print(f"Status refresh failed: {summary['status_refresh_failed']}")
    print(f"Skipped (in sync):     {summary['skipped_push']}")
    if summary["errors"]:
        print("\nErrors:")
        for err in summary["errors"]:
            print(f"  • {err}")

    return 1 if summary["push_failed"] or summary["status_refresh_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
