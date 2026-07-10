#!/usr/bin/env python3
"""Print Customer Feedback Meta 99 push progress table (read-only).

VPS:
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python scripts/cf_meta99_push_status.py
  python scripts/cf_meta99_push_status.py --skip-industries hotel

Shows per-industry rows/topics left, process status, ETA, and recent log lines.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATE_DIR = ROOT / "seed-data" / "customer-feedback" / "push-reports" / "chunk-state"
GLOBAL_STATE_PATH = STATE_DIR / "_meta99-all-push.json"
LOG_PATH = Path("/tmp/cf-meta99-all.log")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _industry_state_path(slug: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in slug)
    return STATE_DIR / f"{safe}.json"


def _lang_rows_for_industry(db, industry_id: str) -> tuple[int, list[int]]:
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
    counts: list[int] = []
    for topic in topics:
        rows = list(
            db.scalars(select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id == topic.id)).all()
        )
        counts.append(
            sum(1 for r in rows if not is_marketing_wa_template(r) and str(r.body_text or "").strip())
        )
    return len(topics), counts


def _remaining(topic_counts: list[int], state: dict) -> tuple[int, int, int, int]:
    topic_index = int(state.get("topic_index") or 0)
    lang_offset = int(state.get("lang_offset") or 0)
    total = sum(topic_counts)
    done = sum(topic_counts[:topic_index]) + lang_offset
    return done, max(0, total - done), topic_index, lang_offset


def _process_status() -> tuple[bool, str]:
    try:
        out = subprocess.check_output(["ps", "-eo", "cmd="], text=True, errors="replace")
    except Exception:
        return False, "unknown"
    orch = [ln for ln in out.splitlines() if "push_cf_all_remaining_meta.py" in ln and "grep" not in ln]
    chunk = [ln for ln in out.splitlines() if "push_cf_service_chunked.py" in ln and "grep" not in ln]
    if orch:
        return True, "orchestrator"
    if chunk:
        return True, "chunk-push"
    return False, "stopped"


def _fmt_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    sep = "  ".join("-" * w for w in widths)
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)), sep]
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="CF Meta 99 push status table")
    parser.add_argument("--skip-industries", default="hotel", help="Comma-separated slugs counted as done")
    parser.add_argument("--log-lines", type=int, default=8, help="Recent log lines to show")
    args = parser.parse_args()

    skip = {s.strip() for s in str(args.skip_industries or "").split(",") if s.strip()}
    global_state = _load_json(GLOBAL_STATE_PATH)
    completed = set(global_state.get("completed_industries") or []) | skip

    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.customer_feedback import FeedbackIndustry

    running, run_kind = _process_status()

    with get_sessionmaker()() as db:
        industries = list(
            db.scalars(
                select(FeedbackIndustry)
                .where(FeedbackIndustry.is_active.is_(True))
                .order_by(FeedbackIndustry.sort_order, FeedbackIndustry.name)
            ).all()
        )

        table_rows: list[list[str]] = []
        grand_total = 0
        grand_done = 0
        grand_left = 0
        pacing = global_state.get("pacing") or {}

        for ind in industries:
            n_topics, topic_counts = _lang_rows_for_industry(db, ind.id)
            total = sum(topic_counts)
            grand_total += total

            if ind.slug in completed:
                status = "DONE (skip)" if ind.slug in skip else "DONE"
                done, left, t_idx, l_off = total, 0, n_topics, 0
                topic_label = "-"
            else:
                state = _load_json(_industry_state_path(ind.slug))
                done, left, t_idx, l_off = _remaining(topic_counts, state)
                if left == 0 and not state:
                    status = "DONE"
                elif state or (global_state.get("current_industry") == ind.slug and running):
                    status = "IN PROGRESS"
                    topic_label = f"{t_idx + 1}/{n_topics}"
                    if l_off:
                        topic_label += f" +{l_off} langs"
                else:
                    status = "PENDING"
                    topic_label = f"0/{n_topics}"

            if ind.slug in skip:
                grand_done += total
            else:
                grand_done += done
                grand_left += left

            pct = f"{(100 * done / total):.0f}%" if total else "0%"
            table_rows.append(
                [
                    ind.slug,
                    status,
                    f"{done}/{total}",
                    pct,
                    topic_label if ind.slug not in completed or status == "IN PROGRESS" else "-",
                    str(left),
                ]
            )

    pct_all = f"{(100 * grand_done / grand_total):.1f}%" if grand_total else "0%"
    delay = pacing.get("delay_sec", "?")
    target_h = pacing.get("target_hours", "?")
    sec_row = float(delay) + 3.0 if isinstance(delay, (int, float)) else 27.0
    eta_h = round((grand_left * sec_row) / 3600.0, 1)

    print()
    print("=" * 72)
    print("  CUSTOMER FEEDBACK — META 99 PUSH STATUS")
    print(f"  Checked: {_utc_now()}")
    print("=" * 72)
    print()
    print(
        _fmt_table(
            ["Industry", "Status", "Rows done", "Pct", "Topic", "Left"],
            table_rows,
        )
    )
    print()
    print(f"  TOTAL:     {grand_done}/{grand_total} rows  ({pct_all})")
    print(f"  REMAINING: {grand_left} rows  (~{eta_h}h at {delay}s/row)")
    print(f"  PROCESS:   {'RUNNING (' + run_kind + ')' if running else 'NOT RUNNING'}")
    if global_state.get("started_at"):
        print(f"  STARTED:   {global_state.get('started_at')}")
    if global_state.get("current_industry"):
        print(f"  CURRENT:   {global_state.get('current_industry')}")
    if global_state.get("consecutive_failures"):
        print(f"  FAILURES:  {global_state.get('consecutive_failures')} consecutive (auto-retry)")
    if global_state.get("last_success_at"):
        print(f"  LAST OK:   {global_state.get('last_success_at')}")
    print()
    print("  MONITOR COMMANDS (VPS):")
    print("    python scripts/cf_meta99_push_status.py --skip-industries hotel")
    print("    tail -f /tmp/cf-meta99-all.log")
    print("    tmux attach -t cf-meta99")
    print()

    if LOG_PATH.exists() and args.log_lines > 0:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-args.log_lines :]
        if tail:
            print("  RECENT LOG:")
            for ln in tail:
                print(f"    {ln}")
            print()

    if not running and grand_left > 0:
        print("  WARNING: push not running but rows remain — restart with:")
        print("    tmux attach -t cf-meta99")
        print("    python -u scripts/push_cf_all_remaining_meta.py --target-hours 24 --skip-industries hotel")
        print()

    if grand_left == 0:
        print("  ALL DONE — Meta 99 CF push complete for configured industries.")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
