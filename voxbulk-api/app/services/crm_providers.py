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
    "zoho_recruit": "Zoho Recruit",
    "breezy_hr": "Breezy HR",
}

# Optional CRM pairing for booking providers (list links/services via API).
# Booking can also connect with a pasted URL alone — CRM is not required.
CRM_DEPENDENT_BOOKING: dict[str, str] = {
    "hubspot_meetings": "hubspot",
    "zoho_bookings": "zoho_crm",
}

CRM_CONFIG_COLUMNS: dict[str, str] = {
    "hubspot": "hubspot_config_json",
    "pipedrive": "pipedrive_config_json",
    "zoho_crm": "zoho_crm_config_json",
    # ATS tokens. Not in CRM_PROVIDERS so they do not displace the active sales CRM.
    "zoho_recruit": "zoho_recruit_config_json",
    "breezy_hr": "breezy_hr_config_json",
}


def crm_provider_label(provider: str | None) -> str | None:
    key = str(provider or "").strip().lower()
    if not key:
        return None
    return CRM_PROVIDER_LABELS.get(key, key.replace("_", " ").title())
