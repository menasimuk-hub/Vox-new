"""Physical pricing column names — single source of truth for SQL + ORM."""

from __future__ import annotations

# Migration contract (0074 / 0106): physical DB column name.
WHATSAPP_SURVEY_FEE_PENCE_COLUMN = "whatsapp_survey_fee_pence"

# Wrong name seen on DBs created via create_all before explicit column mapping.
WA_SURVEY_PACKAGE_FEE_LEGACY_COLUMN = "wa_survey_package_fee_pence"
