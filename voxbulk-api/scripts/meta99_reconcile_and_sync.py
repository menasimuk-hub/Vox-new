#!/usr/bin/env python3
"""Meta 99 reconcile: align credentials, dedupe DB rows, chunked push DB→Meta, verify send.

Run on VPS:
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python scripts/meta99_reconcile_and_sync.py
  python scripts/meta99_reconcile_and_sync.py --push-only --batch-size 5
  python scripts/meta99_reconcile_and_sync.py --report-only
"""
from __future__ import annotations

import argparse
import json
import sys
import time

sys.path.insert(0, ".")

META99_PROFILE_NAME = "Meta 99"
META99_BUSINESS_ID = "959487190007928"
META99_PHONE_NUMBER_ID = "1307579342430096"
META99_WABA_ID = "1033532842963987"
META99_WHATSAPP_FROM = "+447822002099"
TEST_TO = "+447954823445"


def _load_profile(db):
    from sqlalchemy import select

    from app.models.connection_profile import CHANNEL_WHATSAPP, ConnectionProfile

    return db.execute(
        select(ConnectionProfile).where(
            ConnectionProfile.channel == CHANNEL_WHATSAPP,
            ConnectionProfile.name == META99_PROFILE_NAME,
        )
    ).scalar_one_or_none()


def sync_platform_from_profile(db, profile) -> dict:
    from app.services.connection.profile_credentials import meta_config_from_profile
    from app.services.provider_settings import ProviderSettingsService

    cfg = meta_config_from_profile(profile)
    payload = {
        "waba_id": str(cfg.get("waba_id") or META99_WABA_ID).strip(),
        "phone_number_id": str(cfg.get("phone_number_id") or META99_PHONE_NUMBER_ID).strip(),
        "business_id": str(cfg.get("business_id") or META99_BUSINESS_ID).strip(),
        "whatsapp_from": str(cfg.get("whatsapp_from") or META99_WHATSAPP_FROM).strip(),
        "graph_api_version": str(cfg.get("graph_api_version") or "v25.0").strip(),
        "webhook_base_url": str(cfg.get("webhook_base_url") or "https://api.voxbulk.com").strip(),
    }
    if str(cfg.get("access_token") or "").strip():
        payload["access_token"] = str(cfg.get("access_token") or "").strip()
    if str(cfg.get("app_secret") or "").strip():
        payload["app_secret"] = str(cfg.get("app_secret") or "").strip()
    if str(cfg.get("webhook_verify_token") or "").strip():
        payload["webhook_verify_token"] = str(cfg.get("webhook_verify_token") or "").strip()

    profile.meta_business_id = META99_BUSINESS_ID
    profile.meta_phone_number_id = META99_PHONE_NUMBER_ID
    profile.meta_waba_id = META99_WABA_ID
    if not str(profile.meta_whatsapp_from or "").strip():
        profile.meta_whatsapp_from = META99_WHATSAPP_FROM
    db.add(profile)

    ProviderSettingsService.upsert_platform_config(
        db,
        provider="meta_whatsapp",
        config_json=payload,
        is_enabled=True,
    )
    db.commit()
    return payload


def dedupe_welcome_rows(db) -> dict:
    from sqlalchemy import select, text

    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

    rows = db.execute(
        select(TelnyxWhatsappTemplate).where(
            TelnyxWhatsappTemplate.name.like("%standard_utu%")
        )
    ).scalars().all()
    keep_id = 1884
    keep = db.get(TelnyxWhatsappTemplate, keep_id)
    retired: list[int] = []
    for row in rows:
        if int(row.id) == keep_id:
            continue
        if keep is not None and str(row.name or "").endswith("_2"):
            keep.name = str(row.name)
            keep.telnyx_record_id = str(row.telnyx_record_id or keep.telnyx_record_id)
            keep.template_id = str(row.template_id or keep.template_id)
            db.add(keep)
        row.active_for_survey = False
        row.admin_hidden_from_survey = True
        db.add(row)
        retired.append(int(row.id))
    db.commit()
    if keep is not None:
        db.refresh(keep)
    return {
        "keep_id": keep_id,
        "keep_name": keep.name if keep else None,
        "keep_record": keep.telnyx_record_id if keep else None,
        "retired_ids": retired,
    }


def report_duplicates(db) -> list[dict]:
    from sqlalchemy import text

    rows = db.execute(
        text(
            """
            SELECT survey_type_id, step_role, variant_type, language, COUNT(*) AS c,
                   GROUP_CONCAT(id ORDER BY id) AS ids,
                   GROUP_CONCAT(name ORDER BY id) AS names
            FROM telnyx_whatsapp_templates
            WHERE survey_type_id IS NOT NULL AND step_role IS NOT NULL
            GROUP BY survey_type_id, step_role, variant_type, language
            HAVING COUNT(*) > 1
            ORDER BY c DESC
            LIMIT 50
            """
        )
    ).fetchall()
    out = []
    for row in rows:
        out.append(
            {
                "survey_type_id": row[0],
                "step_role": row[1],
                "variant_type": row[2],
                "language": row[3],
                "count": int(row[4] or 0),
                "ids": str(row[5] or ""),
                "names": str(row[6] or ""),
            }
        )
    return out


