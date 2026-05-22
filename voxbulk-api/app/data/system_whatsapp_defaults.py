from __future__ import annotations



from app.data.sales_offer_email_default import SALES_OFFER_WHATSAPP_BODY

from app.data.sales_automation_defaults import (

    SALES_OFFER_FOLLOWUP_WHATSAPP_BODY,

    SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY,

    SALES_OPT_IN_WHATSAPP_BODY,

)



WHATSAPP_SYSTEM_TEMPLATE_KEYS: tuple[str, ...] = (

    "sales_offer",

    "sales_opt_in",

    "sales_offer_followup",

    "sales_offer_keyword_confirm",

)



SYSTEM_WHATSAPP_DEFAULTS: dict[str, dict[str, str]] = {

    "sales_offer": {

        "name": "Sales offer link",

        "body": SALES_OFFER_WHATSAPP_BODY,

    },

    "sales_opt_in": {

        "name": "Sales opt-in (reply SEND OFFER)",

        "body": SALES_OPT_IN_WHATSAPP_BODY,

    },

    "sales_offer_followup": {

        "name": "Sales offer 7-day follow-up",

        "body": SALES_OFFER_FOLLOWUP_WHATSAPP_BODY,

    },

    "sales_offer_keyword_confirm": {

        "name": "Sales offer keyword confirmation",

        "body": SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY,

    },

}

