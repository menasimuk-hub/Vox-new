#!/usr/bin/env python3
"""Convert remaining Meta MARKETING cfs_* to UTILITY using free version names.

Avoids 2388024 by consulting remote names when bumping versions.
Default dry-run; pass --apply to push+delete.

  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  PYTHONPATH=/www/voxbulk/voxbulk-api python /tmp/convert_remaining_cf_mkt.py
  PYTHONPATH=/www/voxbulk/voxbulk-api python /tmp/convert_remaining_cf_mkt.py --apply
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import datetime, timezone

from app.core.database import get_sessionmaker
from app.services.customer_feedback.feedback_telnyx_push_service import (
    _CFS_VERSION_RE,
    suggest_next_cfs_version_name,
)
from app.services.survey_wa_utility_rewrite_service import discover_remote_marketing_templates
from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService
from app.services.wa_marketing_purge_service import PurgePlanItem, apply_purge_plan
from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

SERVICE = "customer_feedback"


def _stem_version(name: str) -> tuple[str, int] | None:
    clean = str(name or "").strip().lower()
    m = _CFS_VERSION_RE.match(clean)
    if m:
        return m.group(1), int(m.group(2))
    m2 = re.match(r"^(.*)_v(\d+)$", clean)
    if not m2:
        return None
    return m2.group(1), int(m2.group(2))


def _remote_used_names(db, profile_id: str) -> set[str]:
    remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
        db,
        connection_profile_id=profile_id,
        service_code=SERVICE,
        allow_account_waba_fallback=False,
    )
    used: set[str] = set()
    for item in remote:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if name:
            used.add(name)
    return used


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--push-delay", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    db = get_sessionmaker()()
    try:
        primary = WaTemplateProfilePushService.resolve_primary_connection_profile_id(
            db, service_code=SERVICE
        )
        if not primary:
            print("ERROR: no primary CF profile")
            return 1

        used = _remote_used_names(db, primary)
        print(f"Remote cfs/all names tracked: {len(used)}")

        overview, candidates = discover_remote_marketing_templates(db, name_contains="cfs_")
        actionable = [c for c in candidates if c.get("actionable")]
        if args.limit and args.limit > 0:
            actionable = actionable[: args.limit]

        print(
            f"Marketing CF actionable: {len(actionable)} "
            f"(unique_remote={overview.get('unique_remote_marketing')})"
        )

        plan: list[PurgePlanItem] = []
        for item in actionable:
            remote_name = str(item.get("remote_name") or item.get("name") or "").strip()
            if not remote_name:
                continue
            fid = item.get("feedback_template_id") or item.get("id")
            lang = str(item.get("language") or item.get("remote_language") or "").strip() or None
            body = str(item.get("full_body") or item.get("body_preview") or "").strip()

            # Prefer next free version vs remote catalog
            bumped = suggest_next_cfs_version_name(remote_name, used_names=used)
            if not bumped or bumped.lower() == remote_name.lower():
                # force bump past highest remote for stem
                parsed = _stem_version(remote_name)
                if not parsed:
                    print(f"SKIP unparseable {remote_name}")
                    continue
                stem, ver = parsed
                nxt = ver + 1
                while f"{stem}_v{nxt}" in used:
                    nxt += 1
                bumped = f"{stem}_v{nxt}"

            used.add(bumped.lower())
            print(f"PLAN {remote_name} -> {bumped} (lang={lang})")
            plan.append(
                PurgePlanItem(
                    action="feedback_rewrite_push",
                    product="feedback",
                    label=remote_name,
                    old_meta_name=remote_name,
                    new_meta_name=bumped,
                    local_template_id=str(fid) if fid else None,
                    language=lang,
                    dry_preview={
                        "body_before": body,
                        "body_after": body,  # keep body; category change via new UTILITY name
                        "new_local_name": bumped,
                        "delete_old_remote_name": remote_name,
                    },
                    meta={
                        "remote_name": remote_name,
                        "manifest_item": True,
                        "keeps_local_db_row": True,
                    },
                )
            )

        print(f"\nPlan size: {len(plan)} | mode={'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"At: {datetime.now(timezone.utc).isoformat()}")
        if not plan:
            print("Nothing to do.")
            return 0
        if not args.apply:
            print("Dry-run only. Re-run with --apply to push+delete.")
            return 0

        results = apply_purge_plan(
            db,
            plan,
            dry_run=False,
            push=True,
            sync_remote=True,
            use_llm=False,
            push_delay_seconds=max(0.0, float(args.push_delay)),
            batch_id="remaining-cf-mkt-free-bump",
        )
        ok = sum(1 for r in results if r.get("ok"))
        fail = len(results) - ok
        print(f"\nDONE ok={ok} fail={fail}")
        for r in results:
            if not r.get("ok"):
                print(f"  FAIL {r.get('label')}: {r.get('error')}")
        return 0 if fail == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
