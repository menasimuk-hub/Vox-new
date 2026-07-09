#!/usr/bin/env python3
"""Push Customer Feedback templates in small chunks (Meta primary → Telnyx backup).

One invocation = small work unit — avoids Meta rate limits / spam flags.

Typical pattern: one industry topic (~20 langs) per run, languages in sub-batches of 3.

VPS (production server)
-----------------------
SSH to the server, then:

  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  git pull origin main   # if script was just pushed

List industries / topics (pick what to push):

  python scripts/push_cf_service_chunked.py --list-industries
  python scripts/push_cf_service_chunked.py --list-topics --industry-slug hotel

Dry run (no Meta/Telnyx POST):

  python scripts/push_cf_service_chunked.py --industry-slug hotel --dry-run

One topic, 3 languages per batch, 20s pause (safe default):

  python scripts/push_cf_service_chunked.py --industry-slug hotel --topics-per-run 1 --lang-batch 3 --delay-sec 20

Auto-advance topics using saved state (run repeatedly until done):

  python scripts/push_cf_service_chunked.py --industry-slug hotel --continue
  python scripts/push_cf_service_chunked.py --industry-slug hotel --continue

Background + log:

  nohup python -u scripts/push_cf_service_chunked.py \\
    --industry-slug hotel --continue --lang-batch 3 --delay-sec 20 \\
    > /tmp/cf-chunk-$(date +%Y%m%d-%H%M).log 2>&1 &
  tail -f /tmp/cf-chunk-*.log

Local Windows (dev DB only — usually no real Meta credentials):

  cd voxbulk-api
  .\\.venv\\Scripts\\Activate.ps1
  python scripts/push_cf_service_chunked.py --list-industries
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

REPORT_DIR = ROOT / "seed-data" / "customer-feedback" / "push-reports"
STATE_DIR = REPORT_DIR / "chunk-state"


def _configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
        except Exception:
            pass


def _log(msg: str, *, err: bool = False) -> None:
    print(msg, file=sys.stderr if err else sys.stdout, flush=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _state_path(industry_slug: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in industry_slug)
    return STATE_DIR / f"{safe}.json"


def _load_state(industry_slug: str) -> dict:
    path = _state_path(industry_slug)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(industry_slug: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    _state_path(industry_slug).write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _list_industries(db) -> None:
    from sqlalchemy import select

    from app.models.customer_feedback import FeedbackIndustry

    rows = db.scalars(
        select(FeedbackIndustry).order_by(FeedbackIndustry.sort_order, FeedbackIndustry.name)
    ).all()
    _log("Customer Feedback industries:")
    for row in rows:
        _log(f"  {row.slug:20}  {row.name}  (id={row.id})")


def _list_topics(db, industry_slug: str) -> None:
    from app.services.customer_feedback.feedback_telnyx_push_service import resolve_feedback_industry

    industry = resolve_feedback_industry(db, industry_slug=industry_slug)
    topics = _topics_for_industry(db, industry.id)
    _log(f"Topics for {industry.name} ({industry.slug}):")
    for topic in topics:
        total = len(_templates_for_topic(db, topic.id))
        _log(f"  {topic.slug:28}  {topic.name or topic.slug}  ({total} lang rows)")


def _topics_for_industry(db, industry_id: str):
    from sqlalchemy import select

    from app.models.customer_feedback import FeedbackSurveyType

    return list(
        db.scalars(
            select(FeedbackSurveyType)
            .where(FeedbackSurveyType.industry_id == industry_id)
            .order_by(FeedbackSurveyType.sort_order, FeedbackSurveyType.name)
        ).all()
    )


def _templates_for_topic(db, survey_type_id: str):
    from sqlalchemy import select

    from app.models.customer_feedback import FeedbackWaTemplate
    from app.services.customer_feedback.feedback_telnyx_push_service import is_marketing_wa_template

    rows = list(
        db.scalars(
            select(FeedbackWaTemplate)
            .where(FeedbackWaTemplate.survey_type_id == survey_type_id)
            .order_by(FeedbackWaTemplate.language)
        ).all()
    )
    return [r for r in rows if not is_marketing_wa_template(r) and str(r.body_text or "").strip()]


def _push_lang_slice(
    db,
    templates: list,
    *,
    start: int,
    lang_batch: int,
    primary_id: str,
    backup_id: str,
    dry_run: bool,
    delay_sec: float,
    profile_delay_sec: float,
    force_meta: bool,
    force_backup: bool,
) -> dict:
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        FeedbackTelnyxPushError,
        push_feedback_template_to_telnyx,
    )
    from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

    slice_rows = templates[start : start + lang_batch]
    if not slice_rows:
        return {
            "ok": True,
            "pushed_primary": 0,
            "pushed_backup": 0,
            "linked_primary": 0,
            "linked_backup": 0,
            "failed": 0,
            "errors": [],
            "has_more_langs": False,
            "next_lang_offset": start,
        }

    totals = {
        "pushed_primary": 0,
        "pushed_backup": 0,
        "linked_primary": 0,
        "linked_backup": 0,
        "failed": 0,
        "errors": [],
    }

    def _push_profile(profile_id: str, *, force_push: bool, label: str) -> None:
        remote_items = None
        if not dry_run:
            try:
                remote_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
                    db,
                    connection_profile_id=profile_id,
                    service_code="customer_feedback",
                    allow_account_waba_fallback=False,
                )
            except Exception as exc:
                _log(f"  [{label}] prefetch warn: {str(exc)[:120]}")

        for tpl in slice_rows:
            lang = str(tpl.language or "")
            name_hint = str(tpl.template_key or tpl.id)
            try:
                result = push_feedback_template_to_telnyx(
                    db,
                    tpl,
                    dry_run=dry_run,
                    remote_items=remote_items,
                    connection_profile_id=profile_id,
                    service_code="customer_feedback",
                    force_push=force_push,
                )
                key = "pushed_primary" if label == "Meta" else "pushed_backup"
                totals[key] += 1
                if result.get("linked") or result.get("skipped_push"):
                    link_key = "linked_primary" if label == "Meta" else "linked_backup"
                    totals[link_key] += 1
                outcome = result.get("message") or ("dry-run" if dry_run else "ok")
                _log(f"  [{label}] {lang} {name_hint}: {outcome}")
            except FeedbackTelnyxPushError as exc:
                totals["failed"] += 1
                err = {"language": lang, "template_key": name_hint, "profile": label, "error": str(exc)}
                totals["errors"].append(err)
                _log(f"  [{label}] FAIL {lang} {name_hint}: {exc}")
            if delay_sec > 0 and not dry_run:
                time.sleep(delay_sec)

    _log(f"  Primary Meta ({primary_id[:8]}…) — changed-only unless --force-meta")
    _push_profile(primary_id, force_push=force_meta, label="Meta")
    if not dry_run:
        db.commit()

    if profile_delay_sec > 0 and not dry_run:
        _log(f"  Waiting {profile_delay_sec:.0f}s before Telnyx mirror…")
        time.sleep(profile_delay_sec)

    _log(f"  Backup Telnyx ({backup_id[:8]}…) — mirror")
    _push_profile(backup_id, force_push=force_backup, label="Telnyx")
    if not dry_run:
        db.commit()

    next_offset = start + len(slice_rows)
    return {
        **totals,
        "ok": totals["failed"] == 0,
        "has_more_langs": next_offset < len(templates),
        "next_lang_offset": next_offset,
    }


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="Chunked Customer Feedback push — one small unit per run (Meta → Telnyx)"
    )
    parser.add_argument("--list-industries", action="store_true", help="Print industry slugs and exit")
    parser.add_argument("--list-topics", action="store_true", help="Print topic slugs for --industry-slug")
    parser.add_argument("--industry-slug", help="Industry slug (required unless --list-industries)")
    parser.add_argument("--topic-slug", help="Push only this topic slug (default: next from state or first)")
    parser.add_argument(
        "--topics-per-run",
        type=int,
        default=1,
        help="How many topics to finish per invocation (default 1)",
    )
    parser.add_argument(
        "--lang-batch",
        type=int,
        default=3,
        help="Language rows per sub-batch within a topic (default 3, max 10)",
    )
    parser.add_argument(
        "--delay-sec",
        type=float,
        default=15.0,
        help="Pause after each language row POST (default 15s)",
    )
    parser.add_argument(
        "--profile-delay-sec",
        type=float,
        default=30.0,
        help="Pause between Meta primary and Telnyx backup for same slice (default 30s)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate only — no provider POST")
    parser.add_argument(
        "--continue",
        dest="continue_run",
        action="store_true",
        help="Resume topic/lang offset from state file for this industry",
    )
    parser.add_argument("--reset-state", action="store_true", help="Clear saved state for --industry-slug")
    parser.add_argument(
        "--force-meta",
        action="store_true",
        help="Re-push on Meta even if already linked (default: changed/missing only)",
    )
    parser.add_argument(
        "--force-backup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Full mirror on Telnyx backup (default: on). Use --no-force-backup for changed-only.",
    )
    parser.add_argument("--pull-after-topic", action="store_true", help="Pull Meta status after each topic completes")
    parser.add_argument("--json", action="store_true", help="Print report JSON")
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        FeedbackTelnyxPushError,
        push_feedback_templates_batch,
        resolve_feedback_industry,
    )
    from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

    lang_batch = max(1, min(int(args.lang_batch), 10))
    topics_per_run = max(1, int(args.topics_per_run))

    with get_sessionmaker()() as db:
        if args.list_industries:
            _list_industries(db)
            return 0

        if not args.industry_slug:
            parser.error("--industry-slug is required (or use --list-industries)")

        if args.list_topics:
            _list_topics(db, args.industry_slug)
            return 0

        if args.reset_state:
            path = _state_path(args.industry_slug)
            if path.exists():
                path.unlink()
            _log(f"Cleared state: {path}")
            return 0

        primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(
            db, service_code="customer_feedback"
        )
        backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(
            db, service_code="customer_feedback"
        )
        if not primary_id or not backup_id:
            _log("ERROR: customer_feedback Meta primary and Telnyx backup profiles must be configured.", err=True)
            return 1

        industry = resolve_feedback_industry(db, industry_slug=args.industry_slug)
        topics = _topics_for_industry(db, industry.id)
        if not topics:
            _log(f"No topics for industry {args.industry_slug}", err=True)
            return 1

        state = _load_state(args.industry_slug) if args.continue_run else {}
        topic_index = int(state.get("topic_index") or 0)
        lang_offset = int(state.get("lang_offset") or 0)

        if args.topic_slug:
            topic_index = next((i for i, t in enumerate(topics) if t.slug == args.topic_slug), -1)
            if topic_index < 0:
                _log(f"Topic slug not found: {args.topic_slug}", err=True)
                return 1
            lang_offset = 0

        report = {
            "started_at": _utc_now(),
            "pid": os.getpid(),
            "cwd": str(Path.cwd()),
            "industry_slug": industry.slug,
            "industry_name": industry.name,
            "dry_run": bool(args.dry_run),
            "lang_batch": lang_batch,
            "delay_sec": args.delay_sec,
            "profiles": {"primary": primary_id, "backup": backup_id},
            "topics_done": [],
        }

        _log("=== Customer Feedback chunked push (service: customer_feedback) ===")
        _log(f"Industry: {industry.name} ({industry.slug})")
        _log(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        _log(f"Lang batch: {lang_batch}, delay: {args.delay_sec}s, profile delay: {args.profile_delay_sec}s")
        _log(f"Meta primary: {primary_id} | Telnyx backup: {backup_id}")

        topics_finished = 0
        stopped = False

        while topics_finished < topics_per_run and topic_index < len(topics):
            topic = topics[topic_index]
            templates = _templates_for_topic(db, topic.id)
            if not templates:
                _log(f"\n[{_utc_now()}] Skip empty topic {topic.slug}")
                topic_index += 1
                lang_offset = 0
                continue

            _log(f"\n[{_utc_now()}] Topic {topic_index + 1}/{len(topics)}: {topic.name} ({topic.slug})")
            _log(f"  Languages: {len(templates)} | starting offset {lang_offset}")

            topic_result = {
                "topic_slug": topic.slug,
                "topic_name": topic.name,
                "language_rows": len(templates),
                "batches": [],
            }

            while lang_offset < len(templates):
                batch_num = (lang_offset // lang_batch) + 1
                _log(f"  Lang batch {batch_num} offset={lang_offset} size={lang_batch}")
                batch_result = _push_lang_slice(
                    db,
                    templates,
                    start=lang_offset,
                    lang_batch=lang_batch,
                    primary_id=primary_id,
                    backup_id=backup_id,
                    dry_run=bool(args.dry_run),
                    delay_sec=float(args.delay_sec),
                    profile_delay_sec=float(args.profile_delay_sec),
                    force_meta=bool(args.force_meta),
                    force_backup=bool(args.force_backup),
                )
                topic_result["batches"].append(batch_result)
                lang_offset = int(batch_result.get("next_lang_offset") or lang_offset)

                _save_state(
                    args.industry_slug,
                    {
                        "industry_slug": industry.slug,
                        "topic_index": topic_index,
                        "topic_slug": topic.slug,
                        "lang_offset": lang_offset,
                        "incomplete": batch_result.get("has_more_langs", False),
                    },
                )

                if batch_result.get("failed"):
                    _log("  Stopping — failures in batch (fix and re-run with --continue)", err=True)
                    stopped = True
                    break

                if not batch_result.get("has_more_langs"):
                    break

            report["topics_done"].append(topic_result)

            if stopped:
                break

            if lang_offset >= len(templates):
                _log(f"  Topic complete: {topic.slug}")
                if args.pull_after_topic and not args.dry_run:
                    try:
                        pull = push_feedback_templates_batch(
                            db,
                            industry_id=industry.id,
                            phase="pull",
                            connection_profile_id=primary_id,
                            service_code="customer_feedback",
                        )
                        _log(f"  Pull status: {pull.get('message') or 'done'}")
                    except FeedbackTelnyxPushError as exc:
                        _log(f"  Pull warn: {exc}")

                topic_index += 1
                lang_offset = 0
                topics_finished += 1
                _save_state(
                    args.industry_slug,
                    {
                        "industry_slug": industry.slug,
                        "topic_index": topic_index,
                        "lang_offset": 0,
                        "last_completed_topic": topic.slug,
                        "incomplete": topic_index < len(topics),
                    },
                )

        all_done = topic_index >= len(topics)
        report["finished_at"] = _utc_now()
        report["all_topics_complete"] = all_done
        report["next_topic_index"] = topic_index
        report["stopped_early"] = stopped

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = REPORT_DIR / f"chunk-push-{industry.slug}-{stamp}.json"
        out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

        _log(f"\n{'=' * 60}")
        _log(f"Run finished: topics completed this run={topics_finished}")
        if all_done:
            _log(f"Industry {industry.slug} fully pushed.")
            if _state_path(args.industry_slug).exists():
                _state_path(args.industry_slug).unlink()
        else:
            nxt = topics[topic_index].slug if topic_index < len(topics) else "—"
            _log(f"Next run: python scripts/push_cf_service_chunked.py --industry-slug {industry.slug} --continue")
            _log(f"  Will resume topic: {nxt} lang_offset={lang_offset}")
        _log(f"Report: {out_path}")

        if args.json:
            _log(json.dumps(report, indent=2, default=str))

        if stopped:
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
