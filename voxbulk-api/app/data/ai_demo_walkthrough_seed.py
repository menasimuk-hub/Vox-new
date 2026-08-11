"""Compare-ready dummy data for AI Demo walkthrough panels (session fixtures only)."""

from __future__ import annotations

from typing import Any

# Story: Leeds dipping, Manchester flat, Bristol improving.
FEEDBACK_WALKTHROUGH: dict[str, Any] = {
    "service": "feedback",
    "locations": [
        {"id": "leeds", "name": "Leeds", "trend": "down", "latest_score": 3.9},
        {"id": "manchester", "name": "Manchester", "trend": "flat", "latest_score": 4.4},
        {"id": "bristol", "name": "Bristol", "trend": "up", "latest_score": 4.7},
    ],
    "months": ["Mar", "Apr", "May", "Jun", "Jul", "Aug"],
    "scores_by_location": {
        "leeds": [4.6, 4.5, 4.4, 4.2, 4.0, 3.9],
        "manchester": [4.3, 4.4, 4.3, 4.4, 4.4, 4.4],
        "bristol": [4.1, 4.2, 4.3, 4.5, 4.6, 4.7],
    },
    "story_lines": [
        "Leeds dipped from 4.6 to 3.9 over two months — the kind of slide Google reviews miss.",
        "Manchester is steady around 4.4.",
        "Bristol climbed from 4.1 to 4.7 — something is working there.",
    ],
    "sample_responses": [
        {"id": "r1", "location": "leeds", "score": 2, "category": "service", "comment": "Waited twenty minutes for the bill."},
        {"id": "r2", "location": "leeds", "score": 3, "category": "food", "comment": "Food was fine but tables felt rushed."},
        {"id": "r3", "location": "manchester", "score": 5, "category": "service", "comment": "Staff were brilliant — back next week."},
        {"id": "r4", "location": "bristol", "score": 5, "category": "cleanliness", "comment": "Place looked spotless."},
        {"id": "r5", "location": "bristol", "score": 4, "category": "food", "comment": "Loved the new lunch menu."},
    ],
    "live_qr_path": "/demo/live-feedback",
}

SURVEYS_WALKTHROUGH: dict[str, Any] = {
    "service": "surveys",
    "segments": [
        {"id": "employees", "name": "Employees", "response_rate": 0.81, "avg_minutes": 0.9, "sentiment": {"pos": 62, "neu": 28, "neg": 10}},
        {"id": "candidates", "name": "Candidates", "response_rate": 0.74, "avg_minutes": 1.1, "sentiment": {"pos": 55, "neu": 30, "neg": 15}},
        {"id": "customers", "name": "Customers", "response_rate": 0.88, "avg_minutes": 0.7, "sentiment": {"pos": 71, "neu": 20, "neg": 9}},
    ],
    "months": ["May", "Jun", "Jul", "Aug"],
    "response_rates": {
        "employees": [0.72, 0.76, 0.79, 0.81],
        "candidates": [0.68, 0.70, 0.72, 0.74],
        "customers": [0.80, 0.83, 0.86, 0.88],
    },
    "voice_note": {
        "label": "Voice note (translated)",
        "original_lang": "ar",
        "transcript_en": "The WhatsApp survey was quick — I finished it on the bus in under a minute.",
    },
    "story_lines": [
        "Customers open and finish fastest — about 88% response rate.",
        "One voice note came in Arabic; translation shows on the results panel live.",
    ],
}

RECRUITMENT_WALKTHROUGH: dict[str, Any] = {
    "service": "recruitment",
    "role": "Senior Engineer",
    "candidates": [
        {"id": "c1", "name": "Amira K.", "ats": 92, "skills": 90, "comms": 88, "fit": 94, "status": "Shortlist"},
        {"id": "c2", "name": "James T.", "ats": 86, "skills": 84, "comms": 90, "fit": 82, "status": "Booked"},
        {"id": "c3", "name": "Priya S.", "ats": 79, "skills": 81, "comms": 76, "fit": 80, "status": "Review"},
        {"id": "c4", "name": "Omar H.", "ats": 74, "skills": 78, "comms": 70, "fit": 72, "status": "Hold"},
        {"id": "c5", "name": "Elena M.", "ats": 88, "skills": 85, "comms": 91, "fit": 87, "status": "Shortlist"},
    ],
    "calling_now": {"id": "c2", "name": "James T.", "label": "AI interview in progress"},
    "story_lines": [
        "Fifteen candidates screened automatically for Senior Engineer.",
        "James is on a live AI interview right now — you can see the calling card update.",
    ],
}

