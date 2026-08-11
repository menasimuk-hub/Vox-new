"""Telnyx webhook tools for the public AI Demo walkthrough."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.data.ai_demo_kb_defaults import DEFAULT_TOOL_SUBSET
from app.models.agent import AgentDefinition
from app.services.telnyx_assistant_service import (
    _update_telnyx_assistant,
    fetch_telnyx_assistant,
    normalize_telnyx_assistant_id,
)

logger = logging.getLogger(__name__)

_HANGUP_TOOL = {
    "type": "hangup",
    "hangup": {
        "description": (
            "Use when the conversation has ended and it is appropriate to hang up the call."
        )
    },
}


def ai_demo_api_base() -> str:
    settings = get_settings()
    # Prefer production API host; fall back if a custom origin is configured later.
    base = str(getattr(settings, "public_site_base_url", "") or "").strip().rstrip("/")
    if "voxbulk.com" in base:
        return "https://api.voxbulk.com"
    return "https://api.voxbulk.com"


def ai_demo_tool_webhook_urls() -> dict[str, str]:
    root = ai_demo_api_base().rstrip("/")
    return {name: f"{root}/ai-demo/tools/{name}" for name in DEFAULT_TOOL_SUBSET}


def _str_prop(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _body(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def build_ai_demo_webhook_tools() -> list[dict[str, Any]]:
    urls = ai_demo_tool_webhook_urls()
    specs: list[tuple[str, str, dict[str, Any]]] = [
        (
            "switch_kb",
            "Switch the active product knowledge base and dashboard tab "
            "(recruitment, surveys, feedback, expo, smart_card).",
            _body(
                {
                    "service": _str_prop("Product code: recruitment|surveys|feedback|expo|smart_card"),
                    "service_code": _str_prop("Alias for service"),
                },
                ["service"],
            ),
        ),
        (
            "highlight_dashboard",
            "Drive the live demo dashboard: highlight, navigate, filter, or open a chart "
            "when you say here/this chart/these locations. Call BEFORE or AS you speak.",
            _body(
                {
                    "action": _str_prop("highlight|navigate|filter|open_chart"),
                    "section": _str_prop("Service section e.g. feedback"),
                    "target": _str_prop("data-demo-target id e.g. leeds-chart, locations-overview"),
                    "location": _str_prop("Location filter e.g. Leeds"),
                    "range": _str_prop("Optional range e.g. 6mo"),
                    "view": _str_prop("Optional smart_card view: rep|manager"),
                    "delay_ms": {"type": "integer", "description": "UI lead delay ms (300-500)"},
                },
                ["action"],
            ),
        ),
        (
            "show_result_panel",
            "Show a JSON/result panel on the demo UI (legacy companion panel).",
            _body({"data": {"type": "object", "description": "Panel payload"}, "json": {"type": "object"}}),
        ),
        (
            "show_link",
            "Show an external link card on the demo UI.",
            _body(
                {
                    "url": _str_prop("Absolute https URL"),
                    "label": _str_prop("Button label"),
                },
                ["url"],
            ),
        ),
        (
            "show_qr_code",
            "Show a real scannable QR so the visitor can try the product live. "
            "Go quiet while they scan.",
            _body(
                {
                    "service": _str_prop("feedback|expo|smart_card"),
                    "label": _str_prop("QR card title"),
                    "data": _str_prop("Optional absolute URL override"),
                    "url": _str_prop("Optional absolute URL override"),
                },
            ),
        ),
        (
            "show_pricing",
            "Open the pricing panel. Explain package differences and recommend. "
            "Never invent discounts — sales will send the best offer.",
            _body(
                {
                    "recommendation": _str_prop("e.g. Growth"),
                    "recommend": _str_prop("Alias for recommendation"),
                    "service": _str_prop("Product context"),
                },
            ),
        ),
        (
            "request_sales_offer",
            "Flag the lead so sales will send the best offer. Do not email a promo yourself.",
            _body(
                {
                    "note": _str_prop("Short note for sales"),
                    "summary": _str_prop("Alias for note"),
                    "volumes": {"type": "object", "description": "Optional volume needs"},
                },
            ),
        ),
        (
            "set_voice_lang",
            "Switch spoken language / voice preference for the session.",
            _body(
                {
                    "lang": _str_prop("en|ar"),
                    "language": _str_prop("Alias for lang"),
                    "voice": _str_prop("Optional voice id"),
                },
            ),
        ),
        (
            "end_demo",
            "End the demo session with a short summary and book-sales CTA.",
            _body(
                {
                    "summary": _str_prop("Needs summary for sales"),
                    "transcript": _str_prop("Optional transcript snippet"),
                },
            ),
        ),
        (
            "log_volume_needs",
            "Capture expected volumes (locations, interviews/month, show size, team size).",
            _body({"volumes": {"type": "object", "description": "Volume needs object"}}),
        ),
    ]

    tools: list[dict[str, Any]] = []
    for name, description, body in specs:
        tools.append(
            {
                "type": "webhook",
                "webhook": {
                    "name": name,
                    "description": description,
                    "url": urls[name],
                    "method": "POST",
                    "body_parameters": body,
                },
            }
        )
    return tools


def _webhook_tool_name(tool: dict[str, Any]) -> str | None:
    if str(tool.get("type") or "").lower() != "webhook":
        return None
    wh = tool.get("webhook") if isinstance(tool.get("webhook"), dict) else {}
    name = str(wh.get("name") or "").strip()
    return name or None


def merge_ai_demo_tools(existing_tools: list[Any] | None) -> list[dict[str, Any]]:
    """Replace AI Demo webhook tools by name; keep hangup + unrelated tools."""
    current = [t for t in (existing_tools or []) if isinstance(t, dict)]
    desired_webhooks = {
        name: tool
        for name, tool in ((_webhook_tool_name(t), t) for t in build_ai_demo_webhook_tools())
        if name
    }
    desired_names = set(desired_webhooks.keys())

    kept: list[dict[str, Any]] = []
    has_hangup = False
    for tool in current:
        ttype = str(tool.get("type") or "").lower()
        if ttype == "hangup":
            has_hangup = True
            kept.append(tool)
            continue
        name = _webhook_tool_name(tool)
        if name and name in desired_names:
            continue  # replaced below
        kept.append(tool)

    for name in DEFAULT_TOOL_SUBSET:
        tool = desired_webhooks.get(name)
        if tool:
            kept.append(tool)
    if not has_hangup:
        kept.append(_HANGUP_TOOL)
    return kept


def ensure_ai_demo_assistant_tools(
    db: Session,
    assistant_id: str,
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """PATCH Telnyx assistant tools with AI Demo webhook endpoints + hangup."""
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    live = existing if isinstance(existing, dict) else fetch_telnyx_assistant(db, clean_id)
    current_tools = live.get("tools") if isinstance(live.get("tools"), list) else []
    desired = merge_ai_demo_tools(current_tools)

    # Skip update if already equivalent by webhook name+url set
    def _sig(tools: list[Any]) -> set[str]:
        out: set[str] = set()
        for t in tools:
            if not isinstance(t, dict):
                continue
            if str(t.get("type") or "").lower() == "hangup":
                out.add("hangup")
                continue
            name = _webhook_tool_name(t)
            if not name:
                continue
            wh = t.get("webhook") if isinstance(t.get("webhook"), dict) else {}
            url = str(wh.get("url") or "").strip()
            out.add(f"{name}|{url}")
        return out

    if _sig(current_tools) >= _sig(desired) and all(
        f"{n}|{ai_demo_tool_webhook_urls()[n]}" in _sig(current_tools) for n in DEFAULT_TOOL_SUBSET
    ):
        return {
            "ok": True,
            "changed": False,
            "assistant_id": clean_id,
            "tool_count": len(current_tools),
            "webhook_tools": list(DEFAULT_TOOL_SUBSET),
        }

    try:
        _update_telnyx_assistant(db, clean_id, {"tools": desired})
        return {
            "ok": True,
            "changed": True,
            "assistant_id": clean_id,
            "tool_count": len(desired),
            "webhook_tools": list(DEFAULT_TOOL_SUBSET),
            "urls": ai_demo_tool_webhook_urls(),
        }
    except Exception as exc:
        logger.warning("ensure_ai_demo_tools_failed assistant_id=%s err=%s", clean_id, exc)
        return {
            "ok": False,
            "changed": False,
            "assistant_id": clean_id,
            "tool_count": len(current_tools),
            "error": str(exc)[:400],
        }


def sync_tools_for_all_ai_demo_agents(db: Session) -> dict[str, Any]:
    """Ensure tools on every Admin agent whose name/slug is AI Demo dedicated."""
    rows = list(
        db.execute(
            select(AgentDefinition).where(AgentDefinition.is_active.is_(True))
        ).scalars()
    )
    results: list[dict[str, Any]] = []
    for agent in rows:
        name = str(agent.name or "")
        slug = str(agent.slug or "")
        if not (name.startswith("AI Demo") or slug.startswith("ai-demo-")):
            continue
        telnyx = str(agent.telnyx_assistant_id or "").strip()
        if not telnyx:
            results.append({"agent_id": agent.id, "name": name, "ok": False, "error": "missing_telnyx"})
            continue
        out = ensure_ai_demo_assistant_tools(db, telnyx)
        results.append({"agent_id": agent.id, "name": name, "slug": slug, **out})
    ok = sum(1 for r in results if r.get("ok"))
    return {"ok": ok == len(results) and bool(results), "synced": ok, "total": len(results), "results": results}