def chunked_push(db, *, batch_size: int = 5, pause_sec: float = 3.0, industry_id: str | None = None) -> dict:
    from app.services.wa_template_sync_service import WaTemplateSyncService

    offset = 0
    rounds: list[dict] = []
    while True:
        result = WaTemplateSyncService.push_changed_batch(
            db,
            industry_id=industry_id,
            offset=offset,
            limit=batch_size,
            force_push=False,
        )
        rounds.append(
            {
                "offset": offset,
                "pushed": result.get("pushed"),
                "linked": result.get("linked"),
                "skipped": result.get("skipped"),
                "errors": result.get("errors"),
                "message": result.get("message"),
            }
        )
        if not result.get("has_more"):
            break
        offset = int(result.get("next_offset") or 0)
        time.sleep(max(pause_sec, 1.0))
    return {"rounds": rounds, "batch_size": batch_size}


def status_only_pull(db) -> dict:
    from app.services.wa_template_sync_service import WaTemplateSyncService

    return WaTemplateSyncService.pull_from_meta(db, status_only=True)


def verify_template_send(db, *, template_name: str, language: str = "en_GB") -> dict:
    from app.models.connection_profile import ConnectionProfile
    from app.services.connection.profile_credentials import meta_config_from_profile
    from app.services.connection.providers.whatsapp_meta import WhatsappMetaProvider

    profile = _load_profile(db)
    if profile is None:
        return {"ok": False, "error": "Meta 99 profile not found"}
    cfg = meta_config_from_profile(profile)
    result = WhatsappMetaProvider.send(
        db,
        config=cfg,
        to_number=TEST_TO,
        body="Meta 99 reconcile test",
        template_name=template_name,
        template_language=language,
        template_components=[
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "Test"},
                    {"type": "text", "text": "VoxBulk"},
                ],
            }
        ],
        meter_usage=False,
    )
    return {"ok": bool(result.ok), "status": result.status, "detail": result.detail}


def main() -> int:
    parser = argparse.ArgumentParser(description="Meta 99 DB↔Meta reconcile and chunked sync")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--push-only", action="store_true")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--pause-sec", type=float, default=3.0)
    parser.add_argument("--industry-id", default="")
    args = parser.parse_args()

    from app.core.database import get_sessionmaker

    db = get_sessionmaker()()
    summary: dict = {"steps": []}

    profile = _load_profile(db)
    if profile is None:
        print("FAIL: Meta 99 connection profile not found")
        return 1
    summary["profile"] = {
        "id": profile.id,
        "waba_id": profile.meta_waba_id,
        "phone_number_id": profile.meta_phone_number_id,
        "business_id": profile.meta_business_id,
    }

    if not args.push_only:
        creds = sync_platform_from_profile(db, profile)
        summary["steps"].append({"sync_platform_from_profile": {k: v for k, v in creds.items() if k != "access_token"}})
        print("OK platform integration aligned with Meta 99 profile")

        dupes = report_duplicates(db)
        summary["duplicate_groups"] = dupes
        print(f"duplicate logical template groups: {len(dupes)}")
        for item in dupes[:10]:
            print(" ", item)

        dedupe = dedupe_welcome_rows(db)
        summary["steps"].append({"dedupe_welcome": dedupe})
        print("OK welcome dedupe", dedupe)

        pull = status_only_pull(db)
        summary["steps"].append({"status_pull": pull})
        print("OK status-only pull", pull.get("message"))

    if args.report_only:
        print(json.dumps(summary, indent=2, default=str))
        db.close()
        return 0

    industry_id = str(args.industry_id or "").strip() or None
    push = chunked_push(db, batch_size=max(1, min(args.batch_size, 10)), pause_sec=args.pause_sec, industry_id=industry_id)
    summary["steps"].append({"chunked_push": push})
    print("OK chunked push rounds", len(push.get("rounds") or []))
    for rnd in push.get("rounds") or []:
        print(" ", rnd.get("message"), "errors=", rnd.get("errors"))

    keep = db.get(__import__("app.models.telnyx_whatsapp_template", fromlist=["TelnyxWhatsappTemplate"]).TelnyxWhatsappTemplate, 1884)
    tpl_name = str(keep.name if keep else "voxbulk_survey_welcome_templates_standard_utu_2")
    send = verify_template_send(db, template_name=tpl_name)
    summary["steps"].append({"verify_send": send})
    print("verify send", send)

    print(json.dumps(summary, indent=2, default=str))
    db.close()
    return 0 if send.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
