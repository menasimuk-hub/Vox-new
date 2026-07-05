#!/usr/bin/env python3
"""Safely push all Customer Feedback templates to Meta/Telnyx in small batches.

Designed for overnight runs — small batches + pauses to avoid rate limits.

Usage (VPS, after deploy):
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate

  # Preview only (no API push)
  python scripts/push_all_feedback_to_meta_overnight.py --dry-run

  # Full overnight run (~3 hours for ~2800 language rows)
  python scripts/push_all_feedback_to_meta_overnight.py

  # One industry only
  python scripts/push_all_feedback_to_meta_overnight.py --industry-slug fitness

  # Resume after interrupt (reads state file)
  python scripts/push_all_feedback_to_meta_overnight.py --resume

  # Run in background + log (use -u so lines appear immediately in nohup log)
  nohup python -u scripts/push_all_feedback_to_meta_overnight.py \
    > /tmp/cf-meta-push-$(date +%Y%m%d-%H%M).log 2>&1 &
  tail -f /tmp/cf-meta-push-*.log
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _configure_stdio() -> None:
    """Line-buffer stdout/stderr so nohup logs update in real time."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
        except Exception:
            pass


def _log(msg: str, *, err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    print(msg, file=stream, flush=True)

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackIndustry
from app.services.customer_feedback.feedback_telnyx_push_service import (
    FeedbackTelnyxPushError,
    push_feedback_templates_batch,
    resolve_feedback_industry,
)

DEFAULT_INDUSTRY_SLUGS = [
    "restaurant",
    "retail",
    "salon",
    "hotel",
    "others",
    "fitness",
    "events",
]

REPORT_DIR = ROOT / "seed-data" / "customer-feedback" / "push-reports"
STATE_FILE = REPORT_DIR / "push_all_feedback_state.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _list_industries(db, slugs: list[str] | None) -> list[FeedbackIndustry]:
    if slugs:
        return [resolve_feedback_industry(db, industry_slug=slug) for slug in slugs]
    rows = db.scalars(
        select(FeedbackIndustry).order_by(FeedbackIndustry.sort_order, FeedbackIndustry.name)
    ).all()
    return list(rows)


def _push_industry(
    db,
    industry: FeedbackIndustry,
    *,
    batch_size: int,
    delay_sec: float,
    dry_run: bool,
    start_offset: int,
    max_failures: int,
) -> dict:
    offset = max(0, int(start_offset or 0))
    batch_num = 0
    batch_failures = 0
    totals: dict = {
        "industry_id": industry.id,
        "industry_slug": industry.slug,
        "industry_name": industry.name,
        "batches": 0,
        "processed": 0,
        "total": 0,
        "pushed": 0,
        "linked": 0,
        "failed": 0,
        "errors": [],
        "dry_run": dry_run,
        "completed": False,
    }

    while True:
        batch_num += 1
        totals["batches"] = batch_num
        _log(f"\n[{_utc_now()}] {industry.slug}: batch {batch_num} offset={offset} limit={batch_size}")

        try:
            batch = push_feedback_templates_batch(
                db,
                industry_id=industry.id,
                offset=offset,
                limit=batch_size,
                dry_run=dry_run,
                phase="push",
            )
        except FeedbackTelnyxPushError as exc:
            batch_failures += 1
            totals["failed"] += 1
            totals["errors"].append({"batch": batch_num, "offset": offset, "error": str(exc)})
            _log(f"  BATCH ERROR: {exc}")
            if batch_failures >= max_failures:
                _log(f"  Stopping industry — {max_failures} batch failures reached.")
                break
            _log(f"  Waiting {delay_sec * 2:.0f}s before retry…")
            time.sleep(delay_sec * 2)
            continue

        batch_failures = 0
        totals["total"] = int(batch.get("total") or totals["total"])
        totals["processed"] = int(batch.get("processed") or offset)
        totals["pushed"] += int(batch.get("pushed") or 0)
        totals["linked"] += int(batch.get("linked") or 0)
        batch_failed = int(batch.get("failed") or 0)
        totals["failed"] += batch_failed
        totals["errors"].extend(batch.get("errors") or [])

        _log(
            f"  {batch.get('message') or 'batch done'} "
            f"| linked={batch.get('linked', 0)} failed={batch_failed}"
        )

        if batch_failed:
            for err in (batch.get("errors") or [])[:3]:
                _log(f"    FAIL {err.get('template_key')}: {str(err.get('error', ''))[:120]}")

        if not batch.get("has_more"):
            totals["completed"] = True
            break

        offset = int(batch.get("next_offset") or offset + batch_size)
        if delay_sec > 0:
            time.sleep(delay_sec)

    if totals["completed"] and not dry_run:
        _log(f"\n[{_utc_now()}] {industry.slug}: pulling status from Meta…")
        try:
            pull = push_feedback_templates_batch(db, industry_id=industry.id, phase="pull")
            totals["pull"] = pull.get("pull") or pull
            _log(f"  {pull.get('message') or 'Pull complete'}")
        except FeedbackTelnyxPushError as exc:
            totals["errors"].append({"phase": "pull", "error": str(exc)})
            _log(f"  PULL ERROR: {exc}")

    return totals


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="Push all Customer Feedback templates to Meta in safe batches (overnight)"
    )
    parser.add_argument(
        "--industry-slug",
        action="append",
        dest="industry_slugs",
        help="Limit to one or more industry slugs (repeat flag). Default: all industries.",
    )
    parser.add_argument("--batch-size", type=int, default=5, help="Templates per batch (default 5, max 50)")
    parser.add_argument(
        "--delay-sec",
        type=float,
        default=15.0,
        help="Pause between batches in seconds (default 15 ≈ ~3h for full catalog)",
    )
    parser.add_argument(
        "--industry-delay-sec",
        type=float,
        default=45.0,
        help="Pause between industries in seconds (default 45)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate payloads only — no Meta POST")
    parser.add_argument("--resume", action="store_true", help="Resume from last saved state file")
    parser.add_argument("--no-resume", action="store_true", help="Ignore saved state and start fresh")
    parser.add_argument(
        "--max-failures",
        type=int,
        default=5,
        help="Stop current industry after this many batch-level failures (default 5)",
    )
    parser.add_argument("--json", action="store_true", help="Print full report JSON at end")
    args = parser.parse_args()

    batch_size = max(1, min(int(args.batch_size), 50))
    explicit_slugs = args.industry_slugs

    state = {} if args.no_resume else _load_state()
    resume_slug = state.get("next_industry_slug") if (args.resume or state.get("next_industry_slug")) else None
    resume_offset = int(state.get("next_offset") or 0) if resume_slug else 0

    started = _utc_now()
    report: dict = {
        "started_at": started,
        "dry_run": bool(args.dry_run),
        "batch_size": batch_size,
        "delay_sec": args.delay_sec,
        "industry_delay_sec": args.industry_delay_sec,
        "industries": [],
        "summary": {},
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _save_state(
        {
            "updated_at": _utc_now(),
            "status": "starting",
            "pid": os.getpid(),
            "cwd": str(Path.cwd()),
        }
    )

    _log("=== Customer Feedback -> Meta overnight push ===")
    _log(f"Started: {started}")
    _log(f"PID: {os.getpid()} | CWD: {Path.cwd()}")
    _log(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE PUSH'}")
    _log(f"Batch size: {batch_size}, delay: {args.delay_sec}s, industry delay: {args.industry_delay_sec}s")
    if resume_slug:
        _log(f"Resuming: {resume_slug} @ offset {resume_offset}")

    with get_sessionmaker()() as db:
        industries = _list_industries(db, explicit_slugs)
        if not industries:
            _log("No industries found.", err=True)
            return 1

        skip_until_resume = bool(resume_slug)
        grand = {"industries": 0, "completed": 0, "pushed": 0, "linked": 0, "failed": 0}
        stopped_early = False

        for idx, industry in enumerate(industries):
            if skip_until_resume:
                if industry.slug != resume_slug:
                    _log(f"\nSkipping {industry.slug} (resume point not reached yet)")
                    continue
                skip_until_resume = False
                start_offset = resume_offset
            else:
                start_offset = 0

            _log(f"\n{'=' * 60}")
            _log(f"Industry: {industry.name} ({industry.slug})")
            _log(f"{'=' * 60}")

            _save_state(
                {
                    "updated_at": _utc_now(),
                    "next_industry_slug": industry.slug,
                    "next_offset": start_offset,
                    "dry_run": args.dry_run,
                }
            )

            result = _push_industry(
                db,
                industry,
                batch_size=batch_size,
                delay_sec=args.delay_sec,
                dry_run=args.dry_run,
                start_offset=start_offset,
                max_failures=args.max_failures,
            )
            report["industries"].append(result)

            grand["industries"] += 1
            grand["pushed"] += result["pushed"]
            grand["linked"] += result["linked"]
            grand["failed"] += result["failed"]
            if result["completed"]:
                grand["completed"] += 1

            if result["completed"]:
                _save_state(
                    {
                        "updated_at": _utc_now(),
                        "last_completed_slug": industry.slug,
                        "next_industry_slug": None,
                        "next_offset": 0,
                    }
                )
            else:
                stopped_early = True
                _save_state(
                    {
                        "updated_at": _utc_now(),
                        "next_industry_slug": industry.slug,
                        "next_offset": result["processed"],
                        "incomplete": True,
                    }
                )
                _log(f"\nStopped early on {industry.slug} — re-run with --resume")
                break

            if idx < len(industries) - 1 and args.industry_delay_sec > 0:
                time.sleep(args.industry_delay_sec)

    finished = _utc_now()
    report["finished_at"] = finished
    report["summary"] = grand

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"push-all-feedback-{finished.replace(':', '')}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    _log(f"\n{'=' * 60}")
    _log("DONE")
    _log(f"Finished: {finished}")
    _log(f"Industries completed: {grand['completed']}/{grand['industries']}")
    _log(f"Pushed rows: {grand['pushed']} | Linked (already on Meta): {grand['linked']} | Failed: {grand['failed']}")
    _log(f"Report: {report_path}")

    if args.json:
        _log(json.dumps(report, indent=2, default=str))

    all_done = not stopped_early and grand["completed"] == len(industries)
    if all_done and STATE_FILE.exists():
        STATE_FILE.unlink()
    if grand["failed"] > 0 or stopped_early:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
