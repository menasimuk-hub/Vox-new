"""WhatsApp sales message bodies (VOXBULK admin placeholders {{first_name}}, etc.).

Pair each key with an approved Meta template in Telnyx — see docs/telnyx-whatsapp-sales-templates.md.
Quick-reply buttons are defined in Telnyx/Meta, not in this body text.
"""

SALES_OPT_IN_WHATSAPP_BODY = """Hi {{first_name}},

Thanks for speaking with VOXBULK today.

When you're ready, tap **Send offer** below and we'll send your personal signup link.

Tap **Stop** if you don't want further messages.

— VOXBULK Sales"""

SALES_OFFER_FOLLOWUP_WHATSAPP_BODY = """Hi {{first_name}},

Your VOXBULK {{offer_line}} is still waiting for you.

Tap **Open offer** below to finish signup, or reply here if you need help.

Tap **Stop** to opt out.

— VOXBULK Sales"""

SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY = """Hi {{first_name}},

As requested — your VOXBULK {{offer_line}}:
{{offer_summary}}

Tap **Start account** below. Your offer applies automatically when you sign up.

— VOXBULK Sales"""
