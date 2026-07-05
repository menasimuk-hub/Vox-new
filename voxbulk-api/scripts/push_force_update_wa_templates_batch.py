#!/usr/bin/env python3
"""Force-push local WA survey template drafts to Meta (same name, content update).

Use when Meta still serves stale approved bodies/buttons but Admin draft is correct.
Processes buttoned survey keepers in batches to avoid rate limits.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  python scripts/push_force_update_wa_templates_batch.py --dry-run
  python scripts/push_force_update_wa_templates_batch.py --batch-size 10 --delay 2
  python scripts/push_force_update_wa_templates_batch.py --industry-slug general --batch-size 5
  python scripts/push_force_update_wa_templates_batch.py --loop-until-done

Optional first step (repair invalid BODY examples + reorder rating buttons):
  python scripts/push_force_update_wa_templates_batch.py --repair-first --loop-until-done
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _effective_components,
    template_row_has_buttons,
)
from app.services.wa_template_meta_sync import format_template_push_error

from scripts.wa_not_pushed_lib import iter_survey_keeper_rows, split_buttoned_buttonless

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"

repair_mod = importlib.util.spec_from_file_location(
    "repair_wa_survey_template_drafts",
    ROOT / "scripts" / "repair_wa_survey_template_drafts.py",
)
if repair_mod is None or repair_mod.loader is None:
    raise SystemExit("Could not load repair_wa_survey_template_drafts.py")
repair = importlib.util.module_from_spec(repair_mod)
repair_mod.loader.exec_module(repair)


def _repair_row(row) -> bool:
    draft = repair._loads(row.draft_components_json)
    if not isinstance(draft, list) or not draft:
        return False
    normalized = repair._normalize_draft_components(draft, step_role=str(row.step_role or "") or None)
    changed = json.dumps(normalized, sort_keys=True) != json.dumps(draft, sort_keys=True)
    had_invalid = repair._body_example_invalid(draft)
    if not changed and not had_invalid:
        return False
    row.draft_components_json = repair._dumps(normalized)
    row.example_values_json = repair._dumps(repair._example_values_for_storage(normalized))
    row.local_sync_status = repair._refresh_local_sync_status(row)
    return True


def _collect_target_ids(db, *, industry_slug: str | None, include_buttonless: bool) -> list[int]:
    keepers = iter_survey_keeper_rows(db, industry_slug=industry_slug)
    buttoned, buttonless = split_buttoned_buttonless(keepers)
    rows = list(buttoned)
    if include_buttonless:
        rows.extend(buttonless)
    out: list[TelnyxWhatsappTemplate] = []
    for row in rows:
        if not _effective_components(row):
            continue
        if not include_buttonless and not template_row_has_buttons(row):
            continue
        out.append(row)
    pairs = [(str(r.name or r.id), int(r.id)) for r in out]
    pairs.sort(key=lambda item: item[0])
    return [row_id for _, row_id in pairs]


def _push_row(db, row, *, force: bool) -> dict:
    SurveyWhatsappTemplateService.push_to_telnyx(db, row, force_approved_update=force)
    return {"ok": True, "name": row.name}


def _push_with_rename_retry(db, row, *, force: bool) -> dict:
    name = str(row.name)
    try:
        return _push_row(db, row, force=force)
    except SurveyWhatsappTemplateError as exc:
        payload = getattr(exc, "payload", None) or {}
        if payload.get("requires_rename") and payload.get("suggested_template_name"):
            new_name = str(payload["suggested_template_name"]).strip()
            print(f"  Rename {name} → {new_name} (Meta lock) …", flush=True)
            row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
            return _push_row(db, row, force=force)
        raise


def run_batch(
    db,
    target_ids: list[int],
    *,
    offset: int,
    batch_size: int,
    delay: float,
    dry_run: bool,
    repair_first: bool,
    force: bool,
) -> dict:
    chunk_ids = target_ids[offset : offset + batch_size]
    ok_count = 0
    fail_count = 0
    repaired = 0
    failures: list[dict] = []

    for index, row_id in enumerate(chunk_ids, start=1):
        row = db.get(TelnyxWhatsappTemplate, int(row_id))
        if row is None:
            fail_count += 1
            failures.append({"id": row_id, "name": "", "error": "template_not_found"})
            print(f"  FAIL id={row_id}: template not found", file=sys.stderr)
            continue
        name = str(row.name)
        global_idx = offset + index
        print(f"[{global_idx}/{len(target_ids)}] id={row.id} {name} …", flush=True)

        if dry_run:
            print(f"  would force-push {name}")
            ok_count += 1
            continue

        if repair_first and _repair_row(row):
            db.add(row)
            db.commit()
            db.refresh(row)
            repaired += 1

        try:
            _push_with_rename_retry(db, row, force=force)
            ok_count += 1
            print(f"  OK {name}")
        except SurveyWhatsappTemplateError as exc:
            err = format_template_push_error(exc)
            fail_count += 1
            failures.append({"id": row.id, "name": name, "error": err})
            print(f"  FAIL {name}: {err}", file=sys.stderr)

        if delay > 0 and index < len(chunk_ids):
            time.sleep(delay)

    next_offset = offset + len(chunk_ids)
    return {
        "offset": offset,
        "batch_size": batch_size,
        "processed": len(chunk_ids),
        "ok": ok_count,
        "failed": fail_count,
        "repaired": repaired,
        "failures": failures,
        "next_offset": next_offset,
        "has_more": next_offset < len(target_ids),
        "total": len(target_ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Force-push local survey templates to Meta in batches")
    parser.add_argument("--industry-slug", help="Limit to one industry (default: all survey keepers)")
    parser.add_argument("--batch-size", type=int, default=10, help="Templates per batch (max 10)")
    parser.add_argument("--offset", type=int, default=0, help="Start offset into target list")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between pushes in a batch")
    parser.add_argument("--repair-first", action="store_true", help="Repair drafts + reorder buttons before push")
    parser.add_argument(
        "--include-buttonless",
        action="store_true",
        help="Also push session-text templates (welcome/thank-you/tell-us-more)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--loop-until-done",
        action="store_true",
        help="Run batches until all targets processed (respects --offset start)",
    )
    parser.add_argument(
        "--no-force",
        action="store_true",
        help="Use default push branch logic (not recommended for stale Meta content)",
    )
    args = parser.parse_args()

    batch_size = max(1, min(int(args.batch_size or 10), 10))
    force = not bool(args.no_force)
    industry_slug = str(args.industry_slug or "").strip() or None

    with get_sessionmaker()() as db:
        target_ids = _collect_target_ids(
            db,
            industry_slug=industry_slug,
            include_buttonless=bool(args.include_buttonless),
        )

    print(f"Targets: {len(target_ids)} survey template(s)" + (f" (industry={industry_slug})" if industry_slug else ""))
    if not target_ids:
        print("Nothing to push.")
        return 0

    offset = max(0, int(args.offset or 0))
    totals = {"ok": 0, "failed": 0, "repaired": 0, "batches": 0}
    all_failures: list[dict] = []

    while True:
        with get_sessionmaker()() as db:
            result = run_batch(
                db,
                target_ids,
                offset=offset,
                batch_size=batch_size,
                delay=float(args.delay or 0),
                dry_run=bool(args.dry_run),
                repair_first=bool(args.repair_first),
                force=force,
            )
        totals["ok"] += int(result["ok"])
        totals["failed"] += int(result["failed"])
        totals["repaired"] += int(result["repaired"])
        totals["batches"] += 1
        all_failures.extend(result.get("failures") or [])

        if not result.get("has_more") or not args.loop_until_done:
            offset = int(result.get("next_offset") or offset)
            break
        offset = int(result["next_offset"])
        print(f"\n--- next batch offset={offset} ---\n", flush=True)

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "industry_slug": industry_slug,
        "total_targets": len(target_ids),
        "force_approved_update": force,
        "repair_first": bool(args.repair_first),
        "include_buttonless": bool(args.include_buttonless),
        "dry_run": bool(args.dry_run),
        **totals,
        "failures": all_failures,
    }
    if not args.dry_run:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug_bit = (industry_slug or "all").replace("/", "_")
        report_path = REPORT_DIR / f"force-push-{slug_bit}-{stamp}.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Report: {report_path}")

    print(
        f"\nDone — OK: {totals['ok']}, failed: {totals['failed']}, "
        f"repaired: {totals['repaired']}, batches: {totals['batches']}"
    )
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
