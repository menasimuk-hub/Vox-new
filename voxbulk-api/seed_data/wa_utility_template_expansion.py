"""Utility-safe topic replacements and 5-topic expansion for WA Survey + Feedback seeds."""

from __future__ import annotations

from typing import Any

# Replace risky topic names + utility-compliant bodies (emoji + transaction anchor)
SURVEY_TOPIC_REPLACEMENTS: dict[str, tuple[str, str]] = {
    "Would recommend": (
        "Overall service satisfaction",
        "😊 Following your recent visit, how satisfied are you with the service you received today?",
    ),
    "Return intent": (
        "Visit met your needs",
        "✅ Following your recent visit, did our service meet your needs today?",
    ),
    "Renewal intent": (
        "Tenancy needs met",
        "📋 Following your recent tenancy interaction, did our service meet your needs?",
    ),
    "Repeat purchase intent": (
        "Purchase met your needs",
        "✅ Following your recent order, did your purchase meet your needs today?",
    ),
    "Repeat use intent": (
        "Delivery met your needs",
        "✅ Following your recent delivery, did the service meet your needs today?",
    ),
    "Referral likelihood": (
        "Service satisfaction today",
        "😊 Following your recent visit, how satisfied are you with our service today?",
    ),
    "Loyalty programme value": (
        "Checkout clarity",
        "🧾 Following your recent purchase, how clear was the checkout process today?",
    ),
}

SURVEY_BODY_PATCHES: list[tuple[str, str]] = [
    ("Would you recommend", "Following your recent visit, how satisfied are you with the service you received today?"),
    ("Would you choose our clinic again", "Following your recent visit, did our service meet your needs today?"),
    ("How likely are you to dine with us again", "Following your recent visit, did our service meet your needs today?"),
    ("Would you stay with us again", "Following your recent stay, did our service meet your needs today?"),
    ("Are you likely to renew your tenancy", "Following your recent tenancy interaction, did our service meet your needs today?"),
    ("How valuable do you find our loyalty programme", "Following your recent purchase, how clear was the checkout process today?"),
]

EXTRA_SURVEY_TOPICS: list[dict[str, Any]] = [
    {
        "name": "Issue resolution rating",
        "body": "⚙️ Following your recent visit, how satisfied were you with how any issue was handled?",
        "options": ["Unsatisfied", "Satisfied", "Very satisfied"],
    },
    {
        "name": "Information clarity",
        "body": "💬 Following your recent visit, how clear was the information provided to you?",
        "options": ["Unclear", "Clear", "Very clear"],
    },
    {
        "name": "Hand-off wait time",
        "body": "⏱️ Following your recent visit, how acceptable was your wait or hand-off time?",
        "options": ["Too long", "Acceptable", "Very short"],
    },
    {
        "name": "Facility access comfort",
        "body": "🚪 Following your recent visit, how comfortable was access to our facility?",
        "options": ["Difficult", "Comfortable", "Very easy"],
    },
    {
        "name": "Overall experience today",
        "body": "🌟 Following your recent visit, how would you rate your overall experience today?",
        "options": ["Poor", "Good", "Excellent"],
    },
]

FEEDBACK_TOPIC_REPLACEMENTS: dict[str, tuple[str, str, list[str]]] = {
    "02 – Would recommend": (
        "02 – Service satisfaction",
        "😊 Following your recent visit, how satisfied are you with the service you received today?",
        ["Very satisfied", "Satisfied", "Dissatisfied"],
    ),
    "10 – Return intent": (
        "10 – Visit met your needs",
        "✅ Following your recent visit, did our service meet your needs today?",
        ["Yes, fully", "Partly", "No"],
    ),
    "17 – Promotions clarity": (
        "17 – Price label clarity",
        "🏷️ Following your recent visit, how clear were price labels and charges today?",
        ["Very clear", "Mostly clear", "Unclear"],
    ),
    "18 – Loyalty programme": (
        "18 – Checkout clarity",
        "🧾 Following your recent purchase, how clear was the checkout process today?",
        ["Very clear", "Mostly clear", "Unclear"],
    ),
}

EXTRA_FEEDBACK_TOPICS: list[tuple[str, str, list[str]]] = [
    (
        "21 – Issue resolution",
        "⚙️ Following your recent visit, how satisfied were you with how any issue was handled?",
        ["Very satisfied", "Satisfied", "Dissatisfied"],
    ),
    (
        "22 – Information clarity",
        "💬 Following your recent visit, how clear was the information provided to you?",
        ["Very clear", "Clear", "Unclear"],
    ),
    (
        "23 – Hand-off wait time",
        "⏱️ Following your recent visit, how acceptable was your wait or hand-off time?",
        ["Very short", "Acceptable", "Too long"],
    ),
    (
        "24 – Facility access comfort",
        "🚪 Following your recent visit, how comfortable was access to our premises?",
        ["Very easy", "Comfortable", "Difficult"],
    ),
    (
        "25 – Overall experience today",
        "🌟 Following your recent visit, how would you rate your overall experience today?",
        ["Excellent", "Good", "Poor"],
    ),
]

FEEDBACK_BODY_PATCHES: list[tuple[str, str]] = [
    ("We hope you enjoyed your visit. Would you recommend", "Following your recent visit, how satisfied are you with the service you received today?"),
    ("We hope you left feeling great. Would you recommend", "Following your recent visit, how satisfied are you with the service you received today?"),
    ("We hope you enjoyed your stay. Would you recommend", "Following your recent stay, how satisfied are you with the service you received?"),
    ("We hope you had a great session. Would you recommend", "Following your recent session, how satisfied are you with the service you received today?"),
    ("We would love to see you again. Would you visit us again", "Following your recent visit, did our service meet your needs today?"),
    ("Did our menu offer enough variety", "Following your recent visit, how satisfied were you with the menu selection available today?"),
    ("Were promotions and discounts clearly displayed", "Following your recent visit, how clear were price labels and charges today?"),
    ("How satisfied are you with our loyalty rewards programme", "Following your recent purchase, how clear was the checkout process today?"),
]
