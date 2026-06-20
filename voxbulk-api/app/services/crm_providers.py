"""CRM provider registry — one active CRM per organisation."""

from __future__ import annotations

CRM_PROVIDERS: tuple[str, ...] = (
    "hubspot",
    "pipedrive",
    "zoho_crm",
)

CRM_PROVIDER_LABELS: dict[str, str] = {
    "hubspot": "HubSpot CRM",
    "pipedrive": "Pipedrive",
    "zoho_crm": "Zoho CRM",
}

# Booking providers that require a matching CRM connection.
CRM_DEPENDENT_BOOKING: dict[str, str] = {
    "hubspot_meetings": "hubspot",
    "zoho_bookings": "zoho_crm",
}

CRM_CONFIG_COLUMNS: dict[str, str] = {
    "hubspot": "hubspot_config_json",
    "pipedrive": "pipedrive_config_json",
    "zoho_crm": "zoho_crm_config_json",
}


def crm_provider_label(provider: str | None) -> str | None:
    key = str(provider or "").strip().lower()
    if not key:
        return None
    return CRM_PROVIDER_LABELS.get(key, key.replace("_", " ").title())
