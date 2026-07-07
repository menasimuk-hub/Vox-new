#!/usr/bin/env python3
"""Delete ALL WhatsApp templates on ONE connection profile's remote store.

REMOTE-ONLY: talks to the profile's provider (Meta Graph API for meta profiles, or
Telnyx API for telnyx profiles). Never writes to the local DB and never writes local
files (unless --report is given). Reads credentials straight off the profile row, so it
works even when the profile is inactive. Hard-refuses the Meta 99 profile / WABA / phone.

Usage (from voxbulk-api, venv active):
  # 1) DRY RUN — just count, delete nothing (default):
  python scripts/purge_profile_remote_wa_templates.py --profile-id <PROFILE_UUID>

  # 2) DELETE everything on that profile's remote store:
  python scripts/purge_profile_remote_wa_templates.py --profile-id <PROFILE_UUID> --apply --yes

Optional:
  --only-prefix voxbulk_survey_     # delete only names starting with this
  --exclude-prefix voxbulk_interview_ --exclude-prefix voxbulk_sales_   # repeatable
  --pause 0.3                       # seconds between delete calls (rate limit)
  --limit 100                       # cap number of delete calls (safety)
  --telnyx-waba <WABA_ID>           # (telnyx only) restrict to one WABA id
  --report /tmp/purge.json          # write a JSON report (off by default)
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

import httpx

from app.core.database import get_sessionmaker
from app.core.http_ssl import httpx_ssl_verify
from app.models.connection_profile import (
    CHANNEL_WHATSAPP,
    PROVIDER_META,
    PROVIDER_TELNYX,
    ConnectionProfile,
)
from app.services.connection.profile_credentials import (
    meta_config_from_profile,
    telnyx_config_from_profile,
)
from app.services.meta_whatsapp_config_service import graph_api_base
from app.services.meta_whatsapp_service import MetaWhatsappService, MetaWhatsappServiceError
from app.services.telnyx_api_key import normalize_telnyx_api_key
from app.services.telnyx_voice_service import _telnyx_headers

TELNYX_WHATSAPP_TEMPLATES_URL = "https://api.telnyx.com/v2/whatsapp/message_templates"

# --- Meta 99 = NEVER TOUCH (from docs/wa-template-sync-contract.md) ---
META99_PROFILE_ID = "b19c8d5b-2406-4bd0-8d56-610574ab491b"
META99_WABA_ID = "1033532842963987"
META99_PHONE_NUMBER_ID = "1307579342430096"


def _refuse_if_meta99(profile: ConnectionProfile, meta_cfg: dict) -> None:
    if str(profile.id) == META99_PROFILE_ID:
        sys.exit("REFUSED: this is the Meta 99 profile id — aborting.")
    if str(meta_cfg.get("waba_id") or "") == META99_WABA_ID:
        sys.exit(f"REFUSED: profile WABA {meta_cfg.get('waba_id')} == Meta 99 WABA — aborting.")
    if str(meta_cfg.get("phone_number_id") or "") == META99_PHONE_NUMBER_ID:
        sys.exit("REFUSED: profile phone_number_id == Meta 99 — aborting.")


# ---------------------------------------------------------------------------
# Meta provider
# ---------------------------------------------------------------------------
def _meta_fetch_all(cfg: dict) -> list[dict]:
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


def _meta_delete_by_name(cfg: dict, name: str) -> None:
    waba_id = str(cfg.get("waba_id") or "").strip()
    MetaWhatsappService._graph_request(
        config=cfg, method="DELETE", path=f"{waba_id}/message_templates", params={"name": name}
    )


# ---------------------------------------------------------------------------
# Telnyx provider
# ---------------------------------------------------------------------------
def _telnyx_fetch_all(api_key: str, waba_id: str | None) -> list[dict]:
    rows: list[dict] = []
    params: dict = {"page[size]": 250, "page[number]": 1}
    if waba_id:
        params["filter[waba_id]"] = waba_id
    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
        while True:
            response = client.get(TELNYX_WHATSAPP_TEMPLATES_URL, params=params, headers=_telnyx_headers(api_key))
            response.raise_for_status()
            body = response.json()
            chunk = body.get("data") if isinstance(body, dict) else []
            if isinstance(chunk, list):
                rows.extend(item for item in chunk if isinstance(item, dict))
            meta = body.get("meta") if isinstance(body, dict) else {}
            if not isinstance(meta, dict):
                break
            page_number = int(meta.get("page_number") or params["page[number]"])
            total_pages = int(meta.get("total_pages") or 1)
            if page_number >= total_pages:
                break
            params["page[number]"] = page_number + 1
    return rows


def _telnyx_delete_by_id(api_key: str, record_id: str) -> None:
    url = f"{TELNYX_WHATSAPP_TEMPLATES_URL}/{record_id}"
    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
        response = client.delete(url, headers=_telnyx_headers(api_key))
        if response.status_code in (200, 204, 404):
            return
        response.raise_for_status()


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Purge remote WA templates on ONE connection profile")
    ap.add_argument("--profile-id", required=True, help="Connection profile UUID")
    ap.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    ap.add_argument("--yes", action="store_true", help="Skip interactive confirmation")
    ap.add_argument("--only-prefix", default="", help="Only names starting with this prefix")
    ap.add_argument("--exclude-prefix", action="append", default=[], help="Skip names with this prefix (repeatable)")
    ap.add_argument("--pause", type=float, default=0.3, help="Seconds between delete calls")
    ap.add_argument("--limit", type=int, default=0, help="Max delete calls (0 = no cap)")
    ap.add_argument("--telnyx-waba", default="", help="(telnyx only) restrict to one WABA id")
    ap.add_argument("--report", default="", help="Optional path to write a JSON report")
    args = ap.parse_args()

    only = str(args.only_prefix or "").strip().lower()
    excludes = [str(p).strip().lower() for p in (args.exclude_prefix or []) if str(p).strip()]

    db = get_sessionmaker()()
    try:
        profile = db.get(ConnectionProfile, str(args.profile_id).strip())
        if profile is None:
            sys.exit("Profile not found")
        if str(profile.channel or "").lower() != CHANNEL_WHATSAPP:
            sys.exit("Profile is not a WhatsApp channel profile")

        provider = str(profile.provider or "").strip().lower()
        if provider not in (PROVIDER_META, PROVIDER_TELNYX):
            sys.exit(f"Unsupported provider '{provider}'.")

        # Meta 99 guard applies regardless of provider (belt and braces).
        _refuse_if_meta99(profile, meta_config_from_profile(profile))

        report: dict = {
            "at": datetime.now(timezone.utc).isoformat(),
            "profile_id": str(profile.id),
            "profile_name": profile.name,
            "provider": provider,
            "dry_run": not args.apply,
            "deleted": [],
            "errors": [],
        }

        # --- Gather remote rows ---
        if provider == PROVIDER_META:
            cfg = meta_config_from_profile(profile)
            if not (cfg.get("access_token") and cfg.get("waba_id")):
                sys.exit("Meta profile is missing access_token or waba_id — cannot proceed.")
            print("=== Target profile (Meta) ===")
            print(f"  name         : {profile.name}")
            print(f"  waba_id      : {cfg.get('waba_id')}")
            print(f"  phone_number : {cfg.get('whatsapp_from') or profile.meta_whatsapp_from}")
            print(f"  graph base   : {graph_api_base(cfg)}")
            print()
            rows = _meta_fetch_all(cfg)
        else:
            tcfg = telnyx_config_from_profile(profile)
            api_key = normalize_telnyx_api_key(str(tcfg.get("api_key") or ""))
            if not api_key:
                sys.exit("Telnyx profile has no API key — cannot proceed.")
            waba_filter = str(args.telnyx_waba or "").strip() or None
            print("=== Target profile (Telnyx) ===")
            print(f"  name         : {profile.name}")
            print(f"  number       : {tcfg.get('whatsapp_from') or profile.telnyx_number}")
            print(f"  waba filter  : {waba_filter or '(all WABAs on this key)'}")
            print()
            rows = _telnyx_fetch_all(api_key, waba_filter)

        # --- Apply name filters ---
        kept: list[dict] = []
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
            kept.append(r)

        report["total_rows"] = len(kept)
        report["excluded_names"] = len(skipped_excluded)

        if provider == PROVIDER_META:
            # Meta deletes by name (removes all languages at once).
            by_name: dict[str, list[dict]] = defaultdict(list)
            for r in kept:
                by_name[str(r.get("name"))].append(r)
            units = sorted(by_name.keys())
            report["unique_names"] = len(units)
            print(f"Templates on this WABA (after filters): {len(kept)} rows across {len(units)} unique names")
        else:
            # Telnyx deletes by record id (one call per row).
            units = kept
            report["unique_names"] = len(kept)
            print(f"Templates on this Telnyx account (after filters): {len(kept)} rows")

        if skipped_excluded:
            print(f"Excluded by prefix: {len(skipped_excluded)} names")
        preview = units[:15]
        for u in preview:
            if provider == PROVIDER_META:
                langs = ",".join(sorted(str(x.get("language") or "?") for x in by_name[u]))
                print(f"  - {u} [{langs}]")
            else:
                print(f"  - {u.get('name')} [{u.get('language') or '?'}] id={u.get('id')}")
        if len(units) > 15:
            print(f"  ... and {len(units) - 15} more")
        print()

        if not args.apply:
            print("DRY RUN — nothing deleted. Re-run with --apply --yes to delete.")
        else:
            target = report["unique_names"]
            if not args.yes:
                confirm = input(f"Delete {target} template(s) from profile '{profile.name}'? type DELETE: ")
                if confirm.strip() != "DELETE":
                    sys.exit("Aborted.")
            deleted = 0
            for u in units:
                if args.limit and deleted >= args.limit:
                    print(f"Reached --limit {args.limit}; stopping.")
                    break
                try:
                    if provider == PROVIDER_META:
                        _meta_delete_by_name(cfg, u)
                        report["deleted"].append(u)
                    else:
                        _telnyx_delete_by_id(api_key, str(u.get("id")))
                        report["deleted"].append({"name": u.get("name"), "id": u.get("id")})
                    deleted += 1
                    if deleted % 50 == 0:
                        print(f"  deleted {deleted}/{target}...")
                except (MetaWhatsappServiceError, httpx.HTTPError) as exc:
                    label = u if provider == PROVIDER_META else u.get("id")
                    report["errors"].append({"unit": str(label), "error": str(exc)[:300]})
                if args.pause:
                    time.sleep(args.pause)
            print(f"\nDone. Deleted {deleted}, {len(report['errors'])} errors.")

        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            print(f"Report: {args.report}")
        else:
            print(json.dumps(
                {k: report[k] for k in ("total_rows", "unique_names", "dry_run", "errors")},
                indent=2,
            ))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
