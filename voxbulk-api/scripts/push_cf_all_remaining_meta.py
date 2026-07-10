#!/usr/bin/env python3
"""Push all remaining Customer Feedback templates to Meta 99 only (~24h safe pace).

Loops every industry in order (in-progress first), one topic per batch, auto-retries
on failure with backoff — state is preserved so resumes never re-spam linked rows.

VPS (recommended — tmux so SSH disconnect is safe):

  tmux new -s cf-meta99
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  git pull origin main   # after this script is on main

  # Preview plan (no POST):
  python scripts/push_cf_all_remaining_meta.py --dry-run --status

  # Start ~24h Meta-only push (continues hotel if chunk-state/hotel.json exists):
  python -u scripts/push_cf_all_remaining_meta.py --target-hours 24 2>&1 | tee /tmp/cf-meta99-all.log

  # Detach: Ctrl+B then D
  # Reattach: tmux attach -t cf-meta99

Stop any dual Meta+Telnyx push first (optional if switching modes):

  tmux send-keys -t cf-hotel C-c Enter

Options:
  --target-hours 24     Spread remaining rows across this budget (default 24)
  --lang-batch 2        Languages per sub-batch (default 2)
  --topic-pause-sec 30  Pause between topics (default 30)
  --start-industry hotel  Force order to start at this slug
  --status              Print progress + exit (no push)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATE_DIR = ROOT / "seed-data" / "customer-feedback" / "push-reports" / "chunk-state"
GLOBAL_STATE_PATH = STATE_DIR / "_meta99-all-push.json"
CHUNK_SCRIPT = ROOT / "scripts" / "push_cf_service_chunked.py"

RATE_LIMIT_RE = re.compile(
    r"rate.?limit|too many|throttl|429|spam|temporarily unavailable|try again later",
    re.I,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    print(msg, flush=True)


def _industry_state_path(slug: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in slug)
    return STATE_DIR / f"{safe}.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utc_now()
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _lang_rows_for_industry(db, industry_id: str) -> tuple[list[str], list[int], int]:
    from sqlalchemy import select

    from app.models.customer_feedback import FeedbackSurveyType, FeedbackWaTemplate
    from app.services.customer_feedback.feedback_telnyx_push_service import is_marketing_wa_template

    topics = list(
        db.scalars(
            select(FeedbackSurveyType)
            .where(FeedbackSurveyType.industry_id == industry_id)
            .order_by(FeedbackSurveyType.sort_order, FeedbackSurveyType.name)
        ).all()
    )
    slugs = [t.slug for t in topics]
    counts: list[int] = []
    for topic in topics:
        rows = list(
            db.scalars(select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id == topic.id)).all()
        )
        counts.append(
            sum(1 for r in rows if not is_marketing_wa_template(r) and str(r.body_text or "").strip())
        )
    return slugs, counts, sum(counts)


def _remaining_rows(slug: str, topic_counts: list[int], state: dict) -> int:
    topic_index = int(state.get("topic_index") or 0)
    lang_offset = int(state.get("lang_offset") or 0)
    done = sum(topic_counts[:topic_index]) + lang_offset
    return max(0, sum(topic_counts) - done)


def _compute_delay_sec(
    *,
    remaining_rows: int,
    remaining_topic_pauses: int,
    target_hours: float,
    topic_pause_sec: float,
    lang_batch: int,
    min_delay: float = 12.0,
    max_delay: float = 45.0,
) -> float:
    """Meta-only: ~3s API overhead per row."""
    budget = max(3600.0, target_hours * 3600.0 - remaining_topic_pauses * topic_pause_sec)
    per_row = budget / max(1, remaining_rows)
    delay = per_row - 3.0
    delay = max(min_delay, min(max_delay, delay))
    return round(delay, 1)


def _list_industries(db) -> list[tuple[str, str, str]]:
    from sqlalchemy import select

    from app.models.customer_feedback import FeedbackIndustry

    rows = db.scalars(
        select(FeedbackIndustry)
        .where(FeedbackIndustry.is_active.is_(True))
        .order_by(FeedbackIndustry.sort_order, FeedbackIndustry.name)
    ).all()
    return [(r.slug, r.name, r.id) for r in rows]


def _order_industries(
    industries: list[tuple[str, str, str]],
    *,
    completed: list[str],
    start_industry: str | None,
) -> list[tuple[str, str, str]]:
    pending = [item for item in industries if item[0] not in completed]
    in_progress = [item for item in pending if _industry_state_path(item[0]).exists()]
    not_started = [item for item in pending if not _industry_state_path(item[0]).exists()]

    ordered = in_progress + not_started
    if start_industry:
        idx = next((i for i, item in enumerate(ordered) if item[0] == start_industry), -1)
        if idx > 0:
            ordered = ordered[idx:] + ordered[:idx]
    return ordered


def _collect_plan(
    db,
    *,
    completed: list[str],
    start_industry: str | None,
    target_hours: float,
    lang_batch: int,
    topic_pause_sec: float,
) -> dict:
    industries = _list_industries(db)
    ordered = _order_industries(industries, completed=completed, start_industry=start_industry)

    items: list[dict] = []
    total_remaining = 0
    total_topic_pauses = 0

    for slug, name, industry_id in ordered:
        _slugs, topic_counts, total_rows = _lang_rows_for_industry(db, industry_id)
        state = _load_json(_industry_state_path(slug))
        rem = _remaining_rows(slug, topic_counts, state)
        topic_index = int(state.get("topic_index") or 0)
        lang_offset = int(state.get("lang_offset") or 0)
        topics_left = max(0, len(topic_counts) - topic_index - (0 if lang_offset < topic_counts[topic_index] else 1))
        pauses = max(0, topics_left)
        total_remaining += rem
        total_topic_pauses += pauses
        items.append(
            {
                "slug": slug,
                "name": name,
                "total_rows": total_rows,
                "remaining_rows": rem,
                "topic_index": topic_index,
                "lang_offset": lang_offset,
                "in_progress": bool(state),
                "topic_pauses_left": pauses,
            }
        )

    delay = _compute_delay_sec(
        remaining_rows=total_remaining,
        remaining_topic_pauses=total_topic_pauses,
        target_hours=target_hours,
        topic_pause_sec=topic_pause_sec,
        lang_batch=lang_batch,
    )
    sec_row = delay + 3.0
    eta_sec = total_remaining * sec_row + total_topic_pauses * topic_pause_sec

    return {
        "industries": items,
        "total_remaining_rows": total_remaining,
        "total_topic_pauses": total_topic_pauses,
        "computed_delay_sec": delay,
        "estimated_hours": round(eta_sec / 3600.0, 2),
        "target_hours": target_hours,
    }


def _failure_pause_sec(*, failures: int, rate_limited: bool, base: int, cap: int) -> int:
    if rate_limited:
        return min(cap, max(900, base * 4))
    pause = base * (2 ** min(failures, 4))
    return min(cap, pause)


def _run_chunk(
    *,
    industry_slug: str,
    delay_sec: float,
    linked_delay_sec: float,
    lang_batch: int,
    topic_pause_sec: float,
    dry_run: bool,
) -> tuple[int, str]:
    cmd = [
        sys.executable,
        "-u",
        str(CHUNK_SCRIPT),
        "--industry-slug",
        industry_slug,
        "--continue",
        "--topics-per-run",
        "1",
        "--lang-batch",
        str(lang_batch),
        "--delay-sec",
        str(delay_sec),
        "--linked-delay-sec",
        str(linked_delay_sec),
        "--meta-only",
        "--pull-after-topic",
    ]
    if dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if output.strip():
        _log(output.rstrip())
    return proc.returncode, output


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Push all remaining CF templates — Meta 99 only, ~24h pace")
    parser.add_argument("--target-hours", type=float, default=24.0, help="Time budget for all remaining rows")
    parser.add_argument("--lang-batch", type=int, default=2)
    parser.add_argument("--topic-pause-sec", type=float, default=30.0)
    parser.add_argument("--linked-delay-sec", type=float, default=2.0)
    parser.add_argument("--start-industry", help="Start at this industry slug (e.g. restaurant)")
    parser.add_argument(
        "--skip-industries",
        help="Comma-separated industry slugs to skip (e.g. hotel)",
    )
    parser.add_argument("--retry-base-sec", type=int, default=60, help="First retry pause after failure")
    parser.add_argument("--retry-cap-sec", type=int, default=900, help="Max retry pause (15 min)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true", help="Print plan and global state, then exit")
    parser.add_argument("--reset-global-state", action="store_true", help="Clear orchestrator state only")
    args = parser.parse_args()

    lang_batch = max(1, min(int(args.lang_batch), 10))

    if args.reset_global_state:
        if GLOBAL_STATE_PATH.exists():
            GLOBAL_STATE_PATH.unlink()
        _log(f"Cleared {GLOBAL_STATE_PATH}")
        return 0

    from app.core.database import get_sessionmaker

    global_state = _load_json(GLOBAL_STATE_PATH)
    completed = list(global_state.get("completed_industries") or [])
    skip_slugs = [s.strip() for s in str(args.skip_industries or "").split(",") if s.strip()]
    for slug in skip_slugs:
        if slug not in completed:
            completed.append(slug)

    with get_sessionmaker()() as db:
        plan = _collect_plan(
            db,
            completed=completed,
            start_industry=args.start_industry,
            target_hours=float(args.target_hours),
            lang_batch=lang_batch,
            topic_pause_sec=float(args.topic_pause_sec),
        )

    _log("=== Customer Feedback — Meta 99 all-remaining push ===")
    _log(f"Target: ~{args.target_hours:.0f}h | lang-batch={lang_batch} | topic-pause={args.topic_pause_sec}s")
    if skip_slugs:
        _log(f"Skipping industries: {', '.join(skip_slugs)}")
    _log(f"Remaining rows (all industries): {plan['total_remaining_rows']}")
    _log(f"Computed delay: {plan['computed_delay_sec']}s/row (linked rows use {args.linked_delay_sec}s)")
    _log(f"Estimated duration: ~{plan['estimated_hours']}h")
    _log("")
    for item in plan["industries"]:
        flag = "IN PROGRESS" if item["in_progress"] else "pending"
        _log(
            f"  {item['slug']:12} {item['remaining_rows']:4}/{item['total_rows']} rows  "
            f"topic {item['topic_index']+1} offset {item['lang_offset']}  [{flag}]"
        )

    if args.status or args.dry_run:
        if global_state:
            _log(f"\nGlobal state: {GLOBAL_STATE_PATH}")
            _log(json.dumps(global_state, indent=2))
        return 0

    if plan["total_remaining_rows"] == 0:
        _log("\nNothing left to push — all industries complete.")
        if GLOBAL_STATE_PATH.exists():
            GLOBAL_STATE_PATH.unlink()
        return 0

    if not global_state.get("started_at"):
        global_state = {
            "started_at": _utc_now(),
            "completed_industries": completed,
            "runs": 0,
            "consecutive_failures": 0,
            "pacing": {
                "target_hours": args.target_hours,
                "delay_sec": plan["computed_delay_sec"],
                "lang_batch": lang_batch,
                "topic_pause_sec": args.topic_pause_sec,
            },
        }
        _save_json(GLOBAL_STATE_PATH, global_state)

    delay_sec = float(global_state.get("pacing", {}).get("delay_sec") or plan["computed_delay_sec"])
    failures = int(global_state.get("consecutive_failures") or 0)

    industries = plan["industries"]
    pending_slugs = [item["slug"] for item in industries if item["remaining_rows"] > 0]

    for slug in pending_slugs:
        if slug in completed:
            continue

        item = next(x for x in industries if x["slug"] == slug)
        _log(f"\n{'=' * 60}")
        _log(f"Industry: {slug} — {item['remaining_rows']} rows remaining")

        while slug not in completed:
            global_state["runs"] = int(global_state.get("runs") or 0) + 1
            global_state["current_industry"] = slug
            _save_json(GLOBAL_STATE_PATH, global_state)

            ec, output = _run_chunk(
                industry_slug=slug,
                delay_sec=delay_sec,
                linked_delay_sec=float(args.linked_delay_sec),
                lang_batch=lang_batch,
                topic_pause_sec=float(args.topic_pause_sec),
                dry_run=False,
            )

            if ec != 0:
                failures += 1
                rate_limited = bool(RATE_LIMIT_RE.search(output))
                pause = _failure_pause_sec(
                    failures=failures,
                    rate_limited=rate_limited,
                    base=int(args.retry_base_sec),
                    cap=int(args.retry_cap_sec),
                )
                global_state["consecutive_failures"] = failures
                global_state["last_error"] = output[-500:]
                global_state["last_failure_at"] = _utc_now()
                _save_json(GLOBAL_STATE_PATH, global_state)

                kind = "rate-limit" if rate_limited else "error"
                _log(f"FAIL ({kind}) exit={ec} — retry same offset in {pause}s (failures={failures})")
                time.sleep(pause)
                continue

            failures = 0
            global_state["consecutive_failures"] = 0
            global_state["last_success_at"] = _utc_now()
            global_state.pop("last_error", None)
            _save_json(GLOBAL_STATE_PATH, global_state)

            if not _industry_state_path(slug).exists():
                _log(f"DONE industry: {slug}")
                completed = list(dict.fromkeys(completed + [slug]))
                global_state["completed_industries"] = completed
                _save_json(GLOBAL_STATE_PATH, global_state)
                break

            _log(f"Topic batch done for {slug} — pause {args.topic_pause_sec:.0f}s")
            time.sleep(float(args.topic_pause_sec))

    _log(f"\n{'=' * 60}")
    _log("ALL INDUSTRIES COMPLETE — Meta 99 CF push finished.")
    if GLOBAL_STATE_PATH.exists():
        final = _load_json(GLOBAL_STATE_PATH)
        final["finished_at"] = _utc_now()
        _save_json(GLOBAL_STATE_PATH, final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
