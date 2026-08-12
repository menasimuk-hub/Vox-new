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
    session_prop = _str_prop("Required: DEMO_SESSION_ID from the system prompt (demo session UUID)")
    specs: list[tuple[str, str, dict[str, Any]]] = [
        (
            "switch_kb",
            "Switch the active product knowledge base and open that dashboard page "
            "(recruitment, surveys, feedback, expo, smart_card).",
            _body(
                {
                    "session_id": session_prop,
                    "service": _str_prop("Product code: recruitment|surveys|feedback|expo|smart_card"),
                    "service_code": _str_prop("Alias for service"),
                },
                ["session_id", "service"],
            ),
        ),
        (
            "highlight_dashboard",
            "Spotlight the live control BEFORE you talk. Always show the highlight box. "
            "VIEW (home_kpis, home_second_row, wizard_*): box title is the area name — never say click here. "
            "CLICK (nav_*, results_* tabs, wizard_next): box says Click here — ask them to tap, then wait. "
            "On wizard steps: highlight, tell them the step name, then STAY QUIET so they can read. Do not answer the form. "
            "Default action=highlight (do NOT navigate). "
            "Use action=navigate only if they ask you to open it or stalled and said yes. "
            "PREFERRED step=: home_kpis|home_second_row|"
            "nav_feedback_results|results_top_menus|results_overview|results_questions|results_responses|results_details|"
            "nav_feedback_compare|nav_feedback_new|"
            "wizard_industry|wizard_topics|wizard_look|wizard_branches|wizard_followup|wizard_launch|wizard_next|"
            "nav_feedback_campaigns|feedback_compare|packages_feedback. "
            "Include a short label that NAMES the area (not the words Click here).",
            _body(
                {
                    "session_id": session_prop,
                    "step": _str_prop(
                        "Preferred curated step id e.g. home_kpis, nav_feedback_results, results_overview"
                    ),
                    "demo_step": _str_prop("Alias for step"),
                    "action": _str_prop("highlight|navigate|filter|open_chart — default highlight; navigate only if they asked you to open it"),
                    "section": _str_prop("Fallback menu/section if step omitted"),
                    "target": _str_prop("Optional alias or path e.g. /expo"),
                    "menu": _str_prop("Alias for section"),
                    "page": _str_prop("Alias for section"),
                    "route": _str_prop("Optional absolute path"),
                    "target_element_id": _str_prop("data-demo-target id if not using step="),
                    "element_id": _str_prop("Alias for target_element_id"),
                    "label": _str_prop("Short on-screen coachmark text e.g. Create QR survey"),
                    "pointer": {"type": "boolean", "description": "Show pointer (default true)"},
                    "show_pointer": {"type": "boolean", "description": "Alias for pointer"},
                    "location": _str_prop("Location filter e.g. Leeds"),
                    "range": _str_prop("Optional range e.g. 6mo"),
                    "view": _str_prop("Optional smart_card view: rep|manager"),
                    "delay_ms": {"type": "integer", "description": "UI lead delay ms (200-500)"},
                },
                ["session_id"],
            ),
        ),
        (
            "show_result_panel",
            "Show a JSON/result panel on the demo UI (legacy companion panel).",
            _body(
                {
                    "session_id": session_prop,
                    "data": {"type": "object", "description": "Panel payload"},
                    "json": {"type": "object"},
                },
                ["session_id"],
            ),
        ),
        (
            "show_link",
            "Show an external link card on the demo UI.",
            _body(
                {
                    "session_id": session_prop,
                    "url": _str_prop("Absolute https URL"),
                    "label": _str_prop("Button label"),
                },
                ["session_id", "url"],
            ),
        ),
        (
            "show_qr_code",
            "Show a real scannable QR so the visitor can try the product live. "
            "Go quiet while they scan.",
            _body(
                {
                    "session_id": session_prop,
                    "service": _str_prop("feedback|expo|smart_card"),
                    "label": _str_prop("QR card title"),
                    "data": _str_prop("Optional absolute URL override"),
                    "url": _str_prop("Optional absolute URL override"),
                },
                ["session_id"],
            ),
        ),
        (
            "show_pricing",
            "Open Packages pricing on the correct service tab (core|feedback|expo|smartCard). "
            "Explain differences and recommend. Never invent discounts — sales will send the best offer.",
            _body(
                {
                    "session_id": session_prop,
                    "recommendation": _str_prop("e.g. Growth"),
                    "recommend": _str_prop("Alias for recommendation"),
                    "service": _str_prop("Product context — maps to packages ?tab="),
                },
                ["session_id"],
            ),
        ),
        (
            "request_sales_offer",
            "Flag the lead so sales will send the best offer. Do not email a promo yourself.",
            _body(
                {
                    "session_id": session_prop,
                    "note": _str_prop("Short note for sales"),
                    "summary": _str_prop("Alias for note"),
                    "volumes": {"type": "object", "description": "Optional volume needs"},
                },
                ["session_id"],
            ),
        ),
        (
            "set_voice_lang",
            "Switch spoken language / voice preference for the session.",
            _body(
                {
                    "session_id": session_prop,
                    "lang": _str_prop("en|ar"),
                    "language": _str_prop("Alias for lang"),
                    "voice": _str_prop("Optional voice id"),
                },
                ["session_id"],
            ),
        ),
        (
            "end_demo",
            "End the demo session with a short summary and book-sales CTA.",
            _body(
                {
                    "session_id": session_prop,
                    "summary": _str_prop("Needs summary for sales"),
                    "transcript": _str_prop("Optional transcript snippet"),
                },
                ["session_id"],
            ),
        ),
        (
            "log_volume_needs",
            "Capture expected volumes (locations, interviews/month, show size, team size).",
            _body(
                {
                    "session_id": session_prop,
                    "volumes": {"type": "object", "description": "Volume needs object"},
                },
                ["session_id"],
            ),
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
    """Replace AI Demo webhook tools by name; keep unrelated tools.

    Important: do NOT include a hangup tool in the PATCH/POST body. Telnyx
    auto-attaches hangup; sending hangup while one already exists returns
    HTTP 400 ("Only one tool of type hangup is allowed").
    """
    current = [t for t in (existing_tools or []) if isinstance(t, dict)]
    desired_webhooks = {
        name: tool
        for name, tool in ((_webhook_tool_name(t), t) for t in build_ai_demo_webhook_tools())
        if name
    }
    desired_names = set(desired_webhooks.keys())

    kept: list[dict[str, Any]] = []
    for tool in current:
        ttype = str(tool.get("type") or "").lower()
        if ttype == "hangup":
            continue  # Telnyx owns hangup — never re-send
        name = _webhook_tool_name(tool)
        if name and name in desired_names:
            continue  # replaced below
        kept.append(tool)

    for name in DEFAULT_TOOL_SUBSET:
        tool = desired_webhooks.get(name)
        if tool:
            kept.append(tool)
    return kept


def ensure_ai_demo_assistant_tools(
    db: Session,
    assistant_id: str,
    *,
    existing: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """PATCH Telnyx assistant tools with AI Demo webhook endpoints (no hangup in body)."""
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    live = existing if isinstance(existing, dict) else fetch_telnyx_assistant(db, clean_id)
    current_tools = live.get("tools") if isinstance(live.get("tools"), list) else []
    desired = merge_ai_demo_tools(current_tools)

    def _webhook_sig(tools: list[Any]) -> set[str]:
        out: set[str] = set()
        for t in tools:
            if not isinstance(t, dict):
                continue
            name = _webhook_tool_name(t)
            if not name:
                continue
            wh = t.get("webhook") if isinstance(t.get("webhook"), dict) else {}
            url = str(wh.get("url") or "").strip()
            out.add(f"{name}|{url}")
        return out

    base_urls = {f"{n}|{ai_demo_tool_webhook_urls()[n]}" for n in DEFAULT_TOOL_SUBSET}
    if not force and base_urls <= _webhook_sig(current_tools):
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
        detail = str(exc)
        try:
            resp = getattr(exc, "response", None)
            if resp is not None:
                detail = f"{detail} body={resp.text[:500]}"
        except Exception:
            pass
        logger.warning("ensure_ai_demo_tools_failed assistant_id=%s err=%s", clean_id, detail)
        return {
            "ok": False,
            "changed": False,
            "assistant_id": clean_id,
            "tool_count": len(current_tools),
            "error": detail[:500],
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
