from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="development", alias="ENV")
    app_name: str = Field(default="VOXBULK API", alias="APP_NAME")

    # Security / JWT
    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # Encryption
    encryption_key: str = Field(default="change-me", alias="ENCRYPTION_KEY")

    # Database
    database_url: str = Field(
        default="sqlite:///./retover.local.db",
        alias="DATABASE_URL",
    )
    db_echo: bool = Field(default=False, alias="DB_ECHO")
    db_pool_pre_ping: bool = Field(default=True, alias="DB_POOL_PRE_PING")

    # CORS / hosts
    cors_allow_origins_raw: str = Field(default="", alias="CORS_ALLOW_ORIGINS")
    cors_allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")
    # Empty in dev lets FastAPI relax host checks via trusted_hosts resolver (defaults to "*" in development).
    trusted_hosts_raw: str = Field(default="", alias="TRUSTED_HOSTS")

    # Redis / Celery
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(default="redis://127.0.0.1:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://127.0.0.1:6379/1", alias="CELERY_RESULT_BACKEND")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=True, alias="LOG_JSON")

    # Webhook signature secrets (HMAC foundation)
    # Twilio request validation uses your Twilio Auth Token.
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    vapi_webhook_secret: str = Field(default="", alias="VAPI_WEBHOOK_SECRET")
    gocardless_webhook_secret: str = Field(default="", alias="GOCARDLESS_WEBHOOK_SECRET")
    invoice_company_name: str = Field(default="VOXBULK", alias="INVOICE_COMPANY_NAME")
    invoice_company_address: str = Field(
        default="VOXBULK Ltd\nLondon, United Kingdom",
        alias="INVOICE_COMPANY_ADDRESS",
    )
    invoice_company_email: str = Field(default="billing@voxbulk.com", alias="INVOICE_COMPANY_EMAIL")
    invoice_company_vat: str = Field(default="", alias="INVOICE_COMPANY_VAT")


    # Twilio API (provider execution)
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_api_key: str = Field(default="", alias="TWILIO_API_KEY")
    twilio_api_secret: str = Field(default="", alias="TWILIO_API_SECRET")
    twilio_from_number: str = Field(default="", alias="TWILIO_FROM_NUMBER")
    twilio_twiml_url: str = Field(default="", alias="TWILIO_TWIML_URL")
    twilio_whatsapp_from: str = Field(default="", alias="TWILIO_WHATSAPP_FROM")

    # Vapi (multi-channel foundation)
    vapi_api_key: str = Field(default="", alias="VAPI_API_KEY")

    # Telnyx (optional fallback when admin DB key is empty)
    telnyx_api_key: str = Field(default="", alias="TELNYX_API_KEY")
    survey_telnyx_assistant_id: str = Field(default="", alias="SURVEY_TELNYX_ASSISTANT_ID")

    calendly_client_id: str = Field(default="", alias="CALENDLY_CLIENT_ID")
    calendly_client_secret: str = Field(default="", alias="CALENDLY_CLIENT_SECRET")
    calendly_redirect_uri: str = Field(default="", alias="CALENDLY_REDIRECT_URI")

    cronofy_client_id: str = Field(default="", alias="CRONOFY_CLIENT_ID")
    cronofy_client_secret: str = Field(default="", alias="CRONOFY_CLIENT_SECRET")
    cronofy_redirect_uri: str = Field(default="", alias="CRONOFY_REDIRECT_URI")

    # Bootstrap
    bootstrap_token: str = Field(default="", alias="BOOTSTRAP_TOKEN")
    enable_test_cash_billing: bool = Field(default=False, alias="ENABLE_TEST_CASH_BILLING")

    # Invite links returned by admin API (public sign-in origin)
    public_app_origin: str = Field(default="http://localhost:5173", alias="PUBLIC_APP_ORIGIN")
    dashboard_app_origin: str = Field(default="http://localhost:5175", alias="DASHBOARD_APP_ORIGIN")

    # Password reset email links expire after this window (minutes)
    password_reset_token_expire_minutes: int = Field(default=60, alias="PASSWORD_RESET_TOKEN_EXPIRE_MINUTES")

    # Dentally (sync foundations)
    dentally_base_url: str = Field(default="https://api.dentally.co", alias="DENTALLY_BASE_URL")
    dentally_api_key: str = Field(default="", alias="DENTALLY_API_KEY")

    @property
    def cors_allow_origins(self) -> List[str]:
        origins = _split_csv(self.cors_allow_origins_raw)
        if origins:
            return origins
        # Make local dev frictionless: if not explicitly set, allow the known local dev frontends.
        if str(self.env).lower() in {"dev", "development", "local"}:
            return [
                "http://localhost:5173",  # public frontend
                "http://localhost:5174",  # admin
                "http://localhost:5175",  # dashboard
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
                "http://127.0.0.1:5175",
            ]
        # Production fallback when CORS_ALLOW_ORIGINS unset (dashboard/public call api.* cross-origin).
        if str(self.env).lower() in {"production", "prod", "staging"}:
            return [
                "https://voxbulk.com",
                "https://www.voxbulk.com",
                "https://admin.voxbulk.com",
                "https://dashboard.voxbulk.com",
            ]
        return []

    @property
    def trusted_hosts(self) -> List[str]:
        hosts = _split_csv(self.trusted_hosts_raw)
        env_l = str(self.env).lower()
        if hosts:
            resolved = list(hosts)
        elif env_l in {"dev", "development", "local"}:
            # LAN access (e.g. http://192.168.x.x:5174) otherwise hits TrustedHostMiddleware before CORS.
            resolved = ["*"]
        else:
            resolved = ["localhost", "127.0.0.1", "api.voxbulk.com"]
        # Starlette TestClient uses "testserver" as Host by default.
        if "*" not in resolved and "testserver" not in resolved:
            resolved.append("testserver")
        return resolved

    @property
    def cors_allow_origin_regex(self) -> str | None:
        """When unset CORS_ALLOW_ORIGINS in local dev, allow any http(s) dev origin (LAN IP, alternate hostnames)."""
        if str(self.env).lower() not in {"dev", "development", "local"}:
            return None
        if _split_csv(self.cors_allow_origins_raw):
            return None
        return r"^https?://[a-zA-Z0-9_.\[\]:-]+(:\d+)?$"

    @property
    def test_cash_billing_allowed(self) -> bool:
        return bool(self.enable_test_cash_billing) or str(self.env).lower() in {"dev", "development", "local"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
