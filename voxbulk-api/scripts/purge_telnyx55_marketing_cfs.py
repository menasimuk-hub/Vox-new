#!/usr/bin/env python3
"""Delete ONLY MARKETING cfs_* WhatsApp templates on the Telnyx 55 WABA.

Uses Meta 99 profile token to manage WABA 1033532842963987 (Telnyx 55 side).
HARD-REFUSES Meta 99 keeper WABA 959487190007928.

Does NOT delete:
  - Meta 99 templates
  - UTILITY cfs_* on Telnyx 55
  - survey was_* / non-cfs names

Usage (VPS):
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python -u scripts/purge_telnyx55_marketing_cfs.py --dry-run
  python -u scripts/purge_telnyx55_marketing_cfs.py --apply --yes
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.models.connection_profile import ConnectionProfile
from app.services.connection.profile_credentials import meta_config_from_profile
from app.services.meta_whatsapp_service import MetaWhatsappService

# Meta 99 profile (token) — never the delete target
META99_PROFILE_ID = "b19c8d5b-2406-4bd0-8d56-610574ab491b"
META99_KEEP_WABA_ID = "959487190007928"
# Telnyx 55 / old 55 Meta WABA (delete target for MARKETING cfs only)
TELNYX55_WABA_ID = "1033532842963987"

REPORT_DIR = ROOT / "seed-data" / "customer-feedback" / "push-reports"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _fetch_all(cfg: dict, waba_id: str) -> list[dict]:
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


def _delete_by_name(cfg: dict, waba_id: str, name: str) -> None:
    MetaWhatsappService._graph_request(
        config=cfg, method="DELETE", path=f"{waba_id}/message_templates", params={"name": name}
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Purge MARKETING cfs_* on Telnyx 55 WABA only (Meta 99 never touched)"
    )
    parser.add_argument("--dry-run", action="store_true", help="List targets only (default if no --apply)")
    parser.add_argument("--apply", action="store_true", help="Actually delete")
    parser.add_argument("--yes", action="store_true", help="Required with --apply (non-interactive)")
    parser.add_argument("--pause", type=float, default=1.0, help="Seconds between deletes (default 1)")
    parser.add_argument("--profile-id", default=META99_PROFILE_ID, help="Token profile (Meta 99)")
    parser.add_argument("--meta-waba", default=TELNYX55_WABA_ID, help="Target WABA (Telnyx 55 side)")
    args = parser.parse_args()

    target_waba = str(args.meta_waba or "").strip()
    if target_waba == META99_KEEP_WABA_ID:
        _log("REFUSED: target WABA is Meta 99 keeper — aborting.")
        return 2
    if not args.apply:
        args.dry_run = True
    if args.apply and not args.yes:
        _log("REFUSED: --apply requires --yes")
        return 2

    with get_sessionmaker()() as db:
        profile = db.get(ConnectionProfile, str(args.profile_id).strip())
        if profile is None:
            _log("ERROR: Meta 99 profile not found")
            return 1
        cfg = meta_config_from_profile(profile)
        if not cfg.get("access_token"):
            _log("ERROR: Meta profile missing access_token")
            return 1

    _log("=== Purge Telnyx 55 MARKETING cfs_* ===")
    _log(f"token_profile : {args.profile_id}")
    _log(f"target_waba   : {target_waba}")
    _log(f"mode          : {'APPLY' if args.apply else 'DRY-RUN'}")

    rows = _fetch_all(cfg, target_waba)
    # Unique names that are cfs_* AND MARKETING (delete is by name → all langs)
    targets: dict[str, dict] = {}
    utility_cfs = 0
    other = 0
    for r in rows:
        name = str(r.get("name") or "").strip()
        cat = str(r.get("category") or "").strip().upper()
        if not name:
            continue
        nl = name.lower()
        if not nl.startswith("cfs_"):
            other += 1
            continue
        if cat == "MARKETING":
            targets[name] = {
                "name": name,
                "category": cat,
                "status": r.get("status"),
                "language": r.get("language"),
                "id": r.get("id"),
            }
        else:
            utility_cfs += 1

    names = sorted(targets.keys())
    _log(f"remote_total={len(rows)} cfs_utility_rows≈{utility_cfs} non_cfs_rows≈{other}")
    _log(f"MARKETING cfs_* names to delete: {len(names)}")
    for n in names[:80]:
        t = targets[n]
        _log(f"  {n}  status={t.get('status')} lang_sample={t.get('language')}")
    if len(names) > 80:
        _log(f"  … +{len(names) - 80} more")

    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "target_waba": target_waba,
        "token_profile_id": str(args.profile_id),
        "dry_run": not args.apply,
        "marketing_cfs_names": names,
        "deleted": [],
        "errors": [],
    }

    if not args.apply:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = REPORT_DIR / f"purge-telnyx55-mkt-cfs-dryrun-{stamp}.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        _log(f"Dry-run report: {out}")
        _log("OK (dry-run) — re-run with --apply --yes to delete")
        return 0

    pause = max(0.0, float(args.pause))
    for idx, name in enumerate(names, start=1):
        try:
            _delete_by_name(cfg, target_waba, name)
            report["deleted"].append(name)
            _log(f"  [{idx}/{len(names)}] DELETED {name}")
        except Exception as exc:  # noqa: BLE001
            err = {"name": name, "error": str(exc)}
            report["errors"].append(err)
            _log(f"  [{idx}/{len(names)}] FAIL {name}: {exc}")
        if pause and idx < len(names):
            time.sleep(pause)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = REPORT_DIR / f"purge-telnyx55-mkt-cfs-apply-{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _log(f"Report: {out}")
    _log(f"deleted={len(report['deleted'])} errors={len(report['errors'])}")
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