EXPO_WALKTHROUGH: dict[str, Any] = {
    "service": "expo",
    "show": "TechNorth Live 2026",
    "days": [
        {"day": "Day 1", "leads": 38},
        {"day": "Day 2", "leads": 52},
        {"day": "Day 3", "leads": 47},
    ],
    "totals": {"hot": 34, "warm": 55, "cold": 48},
    "sample_leads": [
        {"id": "e1", "name": "Nina Park", "company": "Orbit Labs", "score": "Hot", "day": "Day 2"},
        {"id": "e2", "name": "Chris Adey", "company": "Northwind", "score": "Warm", "day": "Day 1"},
        {"id": "e3", "name": "Sara Quinn", "company": "Beacon", "score": "Hot", "day": "Day 3"},
    ],
    "story_lines": [
        "About 137 booth leads across three days — Day 2 peaked at 52.",
        "Roughly a quarter are Hot — ready for a same-week follow-up.",
    ],
    "live_qr_path": "/demo/live-expo",
}

SMART_CARD_WALKTHROUGH: dict[str, Any] = {
    "service": "smart_card",
    "reps": [
        {"id": "rep1", "name": "Alex Morgan", "leads": 22, "hot": 6, "warm": 9, "cold": 7},
        {"id": "rep2", "name": "Sam Rivera", "leads": 18, "hot": 4, "warm": 8, "cold": 6},
        {"id": "rep3", "name": "Jordan Lee", "leads": 25, "hot": 8, "warm": 10, "cold": 7},
    ],
    "views": ["rep", "manager"],
    "story_lines": [
        "As a rep you only see your own attributed leads.",
        "As the owner you see everyone's Hot/Warm/Cold in one board.",
    ],
    "live_qr_path": "/demo/live-smart-card",
}

PRICING_WALKTHROUGH: dict[str, Any] = {
    "source": "https://voxbulk.com/pricing",
    "disclaimer": "Use website package language only — never invent discounts or custom rates on this call.",
    "core_summary": [
        {"code": "starter", "name": "Starter", "blurb": "Best when you are testing one product with light monthly volume."},
        {"code": "growth", "name": "Growth", "blurb": "Most teams land here — more minutes and WhatsApp room to run real campaigns."},
        {"code": "scale", "name": "Scale", "blurb": "Higher included usage when Feedback, Surveys, and interviews run together."},
        {"code": "enterprise", "name": "Enterprise", "blurb": "Custom when you need volume, SLAs, or multi-brand rollout — sales builds the offer."},
    ],
    "product_notes": {
        "feedback": "Feedback plans are location-based with WhatsApp + web response allowances — compare on /pricing.",
        "expo": "Expo is typically pay-once-per-show — different from monthly core packages.",
        "recruitment": "Interview packages are usage-based on screens — recommend Growth unless volume is tiny.",
    },
    "recommend_rules": [
        "One location / light trial → Starter.",
        "Multi-site Feedback or regular Surveys → Growth.",
        "Heavy interview + WhatsApp + Feedback together → Scale or ask sales for Enterprise.",
        "Always say: our sales team will send you the best offer for your numbers — do not invent a promo.",
    ],
}


def walkthrough_for_service(service: str) -> dict[str, Any]:
    code = str(service or "").strip().lower()
    mapping = {
        "feedback": FEEDBACK_WALKTHROUGH,
        "surveys": SURVEYS_WALKTHROUGH,
        "recruitment": RECRUITMENT_WALKTHROUGH,
        "expo": EXPO_WALKTHROUGH,
        "smart_card": SMART_CARD_WALKTHROUGH,
    }
    data = mapping.get(code)
    if not data:
        return {"service": code, "error": "unknown_service"}
    return dict(data)


def feedback_prompt_numbers() -> str:
    lines = ["DEMO DASHBOARD NUMBERS (cite these exactly when you point at the screen):"]
    lines.extend(FEEDBACK_WALKTHROUGH["story_lines"])
    lines.append("Locations: Leeds, Manchester, Bristol — six months of scores each.")
    return "\n".join(lines)


def prompt_numbers_for_service(service: str) -> str:
    data = walkthrough_for_service(service)
    stories = data.get("story_lines") or []
    if not stories:
        return ""
    return "DEMO DASHBOARD NUMBERS (cite these when you show the screen):\n" + "\n".join(f"- {s}" for s in stories)
