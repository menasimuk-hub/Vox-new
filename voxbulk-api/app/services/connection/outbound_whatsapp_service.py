from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.connection_profile import PROVIDER_META, PROVIDER_TELNYX, ConnectionProfile
from app.services.connection.profile_credentials import meta_config_from_profile, telnyx_config_from_profile
from app.services.connection.providers.whatsapp_meta import WhatsappMetaProvider
from app.services.connection.providers.whatsapp_telnyx import WhatsappTelnyxProvider
from app.services.connection.resolver import ConnectionProfileResolver
from app.services.telnyx_messaging_service import TelnyxMessageResult, TelnyxMessagingService


class OutboundWhatsappService:
    @staticmethod
    def send(
        db: Session,
        *,
        to_number: str,
        body: str,
        from_number: str | None = None,
        template_name: str | None = None,
        template_id: str | None = None,
        template_language: str | None = None,
        template_components: list[dict[str, Any]] | None = None,
        org_id: str | None = None,
        meter_usage: bool = True,
        messaging_profile_id: str | None = None,
        service_code: str | None = None,
    ) -> tuple[TelnyxMessageResult, ConnectionProfile | None]:
        profile = ConnectionProfileResolver.resolve_whatsapp(
            db,
            org_id=org_id,
            service_code=service_code,
        )
        if profile is None:
            result = OutboundWhatsappService._legacy_send(
                db,
                to_number=to_number,
                body=body,
                from_number=from_number,
                template_name=template_name,
                template_id=template_id,
                template_language=template_language,
                template_components=template_components,
                org_id=org_id,
                meter_usage=meter_usage,
                messaging_profile_id=messaging_profile_id,
            )
            return result, None

        if profile.provider == PROVIDER_META:
            config = meta_config_from_profile(profile)
            result = WhatsappMetaProvider.send(
                db,
                config=config,
                to_number=to_number,
                body=body,
                from_number=from_number or config.get("whatsapp_from"),
                template_name=template_name,
                template_id=template_id,
                template_language=template_language,
                template_components=template_components,
                org_id=org_id,
                meter_usage=meter_usage,
            )
            return result, profile

        if profile.provider == PROVIDER_TELNYX:
            config = telnyx_config_from_profile(profile)
            wa_profile = str(messaging_profile_id or config.get("whatsapp_messaging_profile_id") or "").strip() or None
            result = WhatsappTelnyxProvider.send(
                db,
                config=config,
                to_number=to_number,
                body=body,
                from_number=from_number or config.get("whatsapp_from"),
                template_name=template_name,
                template_id=template_id,
                template_language=template_language,
                template_components=template_components,
                org_id=org_id,
                meter_usage=meter_usage,
                messaging_profile_id=wa_profile,
            )
            return result, profile

        return (
            TelnyxMessageResult(
                ok=False,
                status="unsupported_provider",
                detail=f"Unsupported WhatsApp provider: {profile.provider}",
                channel="whatsapp",
            ),
            profile,
        )

    @staticmethod
    def _legacy_send(
        db: Session,
        *,
        to_number: str,
        body: str,
        from_number: str | None = None,
        template_name: str | None = None,
        template_id: str | None = None,
        template_language: str | None = None,
        template_components: list[dict[str, Any]] | None = None,
        org_id: str | None = None,
        meter_usage: bool = True,
        messaging_profile_id: str | None = None,
        service_code: str | None = None,
    ) -> TelnyxMessageResult:
        del service_code
        return TelnyxMessagingService._send_whatsapp_telnyx_legacy(
            db,
            to_number=to_number,
            body=body,
            from_number=from_number,
            template_name=template_name,
            template_id=template_id,
            template_language=template_language,
            template_components=template_components,
            org_id=org_id,
            meter_usage=meter_usage,
            messaging_profile_id=messaging_profile_id,
        )
