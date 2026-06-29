#!/usr/bin/env python3
"""Inspect the interview voice agent's language/voice/greeting — READ ONLY.

Sends nothing, changes nothing. Run on the VPS where the API/DB lives:

  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  python3 scripts/diagnose_interview_voice.py --agent "Jammal"
  python3 scripts/diagnose_interview_voice.py --order VB-CMP-9442F012

Prints, for an agent or an interview order:
  - the agent's default_voice + telnyx_assistant_id
  - the LIVE Telnyx assistant runtime (voice, model, greeting, transcription model/language)
  - the detected script language (ar / en) from the approved interview script
  - the generated opening greeting + the first lines of the runtime instructions
so you can confirm Jammal will speak (and transcribe) Arabic before placing a call.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_order(db, ref: str):
    from sqlalchemy import select

    from app.models.service_order import ServiceOrder

    key = str(ref or "").strip()
    if not key:
        return None
    order = db.get(ServiceOrder, key)
    if order is not None:
        return order
    upper = key.upper()
    return db.execute(
        select(ServiceOrder)
        .where((ServiceOrder.campaign_id == upper) | (ServiceOrder.reference_id == upper))
        .limit(1)
    ).scalar_one_or_none()


def _resolve_agent_by_name(db, name: str):
    from sqlalchemy import select

    from app.models.agent import AgentDefinition

    return db.execute(
        select(AgentDefinition).where(AgentDefinition.name == name).limit(1)
    ).scalar_one_or_none()


def _print_live_runtime(db, assistant_id: str) -> None:
    from app.services.telnyx_assistant_service import fetch_telnyx_assistant

    try:
        data = fetch_telnyx_assistant(db, assistant_id)
    except Exception as exc:  # noqa: BLE001
        print(f"  live Telnyx fetch failed: {exc}")
        return
    voice_settings = data.get("voice_settings") if isinstance(data.get("voice_settings"), dict) else {}
    transcription = data.get("transcription") if isinstance(data.get("transcription"), dict) else {}
    print(f"  live voice            {voice_settings.get('voice')}")
    print(f"  live language_boost   {voice_settings.get('language_boost')}")
    print(f"  live model (LLM)      {data.get('model')}")
    print(f"  live STT model        {transcription.get('model')}")
    print(f"  live STT language     {transcription.get('language')}")
    greeting = str(data.get("greeting") or "").strip()
    print(f"  live greeting         {greeting[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose interview voice/language (read only)")
    parser.add_argument("--agent", help="Agent name, e.g. Jammal")
    parser.add_argument("--order", help="VB-CMP-… campaign id, VB-INT-… reference, or order UUID")
    args = parser.parse_args()

    if not args.agent and not args.order:
        parser.error("provide --agent NAME or --order REF")

    from app.core.database import get_sessionmaker
    from app.services.interview_voice_agent_service import (
        build_interview_opening_greeting,
        build_interview_runtime_instructions,
        resolve_interview_telnyx_assistant_id,
    )
    from app.services.voice_agent_runtime import detect_config_language

    sessionmaker = get_sessionmaker()
    with sessionmaker() as db:
        order = None
        agent = None
        config: dict[str, Any] = {}

        if args.order:
            order = _resolve_order(db, args.order)
            if order is None:
                print(f"Order not found: {args.order}")
                return 2
            config = _loads(getattr(order, "config_json", None))
            assistant_id, agent = resolve_interview_telnyx_assistant_id(db, order, config)
        else:
            agent = _resolve_agent_by_name(db, args.agent)
            if agent is None:
                print(f"Agent not found: {args.agent}")
                return 2
            assistant_id = getattr(agent, "telnyx_assistant_id", "") or ""

        print("=== Agent ===")
        print(f"  name                {getattr(agent, 'name', None)}")
        print(f"  default_voice       {getattr(agent, 'default_voice', None)}")
        print(f"  telnyx_assistant_id {assistant_id}")
        print(f"  opening_disclosure  {str(getattr(agent, 'opening_disclosure_template', '') or '')[:160]}")

        print("\n=== Live Telnyx assistant ===")
        if assistant_id:
            _print_live_runtime(db, assistant_id)
        else:
            print("  (no telnyx_assistant_id configured)")

        script_text = str(
            config.get("approved_script")
            or config.get("generated_script_draft")
            or config.get("survey_runtime_prompt")
            or ""
        )
        detected = detect_config_language(config)
        print("\n=== Script language ===")
        print(f"  detected            {detected}")
        print(f"  script preview      {script_text[:160]}")

        if order is not None:
            recipient = None
            try:
                recipient = order.recipients[0] if getattr(order, "recipients", None) else None
            except Exception:
                recipient = None

            print("\n=== Generated runtime (this order) ===")
            try:
                greeting = build_interview_opening_greeting(
                    db,
                    agent=agent,
                    config=config,
                    recipient_name=str(getattr(recipient, "name", None) or "there"),
                    org_id=getattr(order, "org_id", None),
                    order=order,
                )
                print(f"  greeting            {greeting}")
            except Exception as exc:  # noqa: BLE001
                print(f"  greeting build failed: {exc}")
            if recipient is not None:
                try:
                    instructions = build_interview_runtime_instructions(
                        db, order=order, config=config, recipient=recipient, agent=agent
                    )
                    head = "\n".join(str(instructions).splitlines()[:8])
                    print("  instructions (head):")
                    print("    " + head.replace("\n", "\n    "))
                except Exception as exc:  # noqa: BLE001
                    print(f"  instructions build failed: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
