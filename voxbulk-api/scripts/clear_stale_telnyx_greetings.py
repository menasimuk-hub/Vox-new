#!/usr/bin/env python3
"""Clear stale telnyx_greeting values and re-sync instructions to Telnyx (no greeting push)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.frontpage_call_setting import FrontpageCallSetting
from app.models.lead_sales_setting import LeadSalesSetting
from app.services.frontpage_lead_service import build_lead_runtime_prompt
from app.services.lead_sales_service import _sales_playbook_block, refresh_lead_sales_kb
from app.services.telnyx_assistant_service import sync_telnyx_assistant_instructions
from app.services.telnyx_lead_variables import ensure_telnyx_variables_block

STALE_PHRASES = ("good time", "quick chat", "thanks for reaching out")


def _is_stale(value: str | None) -> bool:
    lowered = str(value or "").lower()
    return any(phrase in lowered for phrase in STALE_PHRASES)


def _row_out(table: str, row_id: str, org_id: str | None, greeting: str | None, assistant_id: str | None) -> dict:
    return {
        "table": table,
        "id": row_id,
        "org_id": org_id,
        "assistant_id": assistant_id,
        "telnyx_greeting": greeting,
    }


def show_all_rows(db) -> list[dict]:
    rows: list[dict] = []
    for setting in db.scalars(select(FrontpageCallSetting)).all():
        rows.append(
            _row_out(
                "frontpage_call_settings",
                setting.id,
                setting.org_id,
                setting.telnyx_greeting,
                setting.provider_agent_id,
            )
        )
    for setting in db.scalars(select(LeadSalesSetting)).all():
        rows.append(
            _row_out(
                "lead_sales_settings",
                setting.id,
                None,
                setting.telnyx_greeting,
                setting.telnyx_assistant_id,
            )
        )
    return rows


def clear_stale_rows(db) -> list[dict]:
    cleared: list[dict] = []
    for setting in db.scalars(select(FrontpageCallSetting)).all():
        if not _is_stale(setting.telnyx_greeting):
            continue
        cleared.append(_row_out(
            "frontpage_call_settings",
            setting.id,
            setting.org_id,
            setting.telnyx_greeting,
            setting.provider_agent_id,
        ))
        setting.telnyx_greeting = None
        db.add(setting)

    for setting in db.scalars(select(LeadSalesSetting)).all():
        if not _is_stale(setting.telnyx_greeting):
            continue
        cleared.append(_row_out(
            "lead_sales_settings",
            setting.id,
            None,
            setting.telnyx_greeting,
            setting.telnyx_assistant_id,
        ))
        setting.telnyx_greeting = None
        db.add(setting)

    if cleared:
        db.commit()
    return cleared


def resync_affected(db, cleared: list[dict]) -> list[dict]:
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for item in cleared:
        table = item["table"]
        row_id = item["id"]
        key = (table, row_id)
        if key in seen:
            continue
        seen.add(key)

        if table == "frontpage_call_settings":
            setting = db.get(FrontpageCallSetting, row_id)
            if setting is None:
                continue
            assistant_id = str(setting.provider_agent_id or "").strip()
            if not assistant_id:
                results.append({"table": table, "id": row_id, "ok": False, "error": "no assistant_id"})
                continue
            instructions = ensure_telnyx_variables_block(build_lead_runtime_prompt(setting))
            if not instructions.strip():
                results.append({"table": table, "id": row_id, "ok": False, "error": "empty instructions"})
                continue
            try:
                sync_telnyx_assistant_instructions(
                    db,
                    assistant_id,
                    instructions,
                    greeting=None,
                    sync_greeting=False,
                )
                results.append({"table": table, "id": row_id, "assistant_id": assistant_id, "ok": True})
            except Exception as exc:
                results.append({"table": table, "id": row_id, "assistant_id": assistant_id, "ok": False, "error": str(exc)})
            continue

        if table == "lead_sales_settings":
            setting = db.get(LeadSalesSetting, row_id)
            if setting is None:
                continue
            assistant_id = str(setting.telnyx_assistant_id or "").strip()
            if not assistant_id:
                results.append({"table": table, "id": row_id, "ok": False, "error": "no assistant_id"})
                continue
            refresh_lead_sales_kb(setting, db)
            db.add(setting)
            db.commit()
            instructions = _sales_playbook_block(setting).strip()
            if not instructions:
                results.append({"table": table, "id": row_id, "ok": False, "error": "empty instructions"})
                continue
            try:
                sync_telnyx_assistant_instructions(
                    db,
                    assistant_id,
                    instructions,
                    greeting=None,
                    sync_greeting=False,
                    enable_web_calls=False,
                )
                results.append({"table": table, "id": row_id, "assistant_id": assistant_id, "ok": True})
            except Exception as exc:
                results.append({"table": table, "id": row_id, "assistant_id": assistant_id, "ok": False, "error": str(exc)})

    return results


def main() -> int:
    sessionmaker = get_sessionmaker()
    with sessionmaker() as db:
        print("=== BEFORE: all telnyx_greeting values ===")
        before = show_all_rows(db)
        print(json.dumps(before, indent=2, ensure_ascii=False))

        cleared = clear_stale_rows(db)
        print("\n=== CLEARED rows (set to NULL) ===")
        print(json.dumps(cleared, indent=2, ensure_ascii=False) if cleared else "[]")

        sync_results = resync_affected(db, cleared) if cleared else []
        print("\n=== TELNYX RE-SYNC (instructions only, sync_greeting=False) ===")
        print(json.dumps(sync_results, indent=2, ensure_ascii=False) if sync_results else "[]")

        print("\n=== AFTER: all telnyx_greeting values ===")
        after = show_all_rows(db)
        print(json.dumps(after, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
