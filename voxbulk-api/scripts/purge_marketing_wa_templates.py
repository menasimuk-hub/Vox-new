#!/usr/bin/env python3
"""Rewrite live Marketing *survey* templates to UTILITY — keeps local DB rows.

What this does (per template, ~22 on Meta):
  1. KEEP your local telnyx_whatsapp_templates row (same id — surveys stay linked)
  2. Rewrite BODY to utility-compliant English
  3. Rename locally if needed (_002_ -> _003_) when Meta blocks category change
  4. Push new UTILITY template to Meta (1 every 30s when --push)
  5. DELETE only the OLD Marketing name on Meta + Telnyx (e.g. was_*_002_en)

What this does NOT do:
  - Does NOT delete local DB rows or survey step mappings
  - Does NOT touch customer feedback unless you pass --delete-remote-orphans for
    remote-only survey names with no local row

Usage (VPS):
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python scripts/purge_marketing_wa_templates.py
  .venv/bin/python scripts/purge_marketing_wa_templates.py --apply --push --sync-remote --no-llm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.wa_marketing_purge_service import apply_purge_plan, build_marketing_purge_plan

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"


def _print_plan_item(index: int, item) -> None:
    preview = item.dry_preview or {}
    print(f"\n[{index}] REWRITE survey | local row KEPT (id={preview.get('local_row_id')})")
    print(f"    current name:  {item.label}")
    if preview.get("new_local_name") and preview.get("new_local_name") != item.label:
        print(f"    renamed to:    {preview['new_local_name']}")
    if preview.get("delete_old_remote_name"):
        print(f"    delete Meta/Telnyx only: {preview['delete_old_remote_name']}")
    else:
        print(f"    remote delete: {preview.get('deletes', 'same-name update')}")
    if preview.get("body_before"):
        print(f"    was: {str(preview['body_before'])[:120]}…")
    if preview.get("body_after"):
        print(f"    now: {str(preview['body_after'])[:120]}…")


def _confirm_push() -> bool:
    print("\n" + "=" * 60)
    print("Local DB rows are KEPT (rewrite + rename in place).")
    print("Only OLD Marketing template NAMES are removed from Meta/Telnyx")
    print("after each new UTILITY template is pushed (30s between pushes).")
    print("Type PUSH to continue (anything else aborts): ", end="", flush=True)
    try:
        return input().strip().upper() == "PUSH"
    except EOFError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite Marketing survey templates to UTILITY (keeps local DB)"
    )
    parser.add_argument("--apply", action="store_true", help="Apply plan (default: dry-run)")
    parser.add_argument("--push", action="store_true", help="Push to Meta (30s between each)")
    parser.add_argument("--yes", action="store_true", help="Skip PUSH confirmation")
    parser.add_argument("--sync-remote", action="store_true", help="Refresh row from Meta before rewrite")
    parser.add_argument("--no-llm", action="store_true", help="Rule-based rewrite (NPS/recommend)")
    parser.add_argument("--push-delay", type=float, default=30.0, help="Seconds between pushes")
    parser.add_argument("--limit", type=int, default=0, help="Max items (0=all)")
    parser.add_argument(
        "--delete-remote-orphans",
        action="store_true",
        help="Also delete remote Marketing survey names with no local DB row",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    if args.apply and args.push and not args.yes and not _confirm_push():
        print("Aborted.", file=sys.stderr)
        return 1

    db = get_sessionmaker()()
    try:
        overview, plan = build_marketing_purge_plan(
            db,
            delete_remote_orphans=bool(args.delete_remote_orphans),
        )
    finally:
        db.close()

    print("=" * 60)
    print("SURVEY MARKETING → UTILITY" + (" (dry-run)" if dry_run else " (apply)"))
    print("=" * 60)
    sr = overview.get("survey_remote") or {}
    print(
        f"Live Marketing on Meta: {sr.get('remote_marketing_meta', '—')} | "
        f"Telnyx: {sr.get('remote_marketing_telnyx', '—')}"
    )
    print(f"Templates to rewrite: {overview.get('push_items', 0)}")
    print(f"Local DB rows deleted: {overview.get('local_db_rows_deleted', 0)} (always 0)")

    work_plan = plan[: args.limit] if args.limit and args.limit > 0 else plan
    for index, item in enumerate(work_plan, start=1):
        if item.action == "survey_rewrite_push":
            _print_plan_item(index, item)
        elif item.action == "survey_delete_remote":
            print(f"\n[{index}] DELETE remote only (no local row): {item.label}")

    if dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / f"marketing-purge-dryrun-{stamp}.json"
        report_path.write_text(
            json.dumps(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "dry_run": True,
                    "overview": overview,
                    "plan": [p.to_dict() for p in work_plan],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nDry-run only — no DB or Meta changes. Report: {report_path}")
        print("Apply:  python scripts/purge_marketing_wa_templates.py --apply --push --sync-remote --no-llm")
        return 0

    with get_sessionmaker()() as db:
        results = apply_purge_plan(
            db,
            work_plan,
            dry_run=False,
            push=bool(args.push),
            sync_remote=bool(args.sync_remote),
            use_llm=not args.no_llm,
            push_delay_seconds=max(0.0, float(args.push_delay)),
        )

    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    for result in results:
        status = "OK" if result.get("ok") else "FAIL"
        line = f"{status} [{result.get('index')}/{result.get('total')}] {result.get('label')}"
        if result.get("error"):
            line += f" — {result['error']}"
        elif result.get("new_name"):
            line += f" → {result['new_name']} (local row kept)"
        if result.get("deleted_remote"):
            line += f" | removed old Meta/Telnyx: {result['deleted_remote']}"
        print(line, flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"marketing-purge-apply-{stamp}.json"
    report_path.write_text(
        json.dumps(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "pushed": bool(args.push),
                "overview": overview,
                "ok": ok,
                "failed": fail,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nDone: {ok} ok, {fail} failed. Report: {report_path}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
