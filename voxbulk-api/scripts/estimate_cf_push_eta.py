#!/usr/bin/env python3
"""Estimate remaining time for chunked CF industry push (read state + log).

VPS:
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python scripts/estimate_cf_push_eta.py hotel
  python scripts/estimate_cf_push_eta.py hotel --lang-batch 2 --delay-sec 30 --profile-delay-sec 60 --topic-pause-sec 90
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

STATE_DIR = ROOT / "seed-data" / "customer-feedback" / "push-reports" / "chunk-state"


def _secs_per_lang_row(*, delay_sec: float, profile_delay_sec: float, lang_batch: int) -> float:
    """Meta + Telnyx per language row (average when batched)."""
    meta = delay_sec + 3.0
    telnyx = delay_sec + 3.0
    profile_share = profile_delay_sec / max(1, lang_batch)
    return meta + telnyx + profile_share


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate CF chunked push ETA for one industry")
    parser.add_argument("industry_slug", help="e.g. hotel")
    parser.add_argument("--lang-batch", type=int, default=2)
    parser.add_argument("--delay-sec", type=float, default=30.0)
    parser.add_argument("--profile-delay-sec", type=float, default=60.0)
    parser.add_argument("--topic-pause-sec", type=float, default=90.0)
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.services.customer_feedback.feedback_telnyx_push_service import resolve_feedback_industry

    slug = str(args.industry_slug).strip()
    state_path = STATE_DIR / f"{slug}.json"

    if not state_path.exists():
        print(f"DONE or not started: no state file at {state_path}")
        print("If push is running, wait for first topic batch to finish saving state.")
        return 0

    state = json.loads(state_path.read_text(encoding="utf-8"))
    updated = state.get("updated_at", "?")

    with get_sessionmaker()() as db:
        industry = resolve_feedback_industry(db, industry_slug=slug)
        from sqlalchemy import select

        from app.models.customer_feedback import FeedbackSurveyType, FeedbackWaTemplate
        from app.services.customer_feedback.feedback_telnyx_push_service import is_marketing_wa_template

        topics = list(
            db.scalars(
                select(FeedbackSurveyType)
                .where(FeedbackSurveyType.industry_id == industry.id)
                .order_by(FeedbackSurveyType.sort_order, FeedbackSurveyType.name)
            ).all()
        )

        def lang_rows(survey_type_id: str) -> int:
            rows = list(
                db.scalars(
                    select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id == survey_type_id)
                ).all()
            )
            return sum(
                1
                for r in rows
                if not is_marketing_wa_template(r) and str(r.body_text or "").strip()
            )

        topic_langs = [lang_rows(t.id) for t in topics]

    total_topics = len(topics)
    total_rows = sum(topic_langs)
    topic_index = int(state.get("topic_index") or 0)
    lang_offset = int(state.get("lang_offset") or 0)
    topic_slug = str(state.get("topic_slug") or (topics[topic_index].slug if topic_index < total_topics else "?"))

    done_rows = sum(topic_langs[:topic_index]) + lang_offset
    remaining_rows = max(0, total_rows - done_rows)

    sec_row = _secs_per_lang_row(
        delay_sec=args.delay_sec,
        profile_delay_sec=args.profile_delay_sec,
        lang_batch=max(1, args.lang_batch),
    )
    remaining_topics_after_current = max(0, total_topics - topic_index - (1 if lang_offset >= topic_langs[topic_index] else 0))
    topic_pauses = max(0, total_topics - topic_index - 1) * args.topic_pause_sec

    eta_sec = remaining_rows * sec_row + topic_pauses
    eta_h = eta_sec / 3600.0

    pct = round(100.0 * done_rows / total_rows, 1) if total_rows else 0.0

    print(f"Industry: {industry.name} ({slug})")
    print(f"State updated: {updated}")
    print(f"Progress: topic {topic_index + 1}/{total_topics} ({topic_slug}), lang offset {lang_offset}")
    print(f"Rows: {done_rows}/{total_rows} pushed ({pct}%) — {remaining_rows} remaining")
    print(f"Assumed pacing: lang-batch={args.lang_batch}, delay={args.delay_sec}s, profile-delay={args.profile_delay_sec}s, topic-pause={args.topic_pause_sec}s")
    print(f"Estimated remaining: ~{eta_h:.1f} hours ({int(eta_sec // 60)} minutes)")
    if lang_offset < topic_langs[topic_index]:
        left_this_topic = topic_langs[topic_index] - lang_offset
        print(f"Current topic '{topic_slug}': {left_this_topic} language rows left (~{left_this_topic * sec_row / 60:.0f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
