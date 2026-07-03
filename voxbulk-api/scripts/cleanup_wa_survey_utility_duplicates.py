#!/usr/bin/env python3
"""Clean duplicate WA survey templates on Meta: retire old *_abc_*, resubmit REJECTED *_utu_*.

Topics 21–25 share the same slug across 14 industries — Meta shows many similar names; that is
expected (~84 rows). Problems to fix:
  - Old *_abc_* still on Meta after *_utu_* UTILITY push (delete remote + deactivate DB row)
  - REJECTED *_utu_* (rewrite + push again)
  - Extra duplicate *_utu_* remote rows (keep best status, delete extras)

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/cleanup_wa_survey_utility_duplicates.py --list
  python scripts/cleanup_wa_survey_utility_duplicates.py --retire-abc --dry-run
  python scripts/cleanup_wa_survey_utility_duplicates.py --retire-abc
  python scripts/cleanup_wa_survey_utility_duplicates.py --resubmit-rejected
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_utility_rewrite_service import apply_utility_rewrite_to_row
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _has_remote_telnyx_id,
)
from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService
from app.services.wa_template_meta_sync import is_utility_clone_template_name

SHARED_TOPIC_SLUGS: tuple[str, ...] = (
    "information_clarity",
    "overall_experience_today",
    "issue_resolution_rating",
    "hand_off_wait_time",
    "facility_access_comfort",
    "overall_service_satisfaction",
)


def _matches_shared_topic(name: str) -> bool:
    lower = str(name or "").lower()
    return any(f"_{slug}_" in lower for slug in SHARED_TOPIC_SLUGS)


def _is_abc_name(name: str) -> bool:
    return "_abc_" in str(name or "").lower()


def _remote_status_rank(status: str) -> int:
    s = str(status or "").upper()
    return {"APPROVED": 0, "PENDING": 1, "REJECTED": 2}.get(s, 9)


def cmd_list(db) -> int:
    remote = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(db, filter_waba_id=True)
    by_name: dict[str, list[dict]] = defaultdict(list)
    for item in remote:
        name = str(item.get("name") or "")
        if not _matches_shared_topic(name):
            continue
        by_name[name.lower()].append(item)

    print(f"Telnyx templates matching shared topics 21–25: {sum(len(v) for v in by_name.values())}")
    print(f"Unique names: {len(by_name)}\n")
    dup_names = {k: v for k, v in by_name.items() if len(v) > 1}
    if dup_names:
        print(f"WARNING: {len(dup_names)} name(s) with multiple remote rows:")
        for name, items in sorted(dup_names.items())[:30]:
            for it in items:
                print(f"  DUP {it.get('name')} status={it.get('status')} cat={it.get('category')} id={it.get('id')}")
        print()

    abc = rejected = utu_ok = 0
    for name, items in sorted(by_name.items()):
        item = sorted(items, key=lambda x: _remote_status_rank(str(x.get("status") or "")))[0]
        status = str(item.get("status") or "").upper()
        cat = str(item.get("category") or "").upper()
        if _is_abc_name(name):
            abc += 1
            print(f"  ABC  {item.get('name')} | {status} | {cat}")
        elif status == "REJECTED":
            rejected += 1
            print(f"  REJ  {item.get('name')} | {cat} | {item.get('rejection_reason', '')[:80]}")
        elif is_utility_clone_template_name(name) and status in {"APPROVED", "PENDING"}:
            utu_ok += 1
    print(f"\nSummary: abc_orphans={abc} rejected_utu={rejected} utu_ok={utu_ok}")
    return 0


def cmd_retire_abc(db, *, dry_run: bool) -> int:
    rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(
                TelnyxWhatsappTemplate.step_role == "abc_choice",
                TelnyxWhatsappTemplate.survey_type_id.isnot(None),
            )
        ).scalars()
    )
    by_survey: dict[str, list[TelnyxWhatsappTemplate]] = defaultdict(list)
    for row in rows:
        if not _matches_shared_topic(row.name):
            continue
        by_survey[str(row.survey_type_id)].append(row)

    retired = 0
    for _st_id, group in sorted(by_survey.items()):
        utu_good = [
            r
            for r in group
            if is_utility_clone_template_name(r.name)
            and str(r.category or "").upper() == "UTILITY"
            and str(r.status or "").upper() in {"APPROVED", "PENDING"}
            and _has_remote_telnyx_id(r)
        ]
        if not utu_good:
            continue
        for row in group:
            if not _is_abc_name(row.name):
                continue
            if not _has_remote_telnyx_id(row):
                if row.active_for_survey and not dry_run:
                    row.active_for_survey = False
                    db.add(row)
                continue
            print(f"{'[dry-run] ' if dry_run else ''}retire ABC {row.name} (keep {utu_good[0].name})")
            if not dry_run:
                try:
                    TelnyxWhatsappTemplateSyncService.delete_remote_template(
                        db, str(row.telnyx_record_id or "")
                    )
                except Exception as exc:
                    print(f"  WARN delete failed: {exc}")
                row.active_for_survey = False
                row.last_push_error = None
                db.add(row)
            retired += 1
    if not dry_run:
        db.commit()
    print(f"\n{'Would retire' if dry_run else 'Retired'} {retired} old *_abc_* remote template(s)")
    return 0


def cmd_resubmit_rejected(db, *, dry_run: bool) -> int:
    rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(
                TelnyxWhatsappTemplate.step_role == "abc_choice",
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
        ).scalars()
    )
    targets = [
        r
        for r in rows
        if str(r.status or "").upper() == "REJECTED"
        and _matches_shared_topic(r.name)
        and str(r.category or "").upper() == "UTILITY"
    ]
    if not targets:
        print("No active REJECTED UTILITY rows for shared topics.")
        return 0

    ok = fail = 0
    for row in targets:
        print(f"{'[dry-run] ' if dry_run else ''}resubmit {row.name} …")
        if dry_run:
            ok += 1
            continue
        try:
            apply_utility_rewrite_to_row(db, row, use_llm=False)
            SurveyWhatsappTemplateService.push_to_telnyx(db, row)
            db.refresh(row)
            print(f"  -> OK status={row.status}")
            ok += 1
        except SurveyWhatsappTemplateError as exc:
            print(f"  -> FAIL {exc}")
            fail += 1
    print(f"\nDone: {ok} ok, {fail} failed")
    return 1 if fail else 0


def cmd_dedupe_remote(db, *, dry_run: bool) -> int:
    remote = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(db, filter_waba_id=True)
    by_name: dict[str, list[dict]] = defaultdict(list)
    for item in remote:
        name = str(item.get("name") or "").lower()
        if not _matches_shared_topic(name):
            continue
        by_name[name].append(item)

    deleted = 0
    for name, items in by_name.items():
        if len(items) < 2:
            continue
        sorted_items = sorted(items, key=lambda x: _remote_status_rank(str(x.get("status") or "")))
        keep = sorted_items[0]
        for extra in sorted_items[1:]:
            rid = str(extra.get("id") or "")
            print(
                f"{'[dry-run] ' if dry_run else ''}delete duplicate remote {extra.get('name')} "
                f"status={extra.get('status')} (keep {keep.get('id')})"
            )
            if not dry_run and rid:
                try:
                    TelnyxWhatsappTemplateSyncService.delete_remote_template(db, rid)
                    deleted += 1
                except Exception as exc:
                    print(f"  WARN {exc}")
    print(f"\n{'Would delete' if dry_run else 'Deleted'} {deleted} duplicate remote row(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup WA survey UTILITY duplicates on Meta")
    parser.add_argument("--list", action="store_true", help="List shared-topic templates on Telnyx")
    parser.add_argument("--retire-abc", action="store_true", help="Delete *_abc_* from Meta when *_utu_* exists")
    parser.add_argument("--resubmit-rejected", action="store_true", help="Rewrite + push REJECTED UTILITY rows")
    parser.add_argument("--dedupe-remote", action="store_true", help="Delete extra remote rows with same name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not any([args.list, args.retire_abc, args.resubmit_rejected, args.dedupe_remote]):
        parser.error("Specify --list, --retire-abc, --resubmit-rejected, and/or --dedupe-remote")

    with get_sessionmaker()() as db:
        if args.list:
            return cmd_list(db)
        code = 0
        if args.retire_abc:
            code = max(code, cmd_retire_abc(db, dry_run=args.dry_run))
        if args.dedupe_remote:
            code = max(code, cmd_dedupe_remote(db, dry_run=args.dry_run))
        if args.resubmit_rejected:
            code = max(code, cmd_resubmit_rejected(db, dry_run=args.dry_run))
        return code


if __name__ == "__main__":
    raise SystemExit(main())
