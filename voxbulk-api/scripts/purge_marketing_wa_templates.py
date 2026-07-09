#!/usr/bin/env python3
"""Rewrite live Marketing *survey* templates to UTILITY — keeps local DB rows.

Uses DeepSeek by default for BODY rewrites (OpenAI optional). Do NOT pass --no-llm
for employee / inclusion templates — rule-based keeps the same text and Meta rejects it.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python scripts/purge_marketing_wa_templates.py
  .venv/bin/python scripts/purge_marketing_wa_templates.py --apply --push --sync-remote --yes --limit 1
  .venv/bin/python scripts/purge_marketing_wa_templates.py --apply --push --sync-remote --yes
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
    if preview.get("llm_on_apply"):
        print(f"    note: {preview['llm_on_apply']}")


def _confirm_push() -> bool:
    print("\n" + "=" * 60)
    print("Local DB rows are KEPT (rewrite + rename in place).")
    print("DeepSeek rewrites BODY text; only OLD Marketing names removed on Meta/Telnyx.")
    print("Pushes run 1 every 30s with live progress below.")
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
    parser.add_argument(
        "--llm-provider",
        default="deepseek",
        choices=("deepseek", "openai", "groq"),
        help="LLM for BODY rewrite (default: deepseek)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Rule-based only — OK for would_recommend/NPS; NOT for employee/inclusion",
    )
    parser.add_argument("--push-delay", type=float, default=30.0, help="Seconds between pushes")
    parser.add_argument("--limit", type=int, default=0, help="Max items (0=all)")
    parser.add_argument(
        "--delete-remote-orphans",
        action="store_true",
        help="Also delete remote Marketing survey names with no local DB row",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    use_llm = not args.no_llm

    db = get_sessionmaker()()
    try:
        overview, plan = build_marketing_purge_plan(
            db,
            delete_remote_orphans=bool(args.delete_remote_orphans),
        )
    finally:
        db.close()

    work_plan = plan[: args.limit] if args.limit and args.limit > 0 else plan

    if args.apply and args.push and not args.yes:
        if not _confirm_push():
            print("Aborted.", file=sys.stderr)
            return 1
        print(f"\nApplying {len(work_plan)} item(s) via {args.llm_provider}…\n", flush=True)

    print("=" * 60)
    print("SURVEY MARKETING → UTILITY" + (" (dry-run)" if dry_run else " (apply)"))
    print("=" * 60)
    sr = overview.get("survey_remote") or {}
    print(
        f"Live Marketing on Meta: {sr.get('remote_marketing_meta', '—')} | "
        f"Telnyx: {sr.get('remote_marketing_telnyx', '—')}"
    )
    print(f"Templates to rewrite: {overview.get('push_items', 0)}")
    print(f"LLM: {'off (rule-based)' if args.no_llm else args.llm_provider}")
    print(f"Local DB rows deleted: {overview.get('local_db_rows_deleted', 0)} (always 0)")

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
        print(f"\nDry-run only — no changes. Report: {report_path}")
        print(
            "Apply one test:\n"
            "  python scripts/purge_marketing_wa_templates.py --apply --push --sync-remote --yes --limit 1"
        )
        return 0

    with get_sessionmaker()() as db:
        results = apply_purge_plan(
            db,
            work_plan,
            dry_run=False,
            push=bool(args.push),
            sync_remote=bool(args.sync_remote),
            use_llm=use_llm,
            llm_provider=args.llm_provider,
            push_delay_seconds=max(0.0, float(args.push_delay)),
        )

    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"marketing-purge-apply-{stamp}.json"
    report_path.write_text(
        json.dumps(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "pushed": bool(args.push),
                "llm_provider": args.llm_provider,
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
    if fail:
        print("Avoid --no-llm unless the template is NPS/would_recommend.", file=sys.stderr)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
