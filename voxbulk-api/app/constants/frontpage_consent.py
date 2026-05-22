"""Short recording and consent lines for voice agents (not legal advice)."""

# —— Website Talk to us (intake) ——

RECORDING_NOTICE_SHORT = (
    "The Telnyx greeting field already includes the recording notice. Do NOT say the recording line again in your turns."
)

PHONE_CONFIRM_ONCE_RULE = (
    "You already have their mobile from the website form. Do NOT confirm the number at the start of the call. "
    "Only read it back once near the END, before scheduling a sales callback, and ask if it is still correct. "
    "If they confirm yes, never ask again unless they give a different number."
)

VOICE_INTERRUPT_RULE = (
    "If the caller interrupts, barge-in, or asks a question mid-sentence: STOP your script immediately, "
    "answer their question in one or two short sentences, then continue naturally. "
    "Never restart the call from the opening. Never repeat a line you already said unless they ask you to."
)

VOICE_NO_REPEAT_RULE = (
    "Never repeat the same question or the same sentence twice in one call. "
    "Never read a fixed call script line-by-line. Respond to what they actually said."
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
    f" {PHONE_CONFIRM_ONCE_RULE} {VOICE_INTERRUPT_RULE} {VOICE_NO_REPEAT_RULE} "
    "If they want pricing, a demo, or a sales follow-up, agree a callback time in their local timezone "
    f"(UK, Australia, or Canada). {UK_CALLBACK_CONSENT_SHORT} "
    f"{INTAKE_CONVERSATION_PACE}"
)

# —— Outbound lead sales ——

SALES_RECORDING_NOTICE_SHORT = (
    "The Telnyx greeting field already includes the recording notice. Do NOT say the recording line again in your turns."
)

SALES_OPERATOR_DESCRIPTION_SUFFIX = (
    f" {SALES_RECORDING_NOTICE_SHORT} {VOICE_INTERRUPT_RULE} {VOICE_NO_REPEAT_RULE} Keep responses concise."
)
