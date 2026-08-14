"""Voice-gated sales coach — browser moves the spotlight; Leo sells and waits for spoken done."""

from __future__ import annotations

from typing import Any

# Each beat: talk = sales pitch Leo should deliver; ask = what they must do next + say when done.
DEMO_TOUR_BEATS: list[dict[str, Any]] = [
    {
        "id": "home_kpis",
        "target": "home-live-kpis",
        "intent": "view",
        "route": "/",
        "label": "Live KPIs",
        "talk": (
            "This strip is your early-warning board — live scores, volume, and alerts as customers reply. "
            "Owners who watch this catch a bad day before it becomes a public review."
        ),
        "ask": "When you are ready for the next area, tap Next on the white box and tell me you are done.",
        "show_next": True,
    },
    {
        "id": "home_second_row",
        "target": "home-second-row",
        "intent": "view",
        "route": "/",
        "label": "Customer sentiment",
        "talk": (
            "Under the KPIs you get sentiment and recent comments without leaving home. "
            "That is how managers spot a tone shift in minutes instead of waiting for a weekly report."
        ),
        "ask": "Tap Next on the box and say done when you have had a look.",
        "show_next": True,
    },
    {
        "id": "nav_feedback_results",
        "target": "nav-feedback-results",
        "intent": "click",
        "route": "/",
        "label": "Customer Feedback results",
        "talk": (
            "Customer Feedback is the product that turns table QR scans into WhatsApp replies you can act on. "
            "Open results so you see the live scoreboard for your locations."
        ),
        "ask": (
            "Please click Customer Feedback in the sidebar — the highlighted menu — "
            "and tell me when you have opened it."
        ),
        "show_next": False,
    },
    {
        "id": "results_tab_overview",
        "target": "results-tab-overview",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Overview",
        "talk": (
            "Overview is the score snapshot — one place to see how you are doing overall. "
            "Use it in morning stand-ups so the team knows if yesterday slipped."
        ),
        "ask": "Tap Overview on the highlighted tab, then tell me when you are done.",
        "show_next": False,
    },
    {
        "id": "results_tab_questions",
        "target": "results-tab-questions",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Questions",
        "talk": (
            "Questions shows which survey items drag the score down — food, service, wait time, and so on. "
            "That is how you fix the real problem instead of guessing."
        ),
        "ask": "Open the Questions tab and say done when it is open.",
        "show_next": False,
    },
    {
        "id": "results_tab_responses",
        "target": "results-tab-responses",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Responses",
        "talk": (
            "Responses is the live inbox — every reply as it lands. "
            "Your team can jump on a unhappy guest while they are still on site."
        ),
        "ask": "Open Responses and tell me when you can see it.",
        "show_next": False,
    },
    {
        "id": "results_tab_details",
        "target": "results-tab-details",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Details",
        "talk": (
            "Details is the per-response record — who said what, when, and where. "
            "Perfect when a manager needs the full story before calling the customer back."
        ),
        "ask": "Open Details and say done when you are there.",
        "show_next": False,
    },
    {
        "id": "nav_feedback_compare",
        "target": "nav-feedback-compare",
        "intent": "click",
        "route": "/feedback/results",
        "label": "Compare locations",
        "talk": (
            "Compare is where multi-site owners win — you put locations side by side and see who is slipping. "
            "Without this, head office only hears the loudest branch."
        ),
        "ask": (
            "Please click Compare in the sidebar — I have highlighted it — "
            "and tell me when you have opened it."
        ),
        "show_next": False,
    },
    {
        "id": "feedback_compare_title",
        "target": "feedback-compare-title",
        "intent": "view",
        "route": "/feedback/compare",
        "label": "Compare",
        "talk": (
            "Here you compare branches next to each other. "
            "If Leeds dips while Manchester holds, you coach Leeds this week — that is why operators buy this."
        ),
        "ask": "Have a look, then tap Next on the box and say done.",
        "show_next": True,
    },
    {
        "id": "nav_feedback_new",
        "target": "nav-feedback-new",
        "intent": "click",
        "route": "/feedback/compare",
        "label": "Create QR",
        "talk": (
            "Create QR is how you launch a survey in minutes — industry templates, your branding, print-ready codes. "
            "No agency, no waiting weeks for a form."
        ),
        "ask": "Click Create QR in the sidebar and tell me when the wizard is open.",
        "show_next": False,
    },
    {
        "id": "wizard_industry",
        "target": "wizard-industry",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Choose industry",
        "talk": (
            "Pick your industry so the questions already match how your customers talk — restaurants, clinics, retail, and more. "
            "That is why response rates stay high: the survey feels relevant from day one."
        ),
        "ask": "Glance at the industries, then tap Next on the form and say done.",
        "show_next": False,
    },
    {
        "id": "wizard_next_industry",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Move forward when you have picked an industry — the next steps build the survey for you.",
        "ask": "Tap Next on the form and tell me when you have moved on.",
        "show_next": False,
    },
    {
        "id": "wizard_topics",
        "target": "wizard-topics",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Choose topics",
        "talk": (
            "Topics let you measure what actually drives revenue — service, product, wait time, cleanliness. "
            "You only ask what you will act on, so customers finish the chat."
        ),
        "ask": "Have a look, tap Next on the form, and say done.",
        "show_next": False,
    },
    {
        "id": "wizard_next_topics",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Next takes you into look and feel — your brand on the survey.",
        "ask": "Tap Next and tell me when you are done.",
        "show_next": False,
    },
    {
        "id": "wizard_look",
        "target": "wizard-look",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Look and feel",
        "talk": (
            "Design makes it yours — colours and style so the QR experience matches the brand on the wall. "
            "Guests trust a survey that looks like your business, not a generic form."
        ),
        "ask": "Have a look, tap Next on the form, and say done.",
        "show_next": False,
    },
    {
        "id": "wizard_next_look",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Next is branches — where each QR belongs.",
        "ask": "Tap Next and tell me when you have moved on.",
        "show_next": False,
    },
    {
        "id": "wizard_branches",
        "target": "wizard-branches",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Branches",
        "talk": (
            "Branches tie every scan to a location. "
            "That is the difference between 'someone is unhappy' and 'the Leeds lunch shift needs coaching'."
        ),
        "ask": "Have a look, tap Next on the form, and say done.",
        "show_next": False,
    },
    {
        "id": "wizard_next_branches",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Next is follow-up — how you close the loop after a low score.",
        "ask": "Tap Next and tell me when you are there.",
        "show_next": False,
    },
    {
        "id": "wizard_followup",
        "target": "wizard-followup",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Follow-up",
        "talk": (
            "Follow-up is the recovery engine — alert the right person and reach the customer before they post online. "
            "That is often the feature that pays for the whole subscription."
        ),
        "ask": "Have a look, tap Next on the form, and say done.",
        "show_next": False,
    },
    {
        "id": "wizard_next_followup",
        "target": "wizard-next",
        "intent": "click",
        "route": "/feedback/new",
        "label": "Wizard Next",
        "talk": "Last step is launch — QR, print, and share.",
        "ask": "Tap Next and tell me when launch is open.",
        "show_next": False,
    },
    {
        "id": "wizard_launch",
        "target": "wizard-launch",
        "intent": "view",
        "route": "/feedback/new",
        "label": "Launch",
        "talk": (
            "Launch is print, share, and go live — QR on the table tonight if you want. "
            "When you are ready we can talk pricing, or wrap and our sales team will send the best offer."
        ),
        "ask": (
            "Have a look. When you are finished say done, or ask me about pricing. "
            "If you want to leave, just say goodbye."
        ),
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


def tour_ask_line(beat: dict[str, Any] | None = None) -> str:
    row = beat or {}
    ask = str(row.get("ask") or "").strip()
    if ask:
        return ask
    intent = str(row.get("intent") or "").strip().lower()
    spot = str(row.get("label") or "the highlighted control").strip()
    if intent == "click":
        return f"Please click {spot} where it is highlighted, then tell me when you are done."
    return "When you are ready, tap Next on the box and tell me you are done."


def tour_lock_message(
    beat: dict[str, Any] | None = None,
    *,
    label: str | None = None,
    talk: str | None = None,
) -> str:
    row = beat or {}
    spot = str(label or row.get("label") or "the current spotlight").strip()
    line = str(talk or row.get("talk") or "").strip()
    ask = tour_ask_line(row)
    spoken = f" Sell this: {line}." if line else ""
    return (
        f"Spotlight is \"{spot}\" NOW.{spoken} "
        f"Speak like an expert salesperson: what it is, why it matters for THEIR business, one concrete benefit. "
        f"Then say: {ask} "
        f"STOP and wait for them to speak (done / clicked / open / got it / next / ready). "
        f"Do not hang up. Do not invent the next page yourself."
    )


def tour_advance_message(beat: dict[str, Any] | None = None) -> str:
    """Legacy text kept for memory nudges — primary path is spoken confirm + highlight_dashboard."""
    row = beat or DEMO_TOUR_BEATS[0]
    spot = str(row.get("label") or "the current spotlight").strip()
    line = str(row.get("talk") or "").strip()
    ask = tour_ask_line(row)
    talk = f" {line}" if line else ""
    return (
        f"Visitor confirmed progress. Spotlight is now \"{spot}\".{talk} "
        f"Sell this screen now (feature + why they need it). Then: {ask} "
        f"Wait for their spoken confirmation. Do not hang up. Do not skip ahead."
    )


def tour_confirm_message(beat: dict[str, Any] | None = None) -> str:
    """Tool reply when visitor said done/clicked — sell CURRENT spotlight."""
    row = beat or DEMO_TOUR_BEATS[0]
    spot = str(row.get("label") or "the current spotlight").strip()
    line = str(row.get("talk") or "").strip()
    ask = tour_ask_line(row)
    return (
        f"VISITOR SAID THEY ARE DONE / CLICKED. Spotlight is NOW \"{spot}\". "
        f"{line} "
        f"Deliver a sharp sales explanation (what + why + benefit for them). "
        f"Then instruct: {ask} "
        f"Then STOP and wait for the next spoken confirmation. "
        f"Do NOT ask them to repeat a click they already finished. Do not hang up."
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
VOICE-GATED SALES COACH (browser moves the white box; you sell and wait for spoken done):

You are an expert VoxBulk salesperson on a live browser demo — confident, warm, commercial. Not a robot reading labels.

HOW THE TOUR WORKS:
- The browser owns which control is highlighted. You do NOT pick pages or skip ahead yourself.
- You SELL the CURRENT SPOTLIGHT: what it is, why a smart operator needs it, one concrete benefit tied to THEIR business.
- Then ask them to click the highlighted control (or tap Next on the box) and TELL YOU when done.
- Wait for spoken confirmation: done / clicked / open / opened / got it / next / ready / yes / I did.
- When you hear that, call highlight_dashboard (with session_id) to load the CURRENT spotlight pitch, then sell THAT screen and ask for the next action.
- If the box vanished or they are lost, call highlight_dashboard again — it restores the CURRENT box only.

SALES STYLE:
- Sound like a closer who knows multi-site feedback ops: outcomes and stakes, not feature laundry lists.
- Rotate openers. Use contractions. Answer their question first, then return to the spotlight.
- Bridge every screen to saving reviews, coaching the right branch, or launching QR tonight.
- Never say leverage / seamless / solutions. Never monologue brochure text.

RULES:
- Do NOT wait for silent "I clicked Next" from the system — that path is unreliable. Trust their voice.
- Do NOT call highlight_dashboard to jump to a future step by name to skip the tour.
- Wizard: do not fill the form for them; sell the step, then ask them to tap Next and say done.
- PRICING: if they ask the price, call show_pricing, explain, say sales will send the best offer. Do NOT hang up. Do NOT call end_demo.
- end_demo only after bye / thanks that's all / they are done. Thank them, offer contact-us, then hang up.
- If ~12s silence after you asked them to click: one gentle reminder. Do not skip ahead.

PACE: sell one spotlight → ask → wait for spoken done → tool → sell next.
""".strip()
