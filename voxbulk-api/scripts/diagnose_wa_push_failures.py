#!/usr/bin/env python3
"""Diagnose buttoned WA Survey templates not on Meta — group errors by bucket.

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python3 scripts/diagnose_wa_push_failures.py
  python3 scripts/diagnose_wa_push_failures.py --industry-slug employee_survey
  python3 scripts/diagnose_wa_push_failures.py --try-prepare
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    _effective_components,
    prepare_components_for_telnyx_push,
)
from app.services.wa_template_meta_sync import parse_meta_error_from_provider_detail
from app.services.wa_template_utility_lint import lint_utility_template

from scripts.wa_not_pushed_lib import (
    is_not_on_meta,
    is_stale_approved_local,
    iter_survey_keeper_rows,
    row_summary,
    split_buttoned_buttonless,
)

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"


def _bucket_for_row(db, row, *, try_prepare: bool) -> tuple[str, str, dict]:
    summary = row_summary(db, row)
    detail = str(row.last_push_error or "").strip()
    meta: dict = {}

    if try_prepare:
        try:
            raw = _effective_components(row)
            prepared = prepare_components_for_telnyx_push(raw, row=row)
            body = next(
                (c for c in prepared if str(c.get("type") or "").upper() == "BODY"),
                None,
            )
            body_text = str(body.get("text") or "") if isinstance(body, dict) else ""
            buttons = [
                str(b.get("text") or "")
                for b in (
                    next(
                        (c.get("buttons") for c in prepared if str(c.get("type") or "").upper() == "BUTTONS"),
                        None,
                    )
                    or []
                )
                if isinstance(b, dict)
            ]
            lint = lint_utility_template(
                body=body_text,
                buttons=buttons,
                language=row.language,
                meta_category=row.category or "utility",
            )
            if not lint.ok:
                msgs = "; ".join(i.message for i in lint.issues)
                return "utility_lint", msgs, summary
        except SurveyWhatsappTemplateError as exc:
            payload = getattr(exc, "payload", None) or {}
            provider = str(payload.get("provider_error") or "")
            if provider:
                meta = parse_meta_error_from_provider_detail(provider)
            detail = str(exc)
            if meta.get("kind"):
                return str(meta.get("kind")), detail[:300], summary
            return "prepare_failed", detail[:300], summary

    if detail:
        if "being deleted" in detail.lower() or "language_deletion_lock" in detail.lower():
            return "language_deletion_lock", detail[:300], summary
        if "subcode=2388023" in detail or "2388023" in detail:
            return "language_deletion_lock", detail[:300], summary
        meta = parse_meta_error_from_provider_detail(detail)
        if meta.get("kind"):
            return str(meta.get("kind")), detail[:300], summary
        if "utility lint" in detail.lower():
            return "utility_lint", detail[:300], summary
        if "invalid parameter" in detail.lower():
            return "meta_invalid_parameter", detail[:300], summary
        if "not found for id" in detail.lower():
            return "stale_local_meta_id", detail[:300], summary
        return "stored_error", detail[:300], summary

    if is_stale_approved_local(row):
        rid = str(row.telnyx_record_id or "").strip() or "(empty)"
        return (
            "stale_approved_local_id",
            f"status=APPROVED but record id is not on Meta ({rid[:40]})",
            summary,
        )

    return "unknown_no_error", "No last_push_error — run push_wa_one_verbose.py", summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose not-pushed buttoned survey templates")
    parser.add_argument("--industry-slug", default="")
    parser.add_argument("--name-like", default="")
    parser.add_argument("--try-prepare", action="store_true", help="Run prepare + utility lint per row")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        try:
            keepers = iter_survey_keeper_rows(
                db,
                industry_slug=args.industry_slug.strip() or None,
                name_like=args.name_like.strip() or None,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        buttoned, buttonless = split_buttoned_buttonless(keepers)
        targets = [row for row in buttoned if is_not_on_meta(row)]

        buckets: dict[str, list[dict]] = defaultdict(list)
        for row in targets:
            bucket, error, summary = _bucket_for_row(db, row, try_prepare=args.try_prepare)
            buckets[bucket].append({**summary, "diagnosed_error": error})

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "buttoned_total": len(buttoned),
        "buttonless_skipped": len(buttonless),
        "not_on_meta_count": len(targets),
        "bucket_counts": {k: len(v) for k, v in sorted(buckets.items())},
        "buckets": {k: v for k, v in sorted(buckets.items())},
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORT_DIR / f"diagnose-not-pushed-{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Buttoned (in scope):   {len(buttoned)}")
    print(f"Buttonless (skipped):  {len(buttonless)}")
    print(f"Not on Meta:           {len(targets)}")
    print()
    for bucket, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
        print(f"  {bucket}: {len(items)}")
    print(f"\nReport: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
