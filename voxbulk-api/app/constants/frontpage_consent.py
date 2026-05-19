"""Short recording and consent lines for voice agents (not legal advice)."""

# —— Website Talk to us (intake) ——

RECORDING_NOTICE_SHORT = (
    'Once near the start, say briefly: "This call is recorded for quality — privacy details are on voxbulk.com." '
    "Say it only once. Do not repeat unless they ask."
)

PHONE_CONFIRM_ONCE_RULE = (
    "You already have their mobile number from the website form. Confirm it exactly once: read it back once "
    'and ask "Is that still correct?" If they confirm yes, do not ask again in this call. '
    "Only mention the number again if they correct it or request a callback on a different number."
)

UK_CALLBACK_CONSENT_SHORT = (
    'If they want a sales callback, ask once in plain language: "Are you happy for our team to call you back '
    'on that number about this enquiry?" Only schedule if they clearly say yes. No long legal script.'
)

# Legacy alias for imports that still reference the old name
UK_CALLBACK_RECORDING_CONSENT_SCRIPT = UK_CALLBACK_CONSENT_SHORT

INTAKE_CONVERSATION_PACE = (
    "Keep turns short (one or two sentences). Move the conversation forward — do not loop on the same question."
)

INTAKE_OPERATOR_DESCRIPTION_SUFFIX = (
    f" {RECORDING_NOTICE_SHORT} {PHONE_CONFIRM_ONCE_RULE} "
    "If they want pricing, a demo, or a sales follow-up, agree a callback time in their local timezone "
    f"(UK, Australia, or Canada). {UK_CALLBACK_CONSENT_SHORT} "
    f"{INTAKE_CONVERSATION_PACE}"
)

# —— Outbound lead sales ——

SALES_RECORDING_NOTICE_SHORT = (
    'At the very start of the call, say once: "This call is recorded for quality — see voxbulk.com for privacy." '
    "Then continue with the sales conversation. Do not repeat unless asked."
)

SALES_OPERATOR_DESCRIPTION_SUFFIX = (
    f" {SALES_RECORDING_NOTICE_SHORT} Keep responses concise."
)
