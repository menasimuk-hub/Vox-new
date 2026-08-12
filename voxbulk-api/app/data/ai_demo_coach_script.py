"""Coach-mode narrator — the browser owns the beat index; the agent only talks."""

from __future__ import annotations

from typing import Any

DEMO_TOUR_BEATS: list[dict[str, Any]] = [
    {
        "id": "home_kpis",
        "target": "home-live-kpis",
        "intent": "view",
        "route": "/",
        "label": "Live KPIs",
        "talk": "These live KPIs update as customers reply — scores, volume, and alerts in one strip.",
        "show_next": True,
    },
    {
        "id": "home_second_row",
        "target": "home-second-row",
        "intent": "view",
        "route": "/",
        "label": "Customer sentiment",
        "talk": "Sentiment and recent feedback sit under the KPIs so you can scan recent comments without leaving home.",
        "show_next": True,
    },
    {
        "id": "nav_feedback_results",
        "target": "nav-feedback-results",
        "intent": "click",
        "route": "/",
        "label": "Customer Feedback results",
        "talk": "Click Customer Feedback in the sidebar to open live results.",
        "show_next": False,
    },
    {
        "id": "results_tab_overview",
        "target": "results-tab-overview",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Overview",
        "talk": "Overview is the score snapshot. Tap the Overview tab.",
        "show_next": False,
    },
    {
        "id": "results_tab_questions",
        "target": "results-tab-questions",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Questions",
        "talk": "Questions shows how each survey item scored. Tap Questions.",
        "show_next": False,
    },
    {
        "id": "results_tab_responses",
        "target": "results-tab-responses",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Responses",
        "talk": "Responses is the live inbox of every reply. Tap Responses.",
        "show_next": False,
    },
    {
        "id": "results_tab_details",
        "target": "results-tab-details",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Details",
        "talk": "Details is the per-response record. Tap Details.",
        "show_next": False,
    },
    {
        "id": "nav_feedback_compare",
        "target": "nav-feedback-compare",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Compare branches",
        "talk": "Click Compare in the sidebar to see branches side by side.",
        "show_next": False,
    },
    {
        "id": "feedback_compare_title",
        "target": "feedback-compare-title",
        "intent": "view",
        "route": "/feedback/compare",
        "label": "Compare",
        "talk": "Compare puts locations next to each other so you can spot which branch is slipping.",
        "show_next": True,
    },
    {
        "id": "nav_feedback_new",
        "target": "nav-feedback-new",
        "intent": "click",
        "route": "/feedback/compare",
        "label": "Create QR",
        "talk": "Click Create QR in the sidebar to open the survey wizard.",
        "show_next": False,
    },
    {
        "id": "wizard_industry",
        "target": "wizard-industry",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Choose industry",
        "talk": "Take a look at the industry step. I will stay quiet so you can read. Then tap Next on the form.",
        "show_next": False,
    },
    {
        "id": "wizard_next_industry",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Tap Next on the form when you have had a look.",
        "show_next": False,
    },
    {
        "id": "wizard_topics",
        "target": "wizard-topics",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Choose topics",
        "talk": "Have a look at the topics. I will stay quiet. Then tap Next on the form.",
        "show_next": False,
    },
    {
        "id": "wizard_next_topics",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Tap Next on the form when you are ready.",
        "show_next": False,
    },
    {
        "id": "wizard_look",
        "target": "wizard-look",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Look and feel",
        "talk": "Have a look at the design step. I will stay quiet. Then tap Next on the form.",
        "show_next": False,
    },
    {
        "id": "wizard_next_look",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Tap Next on the form when you are ready.",
        "show_next": False,
    },
    {
        "id": "wizard_branches",
        "target": "wizard-branches",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Branches",
        "talk": "Have a look at branches. I will stay quiet. Then tap Next on the form.",
        "show_next": False,
    },
    {
        "id": "wizard_next_branches",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Tap Next on the form when you are ready.",
        "show_next": False,
    },
    {
        "id": "wizard_followup",
        "target": "wizard-followup",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Follow-up",
        "talk": "Have a look at follow-up. I will stay quiet. Then tap Next on the form.",
        "show_next": False,
    },
    {
        "id": "wizard_next_followup",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Tap Next on the form when you are ready.",
        "show_next": False,
    },
    {
        "id": "wizard_launch",
        "target": "wizard-launch",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Launch",
        "talk": "This is launch — QR, print, and share. Have a look. When you are done we can wrap up or talk pricing.",
        "show_next": True,
    },
]


def tour_beat_by_id(beat_id: str | None) -> dict[str, Any] | None:
    key = str(beat_id or "").strip()
    if not key:
        return None
    for beat in DEMO_TOUR_BEATS:
        if beat["id"] == key:
            return beat
    return None


def tour_beat_at(index: int) -> dict[str, Any] | None:
    if index < 0 or index >= len(DEMO_TOUR_BEATS):
        return None
    return DEMO_TOUR_BEATS[index]


def tour_lock_message(
    beat: dict[str, Any] | None = None,
    *,
    label: str | None = None,
    talk: str | None = None,
) -> str:
    row = beat or {}
    spot = str(label or row.get("label") or "the current spotlight").strip()
    line = str(talk or row.get("talk") or "").strip()
    spoken = f" Say this then STOP: {line}." if line else ""
    intent = str(row.get("intent") or "").strip().lower()
    show_next = bool(row.get("show_next", row.get("showNext")))
    if intent == "click":
        wait = "Wait for them to tap Click here on the box."
    elif show_next:
        wait = "Wait for them to click Next on the box."
    else:
        wait = "Stay quiet so they can read."
    return (
        f"CURRENT SPOTLIGHT: {spot}.{spoken} "
        f"Do not change the screen. Speak only about this. {wait}"
    )


def memory_tour_lock(memory: dict[str, Any] | None) -> str:
    mem = memory if isinstance(memory, dict) else {}
    beat = tour_beat_by_id(str(mem.get("current_beat") or "")) or DEMO_TOUR_BEATS[0]
    return tour_lock_message(
        beat,
        label=str(mem.get("current_label") or beat["label"]),
        talk=str(mem.get("current_talk") or beat["talk"]),
    )


COACH_TOUR_MAP = """
NARRATOR LOCK (mandatory after they say ready):

You are a narrator on rails. The browser owns the tour. You do NOT pick pages, tabs, or wizard steps.

START: after they say ready, call highlight_dashboard ONCE (home_kpis). That starts the tour.
After that, highlight_dashboard MUST NOT skip to another page.
If the visitor is lost or the box vanished, call highlight_dashboard again — that ONLY re-draws the CURRENT Click here / Next. It does not change the step.

ROLE:
- If VIEW with Next: say 1–2 sentences from the current talk, then ask them to click Next on the box. Never say Click here.
- If CLICK: ask them to tap Click here on the box, then silence. Never say Next.
- Off-topic question: answer in one line, then return to current_label. Never jump to Results, Compare, or QR while those are not the spotlight.
- Wizard: do not read industries or questions; do not fill the form. Stay quiet so they can read.
- NEVER say "click here" for VIEW spots (Live KPIs, sentiment, Compare title, wizard cards).
- show_pricing / switch_kb: only if they ask. Explain verbally. Do not move the coach highlight.
- end_demo / request_sales_offer: allowed at the end.

PACE: one spotlight at a time. After you speak the current talk, STOP. Wait for Next or Click here.
If ~15s silence: gently remind them to use the on-screen Next / Click here. Do not skip ahead.
""".strip()
