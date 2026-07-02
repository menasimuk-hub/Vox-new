#!/usr/bin/env python3
"""Retry failed templates from a migration-phaseN-*.json report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_utility_rewrite_service import process_template_names


def _latest_report(phase: int) -> Path:
    reports = sorted((ROOT / "seed-data" / "wa-survey" / "migration-reports").glob(f"migration-phase{phase}-*.json"))
    if not reports:
        raise SystemExit(f"No migration-phase{phase}-*.json report found")
    return reports[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry failed WA UTILITY migration templates from JSON report")
    parser.add_argument("--phase", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--report", help="Path to migration report JSON (default: latest for phase)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--push-delay", type=float, default=1.5)
    args = parser.parse_args()

    if args.push:
        args.save = True
    if not args.dry_run and not args.save and not args.push:
        parser.error("Specify --dry-run, --save, and/or --push")

    report_path = Path(args.report) if args.report else _latest_report(args.phase)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    report = payload.get("report") or {}
    failed = [r for r in (report.get("results") or []) if not r.get("ok")]
    names = [str(r.get("template_name") or "").strip() for r in failed]
    names = [n for n in names if n]
    if not names:
        print(f"No failures in {report_path}")
        return 0

    print(f"Retry {len(names)} failed template(s) from {report_path}")
    with get_sessionmaker()() as db:
        results = process_template_names(
            db,
            names,
            save=args.save and not args.dry_run,
            push=args.push and not args.dry_run,
            dry_run=args.dry_run,
            skip_already_pushed=False,
            push_delay_seconds=max(0.0, float(args.push_delay or 0)),
        )

    ok = sum(1 for r in results if r.ok)
    fail = sum(1 for r in results if not r.ok)
    print(f"Done: {ok} ok, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
