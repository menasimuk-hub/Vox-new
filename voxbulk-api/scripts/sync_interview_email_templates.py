"""Push latest interview email templates from code defaults into the database (VPS one-off)."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS
from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService

INTERVIEW_KEYS = [k for k in EMAIL_TEMPLATE_KEYS if k.startswith("interview_")]


def main() -> None:
    with get_sessionmaker()() as db:
        for key in INTERVIEW_KEYS:
            defaults = SYSTEM_EMAIL_DEFAULTS.get(key, {})
            row = EmailTemplateService.upsert(
                db,
                key=key,
                title=str(defaults.get("title") or key),
                subject=str(defaults.get("subject") or key),
                body=str(defaults.get("body") or ""),
                is_enabled=True,
            )
            print(f"upserted {row.template_key} (enabled={row.is_enabled})")
    print("Done — interview email templates synced from code defaults.")


if __name__ == "__main__":
    main()
