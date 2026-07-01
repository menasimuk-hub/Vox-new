#!/usr/bin/env python3
"""Inspect the interview voice agent's language/voice/greeting — READ ONLY.

Sends nothing, changes nothing. Run on the VPS where the API/DB lives:

  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  python3 scripts/diagnose_interview_voice.py --agent "Sultan"
  python3 scripts/diagnose_interview_voice.py --agent "interview_AR-Sultan"
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
    from sqlalchemy import or_, select

    from app.models.agent import AgentDefinition

    key = str(name or "").strip()
    if not key:
        return None
    exact = db.execute(select(AgentDefinition).where(AgentDefinition.name == key).limit(1)).scalar_one_or_none()
    if exact is not None:
        return exact
    pattern = f"%{key}%"
    return db.execute(
        select(AgentDefinition)
        .where(
            or_(
                AgentDefinition.name.ilike(pattern),
                AgentDefinition.voice_label.ilike(pattern),
                AgentDefinition.slug.ilike(pattern),
            )
        )
        .order_by(AgentDefinition.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _print_live_runtime(db, assistant_id: str) -> dict[str, Any] | None:
    from app.services.telnyx_assistant_service import fetch_telnyx_assistant, parse_telnyx_assistant_voice, resolve_telnyx_assistant_runtime

    try:
        data = fetch_telnyx_assistant(db, assistant_id)
    except Exception as exc:  # noqa: BLE001
        print(f"  live fetch failed: {exc}")
        return None
    voice_settings = data.get("voice_settings") if isinstance(data.get("voice_settings"), dict) else {}
    transcription = data.get("transcription") if isinstance(data.get("transcription"), dict) else {}
    voice_raw = str(voice_settings.get("voice") or "")
    provider, voice_id, _extras = parse_telnyx_assistant_voice(voice_raw, voice_settings=voice_settings)
    print(f"  live voice            {voice_raw}")
    print(f"  TTS provider          {provider}")
    print(f"  ElevenLabs voice id   {voice_id or '(none)'}")
    print(f"  api_key_ref           {voice_settings.get('api_key_ref')}")
    print(f"  live language_boost   {voice_settings.get('language_boost')}")
    print(f"  live model (LLM)      {data.get('model')}")
    print(f"  live STT model        {transcription.get('model')}")
    print(f"  live STT language     {transcription.get('language')}")
    greeting = str(data.get("greeting") or "").strip()
    print(f"  live greeting         {greeting[:200]}")
    try:
        runtime = resolve_telnyx_assistant_runtime(db, assistant_id)
        print(f"  runtime tts_provider  {runtime.get('tts_provider')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  runtime resolve failed: {exc}")
    return data


def _preview_check(db, agent) -> None:
    from app.services.interview_agent_display_service import _resolve_elevenlabs_voice_for_preview
    from app.services.providers.elevenlabs_service import ElevenLabsProviderService

    print("\n=== Voice preview check ===")
    voice_id, voice_settings, hint = _resolve_elevenlabs_voice_for_preview(db, agent)
    if not voice_id:
        print(f"  PREVIEW BLOCKED: {hint}")
        return
    print(f"  voice_id resolved     {voice_id}")
    print(f"  model_id              {voice_settings.get('model_id')}")
    sample = "Hello, this is a short voice test from VoxBulk."
    try:
        result = ElevenLabsProviderService.synthesize_text_result(
            db,
            text=sample,
            voice_id=voice_id,
            voice_settings=voice_settings,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  ElevenLabs FAILED: {exc}")
        return
    if result.get("ok"):
        print(f"  ElevenLabs OK         {len(result.get('audio_data') or b'')} bytes")
    else:
        print(f"  ElevenLabs FAILED: {result.get('error')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose interview voice/language (read only)")
    parser.add_argument("--agent", help="Agent name, slug, or voice label, e.g. Jack, interview-au-jack")
    parser.add_argument("--assistant-id", help="Telnyx assistant ID, e.g. assistant-d638feb0-...")
    parser.add_argument("--order", help="VB-CMP-… campaign id, VB-INT-… reference, or order UUID")
    parser.add_argument("--preview", action="store_true", help="Run ElevenLabs preview synthesis test")
    args = parser.parse_args()

    if not args.agent and not args.order and not args.assistant_id:
        parser.error("provide --agent NAME, --assistant-id ID, or --order REF")

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
        elif args.assistant_id:
            assistant_id = str(args.assistant_id).strip()
            agent = _resolve_agent_by_name(db, args.agent) if args.agent else None
            if agent is None and args.agent:
                print(f"Agent not found: {args.agent} (still checking assistant-id)")
        else:
            agent = _resolve_agent_by_name(db, args.agent)
            if agent is None:
                print(f"Agent not found: {args.agent}")
                return 2
            assistant_id = getattr(agent, "telnyx_assistant_id", "") or ""

        print("=== Agent ===")
        if agent is not None:
            print(f"  slug                {getattr(agent, 'slug', None)}")
            print(f"  name                {getattr(agent, 'name', None)}")
            print(f"  default_voice       {getattr(agent, 'default_voice', None)}")
            print(f"  telnyx_assistant_id {getattr(agent, 'telnyx_assistant_id', None)}")
            print(f"  opening_disclosure  {str(getattr(agent, 'opening_disclosure_template', '') or '')[:160]}")
        else:
            print("  (no DB agent row — assistant-id only)")

        print("\n=== Live Telnyx assistant ===")
        if assistant_id:
            _print_live_runtime(db, assistant_id)
        else:
            print("  (no telnyx_assistant_id configured)")

        if args.preview and agent is not None:
            _preview_check(db, agent)
        elif args.preview and assistant_id:
            from app.models.agent import AgentDefinition

            stub = AgentDefinition(
                name="preview-stub",
                slug="preview-stub",
                system_prompt="x",
                telnyx_assistant_id=assistant_id,
            )
            _preview_check(db, stub)

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

            print("\n=== Recipients (activity + cost) ===")
            from sqlalchemy import select

            from app.models.service_order import ServiceOrderRecipient
            from app.services.platform_catalog_service import ServiceOrderService
            from app.services.service_order_admin_cost_service import enrich_admin_order_costs

            rec_rows = db.execute(
                select(ServiceOrderRecipient)
                .where(ServiceOrderRecipient.order_id == order.id)
                .order_by(ServiceOrderRecipient.row_number.asc())
            ).scalars().all()
            payload = ServiceOrderService.order_to_admin_dict(
                order, include_recipients=True, recipients=list(rec_rows)
            )
            payload = enrich_admin_order_costs(db, order, payload)
            for row in payload.get("recipients") or []:
                print(f"  --- {row.get('name') or row.get('id')} ---")
                print(f"    status              {row.get('status')}")
                print(f"    channel             {row.get('call_channel')}")
                print(f"    transport           {row.get('transport')}")
                print(f"    duration_seconds    {row.get('duration_seconds')}")
                print(f"    billable_minutes    {row.get('billable_minutes')}")
                print(f"    telnyx_conversation {row.get('telnyx_conversation_id')}")
                print(f"    retail_cost         {row.get('retail_cost_display')}")
                print(f"    operator_cost       {row.get('operator_cost_display')}")
                print(f"    margin              {row.get('margin_display')}")
                try:
                    from app.services.interview_activity_service import InterviewActivityService

                    rec = next((r for r in rec_rows if r.id == row.get("id")), None)
                    if rec is not None:
                        timeline = InterviewActivityService.timeline(db, order, rec)
                        print(f"    activity_status     {timeline.get('activity_status')}")
                        events = timeline.get("events") or []
                        if events:
                            last = events[-1]
                            print(f"    last_event          {last.get('label')} @ {last.get('at')}")
                except Exception as exc:  # noqa: BLE001
                    print(f"    activity            (failed: {exc})")

            fin = payload.get("financial_summary") or {}
            if fin:
                print("\n=== Order financial summary ===")
                print(f"  quote               {fin.get('quote_total_display')}")
                rates = fin.get("sales_rates") or {}
                print(f"  sales per min       {rates.get('interview_per_min_display')}")
                print(f"  connection          {rates.get('connection_fee_display')}")
                print(f"  total R.cost        {fin.get('total_retail_cost_display')}")
                print(f"  total O.cost        {fin.get('total_operator_cost_display')}")
                print(f"  margin              {fin.get('margin_display')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
