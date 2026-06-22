from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
    is_suspended: bool = False
    profile_notes: str | None = None
    category_id: str | None = None
    onboarding_state: str = "account_created"
    onboarding_completed_at: datetime | None = None
    onboarding_version: str | None = None
    booking_software_slug: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    county_state: str | None = None
    postcode: str | None = None
    country: str | None = None
    country_code: str | None = None
    billing_currency: str | None = None
    currency_symbol: str | None = None
    billing_currency_locked: bool = False
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    website: str | None = None
    enabled_services: dict[str, bool] | None = None
    allowed_services: dict[str, bool] | None = None
    logo_url: str | None = None


class EnabledServicesUpdate(BaseModel):
    interview: bool | None = None
    survey: bool | None = None
    customer_feedback: bool | None = None
    recovery: bool | None = None
    follow_up: bool | None = None
    campaigns: bool | None = None
    appointments: bool | None = None


class OrganisationUpdate(BaseModel):
    name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    county_state: str | None = None
    postcode: str | None = None
    country: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    website: str | None = None


class OrganisationCreate(BaseModel):
    name: str

