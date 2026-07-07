#!/usr/bin/env python3
"""Delete ALL WhatsApp templates on ONE connection profile's remote Meta WABA.

REMOTE-ONLY: touches Meta (Graph API) for the given profile's WABA. Never writes to
the local DB and never writes local files (unless --report is given). Hard-refuses the
Meta 99 profile / WABA / phone number id.

Usage (from voxbulk-api, venv active):
  # 1) DRY RUN — just count, delete nothing (default):
  python scripts/purge_profile_remote_wa_templates.py --profile-id <TELNYX_55_PROFILE_UUID>

  # 2) DELETE everything on that profile's WABA:
  python scripts/purge_profile_remote_wa_templates.py --profile-id <TELNYX_55_PROFILE_UUID> --apply --yes

Optional:
  --only-prefix voxbulk_survey_     # delete only names starting with this
  --exclude-prefix voxbulk_interview_ --exclude-prefix voxbulk_sales_   # repeatable
  --pause 0.3                       # seconds between delete calls (rate limit)
  --limit 100                       # cap number of delete calls (safety)
  --report /tmp/purge55.json        # write a JSON report (off by default)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.models.connection_profile import (
    CHANNEL_WHATSAPP,
    PROVIDER_META,
    ConnectionProfile,
)
from app.services.connection.profile_credentials import meta_config_from_profile
from app.services.meta_whatsapp_config_service import graph_api_base
from app.services.meta_whatsapp_service import MetaWhatsappService, MetaWhatsappServiceError

# --- Meta 99 = NEVER TOUCH (from docs/wa-template-sync-contract.md) ---
META99_PROFILE_ID = "b19c8d5b-2406-4bd0-8d56-610574ab491b"
META99_WABA_ID = "1033532842963987"
META99_PHONE_NUMBER_ID = "1307579342430096"


def _refuse_if_meta99(profile: ConnectionProfile, cfg: dict) -> None:
    if str(profile.id) == META99_PROFILE_ID:
        sys.exit("REFUSED: this is the Meta 99 profile id — aborting.")
    if str(cfg.get("waba_id") or "") == META99_WABA_ID:
        sys.exit(f"REFUSED: profile WABA {cfg.get('waba_id')} == Meta 99 WABA — aborting.")
    if str(cfg.get("phone_number_id") or "") == META99_PHONE_NUMBER_ID:
        sys.exit("REFUSED: profile phone_number_id == Meta 99 — aborting.")


def _fetch_all(cfg: dict) -> list[dict]:
    """Paginate all message templates for this WABA (name+language rows)."""
    waba_id = str(cfg.get("waba_id") or "").strip()
    rows: list[dict] = []
    after: str | None = None
    fields = "id,name,language,status,category"
    while True:
        params: dict = {"limit": 250, "fields": fields}
        if after:
            params["after"] = after
        payload = MetaWhatsappService._graph_request(
            config=cfg, method="GET", path=f"{waba_id}/message_templates", params=params
        )
        chunk = payload.get("data") if isinstance(payload.get("data"), list) else []
        rows.extend(x for x in chunk if isinstance(x, dict))
        paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
        cursors = paging.get("cursors") if isinstance(paging.get("cursors"), dict) else {}
        after = str(cursors.get("after") or "").strip() or None
        if not after or not paging.get("next"):
            break
    return rows


def _delete_by_name(cfg: dict, name: str) -> None:
    """Delete every language version of a template name on this WABA."""
    waba_id = str(cfg.get("waba_id") or "").strip()
    MetaWhatsappService._graph_request(
        config=cfg, method="DELETE", path=f"{waba_id}/message_templates", params={"name": name}
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge remote WA templates on ONE profile's Meta WABA")
    ap.add_argument("--profile-id", required=True, help="Connection profile UUID (e.g. Telnyx 55)")
    ap.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    ap.add_argument("--yes", action="store_true", help="Skip interactive confirmation")
    ap.add_argument("--only-prefix", default="", help="Only names starting with this prefix")
    ap.add_argument("--exclude-prefix", action="append", default=[], help="Skip names with this prefix (repeatable)")
    ap.add_argument("--pause", type=float, default=0.3, help="Seconds between delete calls")
    ap.add_argument("--limit", type=int, default=0, help="Max delete calls (0 = no cap)")
    ap.add_argument("--report", default="", help="Optional path to write a JSON report")
    args = ap.parse_args()

    db = get_sessionmaker()()
    try:
        profile = db.get(ConnectionProfile, str(args.profile_id).strip())
        if profile is None:
            sys.exit("Profile not found")
        if str(profile.channel or "").lower() != CHANNEL_WHATSAPP:
            sys.exit("Profile is not a WhatsApp channel profile")
        if profile.provider != PROVIDER_META:
            sys.exit(
                f"Profile provider is '{profile.provider}', not Meta. "
                "This script only deletes on Meta WABAs. Aborting to avoid hitting the wrong account."
            )

        cfg = meta_config_from_profile(profile)
        _refuse_if_meta99(profile, cfg)

        if not (cfg.get("access_token") and cfg.get("waba_id")):
            sys.exit("Profile is missing Meta access_token or waba_id — cannot proceed.")

        print("=== Target profile ===")
        print(f"  name          : {profile.name}")
        print(f"  provider      : {profile.provider}")
        print(f"  waba_id       : {cfg.get('waba_id')}")
        print(f"  phone_number  : {cfg.get('whatsapp_from') or profile.meta_whatsapp_from}")
        print(f"  graph base    : {graph_api_base(cfg)}")
        print()

        rows = _fetch_all(cfg)

        only = str(args.only_prefix or "").strip().lower()
        excludes = [str(p).strip().lower() for p in (args.exclude_prefix or []) if str(p).strip()]

        by_name: dict[str, list[dict]] = defaultdict(list)
        skipped_excluded: set[str] = set()
        for r in rows:
            nm = str(r.get("name") or "").strip()
            if not nm:
                continue
            nl = nm.lower()
            if only and not nl.startswith(only):
                continue
            if any(nl.startswith(p) for p in excludes):
                skipped_excluded.add(nm)
                continue
            by_name[nm].append(r)

        total_rows = sum(len(v) for v in by_name.values())
        names = sorted(by_name.keys())
        print(f"Templates on this WABA (after filters): {total_rows} rows across {len(names)} unique names")
        if skipped_excluded:
            print(f"Excluded by prefix: {len(skipped_excluded)} names")
        for nm in names[:15]:
            langs = ",".join(sorted(str(x.get("language") or "?") for x in by_name[nm]))
            print(f"  - {nm} [{langs}]")
        if len(names) > 15:
            print(f"  ... and {len(names) - 15} more names")
        print()

        report = {
            "at": datetime.now(timezone.utc).isoformat(),
            "profile_id": str(profile.id),
            "profile_name": profile.name,
            "waba_id": cfg.get("waba_id"),
            "total_rows": total_rows,
            "unique_names": len(names),
            "dry_run": not args.apply,
            "deleted": [],
            "errors": [],
        }

        if not args.apply:
            print("DRY RUN — nothing deleted. Re-run with --apply --yes to delete.")
        else:
            if not args.yes:
                confirm = input(f"Delete {len(names)} template names from WABA {cfg.get('waba_id')}? type DELETE: ")
                if confirm.strip() != "DELETE":
                    sys.exit("Aborted.")
            deleted = 0
            for nm in names:
                if args.limit and deleted >= args.limit:
                    print(f"Reached --limit {args.limit}; stopping.")
                    break
                try:
                    _delete_by_name(cfg, nm)
                    report["deleted"].append(nm)
                    deleted += 1
                    if deleted % 50 == 0:
                        print(f"  deleted {deleted}/{len(names)}...")
                except MetaWhatsappServiceError as exc:
                    report["errors"].append({"name": nm, "error": str(exc)[:300]})
                if args.pause:
                    time.sleep(args.pause)
            print(f"\nDone. Deleted {deleted} names, {len(report['errors'])} errors.")

        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            print(f"Report: {args.report}")
        else:
            print(json.dumps({k: report[k] for k in ("total_rows", "unique_names", "dry_run", "errors")}, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
