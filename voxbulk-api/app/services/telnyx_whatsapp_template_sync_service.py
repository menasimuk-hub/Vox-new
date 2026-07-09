"""Fetch Telnyx/Meta WhatsApp templates and store them for sends by template_id."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.sales_whatsapp_telnyx_service import (
    TELNYX_SALES_TEMPLATE_NAMES,
    TEST_TEMPLATE_VARIABLES,
    build_telnyx_components,
    build_test_components_for_template_name,
    canonical_telnyx_name_for_sales_key,
    legacy_telnyx_names_for_sales_key,
    template_key_for_telnyx_name,
    url_button_has_dynamic_suffix,
    url_button_index_from_components,
)
from app.services.telnyx_api_key import normalize_telnyx_api_key, require_telnyx_api_key
from app.services.telnyx_messaging_service import _TEMPLATE_UUID_RE
from app.services.telnyx_voice_service import (
    _telnyx_config,
    _telnyx_headers,
    _telnyx_http_error_detail,
    resolve_telnyx_whatsapp_waba_id,
    resolve_telnyx_whatsapp_waba_filter_id,
    TelnyxConfigError,
)

logger = logging.getLogger(__name__)

TELNYX_WHATSAPP_TEMPLATES_URL = "https://api.telnyx.com/v2/whatsapp/message_templates"
_VAR_RE = re.compile(r"\{\{(\d+)\}\}")
# Meta/Telnyx statuses — do not keep locally (removed from portal or rejected).
_SKIP_REMOTE_STATUSES = frozenset({"DELETED", "DISABLED", "PENDING_DELETION"})
_LOCAL_ID_PREFIX = "local-"
_REMOTE_STATUS_RANK = {"APPROVED": 0, "PENDING": 1, "REJECTED": 2, "PAUSED": 3}


def _remote_language_code(raw: str | None) -> str:
    text = str(raw or "en_US").strip() or "en_US"
    normalized = text.replace("-", "_")
    if "_" in normalized:
        parts = normalized.split("_", 1)
        return f"{parts[0].lower()}_{parts[1].upper()}"
    return normalized.lower()


def _remote_item_matches_names(item: dict[str, Any], names: set[str]) -> bool:
    remote_name = str(item.get("name") or "").strip().lower()
    if not remote_name:
        return False
    if remote_name in names:
        return True
    sales_key = template_key_for_telnyx_name(remote_name)
    if not sales_key:
        return False
    canonical = canonical_telnyx_name_for_sales_key(sales_key)
    if canonical and canonical.lower() in names:
        return True
    for legacy in legacy_telnyx_names_for_sales_key(sales_key):
        if legacy.lower() in names:
            return True
    return False


def _remote_item_matches_sales_key(item: dict[str, Any], sales_key: str | None) -> bool:
    key = str(sales_key or "").strip().lower()
    if not key:
        return False
    remote_name = str(item.get("name") or "").strip().lower()
    if template_key_for_telnyx_name(remote_name) == key:
        return True
    canonical = canonical_telnyx_name_for_sales_key(key)
    if canonical and canonical.lower() == remote_name:
        return True
    return remote_name in {n.lower() for n in legacy_telnyx_names_for_sales_key(key)}


def _components_content_hash(components: list[Any] | None) -> str | None:
    if not isinstance(components, list):
        return None
    raw = json.dumps(components, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _pick_best_remote_item(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None

    def _rank(item: dict[str, Any]) -> tuple[int, str]:
        status = str(item.get("status") or "").upper()
        return (_REMOTE_STATUS_RANK.get(status, 99), str(item.get("name") or ""))

    return sorted(items, key=_rank)[0]


class TelnyxWhatsappTemplateSyncError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def _sales_key_for_name(name: str | None) -> str | None:
    return template_key_for_telnyx_name(name)


def _component_text(comp: dict[str, Any]) -> str:
    return str(comp.get("text") or "").strip()


def _body_preview(components: list[Any] | None) -> str | None:
    if not isinstance(components, list):
        return None
    for comp in components:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() == "BODY":
            text = _component_text(comp)
            return text[:2000] if text else None
    return None


def full_body_preview(components: list[Any] | None) -> str | None:
    """Header + body + footer — used for dashboard previews so emojis in headers are visible."""
    if not isinstance(components, list):
        return None
    parts: list[str] = []
    for section in ("HEADER", "BODY", "FOOTER"):
        for comp in components:
            if not isinstance(comp, dict):
                continue
            if str(comp.get("type") or "").upper() != section:
                continue
            text = _component_text(comp)
            if text:
                parts.append(text)
            break
    if not parts:
        return _body_preview(components)
    joined = "\n\n".join(parts)
    return joined[:4000] if joined else None


def _body_variable_count(components: list[Any] | None) -> int:
    preview = _body_preview(components)
    if not preview:
        return 0
    nums = {int(m.group(1)) for m in _VAR_RE.finditer(preview)}
    return max(nums) if nums else 0


def _send_template_id_from_api_item(item: dict[str, Any]) -> str:
    """Telnyx send API uses list `id` (UUID). `template_id` is often Meta's numeric id."""
    telnyx_id = str(item.get("id") or "").strip()
    meta_id = str(item.get("template_id") or "").strip()
    if telnyx_id and (_TEMPLATE_UUID_RE.match(telnyx_id) or not meta_id.isdigit()):
        return telnyx_id
    if meta_id and _TEMPLATE_UUID_RE.match(meta_id):
        return meta_id
    return telnyx_id or meta_id


def send_template_id_for_row(row: TelnyxWhatsappTemplate) -> str:
    """Id to pass to Telnyx messages API — always prefer Telnyx list UUID (telnyx_record_id)."""
    record = str(row.telnyx_record_id or "").strip()
    if record:
        return record
    return str(row.template_id or "").strip()


def _is_local_draft_row(row: TelnyxWhatsappTemplate) -> bool:
    rid = str(row.telnyx_record_id or "").strip()
    if rid.startswith(_LOCAL_ID_PREFIX):
        return True
    return str(row.status or "").upper() == "LOCAL_DRAFT"


def _detach_template_references(db: Session, template_id: int) -> None:
    from app.models.survey_flow import SurveyFlowNode, SurveyFlowOutcome
    from app.models.survey_type_template import SurveyTypeTemplate

    for mapping in db.execute(
        select(SurveyTypeTemplate).where(SurveyTypeTemplate.template_id == template_id)
    ).scalars().all():
        db.delete(mapping)

    for node in db.execute(
        select(SurveyFlowNode).where(SurveyFlowNode.template_id == template_id)
    ).scalars().all():
        node.template_id = None

    for outcome in db.execute(
        select(SurveyFlowOutcome).where(SurveyFlowOutcome.template_id == template_id)
    ).scalars().all():
        outcome.template_id = None

    for child in db.execute(
        select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.parent_template_id == template_id)
    ).scalars().all():
        child.parent_template_id = None


def _delete_stale_template_row(db: Session, row: TelnyxWhatsappTemplate) -> bool:
    if _is_local_draft_row(row):
        return False
    _detach_template_references(db, int(row.id))
    db.delete(row)
    return True


def _apply_managed_product_status_only(
    existing: TelnyxWhatsappTemplate,
    item: dict[str, Any],
    *,
    now: datetime,
) -> None:
    """Refresh Meta approval fields only — never overwrite local name/body (DB is master)."""
    from app.services.survey_whatsapp_template_service import _refresh_local_sync_status

    send_template_id = _send_template_id_from_api_item(item)
    record_id = str(item.get("id") or "").strip()
    status = str(item.get("status") or "UNKNOWN").strip().upper()
    category = str(item.get("category") or "").strip() or None
    waba = item.get("whatsapp_business_account")
    waba_id = str(waba.get("id") or "").strip() if isinstance(waba, dict) else None

    existing.template_id = send_template_id
    existing.telnyx_record_id = record_id
    if category:
        existing.category = category
    existing.status = status
    if status == "APPROVED":
        existing.last_push_error = None
    existing.rejection_reason = str(item.get("rejection_reason") or "").strip() or None
    existing.waba_id = waba_id
    existing.synced_at = now
    existing.updated_at = now
    existing.local_sync_status = _refresh_local_sync_status(existing)


def template_to_dict(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
    send_id = send_template_id_for_row(row)
    return {
        "id": row.id,
        "telnyx_record_id": row.telnyx_record_id,
        "template_id": send_id,
        "meta_template_id": (
            row.template_id
            if row.template_id != send_id and str(row.template_id or "").isdigit()
            else None
        ),
        "name": row.name,
        "language": row.language,
        "category": row.category,
        "status": row.status,
        "sales_template_key": row.sales_template_key,
        "body_preview": row.body_preview,
        "waba_id": row.waba_id,
        "rejection_reason": row.rejection_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "synced_at": row.synced_at.isoformat() if row.synced_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _normalize_meta_template_item(item: dict[str, Any], *, waba_id: str | None = None) -> dict[str, Any]:
    """Normalize Meta Graph message_templates row to Telnyx sync shape."""
    meta_id = str(item.get("id") or "").strip()
    record_id = f"meta-{meta_id}" if meta_id else ""
    return {
        "id": record_id,
        "template_id": meta_id,
        "name": str(item.get("name") or "").strip(),
        "language": _remote_language_code(str(item.get("language") or "en_US")),
        "status": str(item.get("status") or "UNKNOWN").strip().upper(),
        "category": str(item.get("category") or "").strip() or None,
        "components": item.get("components"),
        "whatsapp_business_account": {"id": waba_id} if waba_id else None,
    }


class TelnyxWhatsappTemplateSyncService:
    @staticmethod
    def _config(
        db: Session,
        *,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        if connection_profile_id:
            from app.services.connection.config_resolver import (
                WhatsappSyncRouteError,
                resolve_whatsapp_route_by_profile_id,
            )

            route = resolve_whatsapp_route_by_profile_id(
                db, connection_profile_id, service_code=service_code or "survey"
            )
            if not route.is_telnyx:
                raise TelnyxWhatsappTemplateSyncError(
                    f"Profile uses {route.provider}, not Telnyx — cannot fetch Telnyx templates"
                )
            return route.config
        try:
            return _telnyx_config(db)
        except TelnyxConfigError as e:
            raise TelnyxWhatsappTemplateSyncError(str(e)) from e

    @staticmethod
    def fetch_from_telnyx(
        db: Session,
        *,
        filter_waba_id: bool = True,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
        allow_account_waba_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        config = TelnyxWhatsappTemplateSyncService._config(
            db,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
        )
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key:
            api_key, _ = require_telnyx_api_key(db)

        # Prefer an explicit WABA on the profile/config. For live profile monitors we must NOT
        # fall back to "first WABA on this Telnyx account" — that steals Meta/other numbers.
        configured_waba = (
            str(config.get("whatsapp_waba_id") or "").strip()
            or str(config.get("waba_id") or "").strip()
        )
        if filter_waba_id and not configured_waba and not allow_account_waba_fallback:
            # Empty / unlinked Telnyx profile → report 0 live templates.
            return []
        if filter_waba_id:
            waba_id = (
                resolve_telnyx_whatsapp_waba_filter_id(db, config)
                if configured_waba
                else resolve_telnyx_whatsapp_waba_id(db, config)
            )
        else:
            waba_id = ""
        params: dict[str, Any] = {"page[size]": 250, "page[number]": 1}
        if waba_id:
            params["filter[waba_id]"] = waba_id
        elif filter_waba_id and connection_profile_id:
            # Profile selected but no WABA — do not dump the whole account catalog.
            return []

        rows: list[dict[str, Any]] = []
        try:
            with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
                while True:
                    response = client.get(
                        TELNYX_WHATSAPP_TEMPLATES_URL,
                        params=params,
                        headers=_telnyx_headers(api_key),
                    )
                    response.raise_for_status()
                    body = response.json()
                    chunk = body.get("data") if isinstance(body, dict) else []
                    if isinstance(chunk, list):
                        rows.extend(item for item in chunk if isinstance(item, dict))

                    meta = body.get("meta") if isinstance(body, dict) else {}
                    if not isinstance(meta, dict):
                        break
                    page_number = int(meta.get("page_number") or params["page[number]"])
                    total_pages = int(meta.get("total_pages") or 1)
                    if page_number >= total_pages:
                        break
                    params["page[number]"] = page_number + 1
        except httpx.HTTPStatusError as e:
            raise TelnyxWhatsappTemplateSyncError(_telnyx_http_error_detail(e)) from e
        except Exception as e:
            raise TelnyxWhatsappTemplateSyncError(str(e)) from e

        return rows

    @staticmethod
    def fetch_from_meta(
        db: Session,
        *,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> list[dict[str, Any]]:
        from app.services.meta_whatsapp_config_service import MetaWhatsappConfigError
        from app.services.meta_whatsapp_service import MetaWhatsappService

        try:
            config, enabled = MetaWhatsappService._config(
                db,
                service_code=service_code,
                connection_profile_id=connection_profile_id,
            )
        except Exception as exc:
            raise TelnyxWhatsappTemplateSyncError(str(exc)) from exc
        if not enabled:
            raise TelnyxWhatsappTemplateSyncError("Meta WhatsApp integration is disabled")
        waba_id = str(config.get("waba_id") or "").strip()
        try:
            remote = MetaWhatsappService.fetch_all_templates(
                db,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )
        except MetaWhatsappConfigError as exc:
            raise TelnyxWhatsappTemplateSyncError(str(exc)) from exc
        except Exception as exc:
            raise TelnyxWhatsappTemplateSyncError(str(exc)) from exc
        return [_normalize_meta_template_item(item, waba_id=waba_id or None) for item in remote if isinstance(item, dict)]

    @staticmethod
    def fetch_remote_templates(
        db: Session,
        *,
        filter_waba_id: bool = True,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
        allow_account_waba_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

        if is_meta_whatsapp_primary(
            db,
            service_code=service_code,
            connection_profile_id=connection_profile_id,
        ):
            return TelnyxWhatsappTemplateSyncService.fetch_from_meta(
                db,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )
        return TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(
            db,
            filter_waba_id=filter_waba_id,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
            allow_account_waba_fallback=allow_account_waba_fallback,
        )

    @staticmethod
    def fetch_template_by_record_id(
        db: Session,
        record_id: str,
        *,
        connection_profile_id: str | None = None,
        service_code: str = "survey",
    ) -> dict[str, Any]:
        """Fetch a single WhatsApp template from Meta or Telnyx by record id."""
        from app.services.meta_whatsapp_service import _META_RECORD_PREFIX
        from app.services.telnyx_messaging_service import _TEMPLATE_UUID_RE

        rid = str(record_id or "").strip()
        if not rid:
            raise TelnyxWhatsappTemplateSyncError("Template record id is required")

        use_meta_api = rid.startswith(_META_RECORD_PREFIX) or rid.startswith("meta-")
        if not use_meta_api and _TEMPLATE_UUID_RE.match(rid):
            use_meta_api = False
        elif not use_meta_api:
            from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

            use_meta_api = is_meta_whatsapp_primary(
                db,
                service_code=service_code,
                connection_profile_id=connection_profile_id,
            )

        if use_meta_api:
            from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateError, MetaWhatsappTemplateService

            try:
                return MetaWhatsappTemplateService.fetch_by_record_id(db, rid)
            except MetaWhatsappTemplateError as exc:
                raise TelnyxWhatsappTemplateSyncError(str(exc)) from exc

        if connection_profile_id:
            from app.services.connection.config_resolver import resolve_whatsapp_route_by_profile_id

            route = resolve_whatsapp_route_by_profile_id(
                db,
                connection_profile_id,
                service_code=service_code,
            )
            config = route.config
        else:
            config = TelnyxWhatsappTemplateSyncService._config(db)
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key:
            api_key, _ = require_telnyx_api_key(db)

        url = f"{TELNYX_WHATSAPP_TEMPLATES_URL}/{rid}"
        try:
            with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
                response = client.get(url, headers=_telnyx_headers(api_key))
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as e:
            raise TelnyxWhatsappTemplateSyncError(_telnyx_http_error_detail(e)) from e
        except Exception as e:
            raise TelnyxWhatsappTemplateSyncError(str(e)) from e

        item = body.get("data") if isinstance(body, dict) else None
        if not isinstance(item, dict):
            raise TelnyxWhatsappTemplateSyncError("Telnyx returned an unexpected template response")
        return item

    @staticmethod
    def find_remote_template(
        db: Session,
        *,
        names: list[str],
        language: str | None = None,
        sales_template_key: str | None = None,
        remote_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Find an existing Telnyx/Meta template by name (+ optional language)."""
        items = remote_items if remote_items is not None else TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        name_set = {str(n or "").strip().lower() for n in names if str(n or "").strip()}
        if sales_template_key:
            canonical = canonical_telnyx_name_for_sales_key(sales_template_key)
            if canonical:
                name_set.add(canonical.lower())
            for legacy in legacy_telnyx_names_for_sales_key(sales_template_key):
                name_set.add(legacy.lower())

        matches: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").upper()
            if status in _SKIP_REMOTE_STATUSES:
                continue
            if sales_template_key and _remote_item_matches_sales_key(item, sales_template_key):
                matches.append(item)
                continue
            if name_set and _remote_item_matches_names(item, name_set):
                matches.append(item)

        if not matches:
            return None

        lang = _remote_language_code(language) if language else None
        if lang:
            exact = [
                item
                for item in matches
                if _remote_language_code(str(item.get("language") or "")) == lang
            ]
            if exact:
                return _pick_best_remote_item(exact)

        return _pick_best_remote_item(matches)

    @staticmethod
    def _find_local_row_to_merge(
        db: Session,
        *,
        local_name: str,
        language: str,
        sales_key: str | None,
        record_id: str,
    ) -> TelnyxWhatsappTemplate | None:
        by_record = db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == record_id)
        ).scalar_one_or_none()
        if by_record is not None:
            return by_record

        if sales_key:
            by_key = db.execute(
                select(TelnyxWhatsappTemplate)
                .where(
                    TelnyxWhatsappTemplate.sales_template_key == sales_key,
                    TelnyxWhatsappTemplate.telnyx_record_id.like(f"{_LOCAL_ID_PREFIX}%"),
                )
                .order_by(TelnyxWhatsappTemplate.updated_at.desc())
            ).scalars().first()
            if by_key is not None:
                return by_key

        candidates = {local_name.strip().lower()}
        if sales_key:
            canonical = canonical_telnyx_name_for_sales_key(sales_key)
            if canonical:
                candidates.add(canonical.lower())
            for legacy in legacy_telnyx_names_for_sales_key(sales_key):
                candidates.add(legacy.lower())

        for name_lower in candidates:
            if not name_lower:
                continue
            row = db.execute(
                select(TelnyxWhatsappTemplate)
                .where(
                    func.lower(TelnyxWhatsappTemplate.name) == name_lower,
                    TelnyxWhatsappTemplate.telnyx_record_id.like(f"{_LOCAL_ID_PREFIX}%"),
                )
                .order_by(TelnyxWhatsappTemplate.updated_at.desc())
            ).scalars().first()
            if row is not None:
                return row
        return None

    @staticmethod
    def delete_remote_template(db: Session, record_id: str, *, template_name: str | None = None) -> None:
        """Delete a WhatsApp template from Meta or Telnyx. Not-found is treated as success."""
        rid = str(record_id or "").strip()
        if not rid or rid.startswith("local-"):
            return

        from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

        if is_meta_whatsapp_primary(db, service_code="survey"):
            from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateError, MetaWhatsappTemplateService

            try:
                MetaWhatsappTemplateService.delete_message_template(
                    db,
                    name=str(template_name or "").strip() or None,
                    hsm_id=rid,
                )
            except MetaWhatsappTemplateError as exc:
                if "404" in str(exc).lower() or "not found" in str(exc).lower():
                    return
                raise TelnyxWhatsappTemplateSyncError(str(exc)) from exc
            return

        config = TelnyxWhatsappTemplateSyncService._config(db)
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key:
            api_key, _ = require_telnyx_api_key(db)

        url = f"{TELNYX_WHATSAPP_TEMPLATES_URL}/{rid}"
        try:
            with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
                response = client.delete(url, headers=_telnyx_headers(api_key))
                if response.status_code == 404:
                    return
                if response.status_code not in (200, 204):
                    response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise TelnyxWhatsappTemplateSyncError(_telnyx_http_error_detail(e)) from e
        except Exception as e:
            raise TelnyxWhatsappTemplateSyncError(str(e)) from e

    @staticmethod
    def sync(db: Session, *, remote: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        items = remote if remote is not None else TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        now = _now()
        synced = 0
        approved = 0
        remote_record_ids: set[str] = set()
        from app.services.survey_whatsapp_template_service import _refresh_local_sync_status, _sync_content_hash
        from app.services.wa_template_product_scope import is_managed_product_remote_name, is_managed_product_row

        for item in items:
            record_id = str(item.get("id") or "").strip()
            meta_template_id = str(item.get("template_id") or "").strip()
            send_template_id = _send_template_id_from_api_item(item)
            name = str(item.get("name") or "").strip()
            if not record_id or not send_template_id or not name:
                continue

            language = str(item.get("language") or "en_US").strip() or "en_US"
            status = str(item.get("status") or "UNKNOWN").strip().upper()
            if status in _SKIP_REMOTE_STATUSES:
                existing = db.execute(
                    select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == record_id)
                ).scalar_one_or_none()
                if existing is not None:
                    if is_managed_product_row(db, existing) or is_managed_product_remote_name(name):
                        existing.status = status
                        existing.updated_at = now
                        db.flush()
                    else:
                        db.delete(existing)
                continue

            sales_key = _sales_key_for_name(name)
            canonical_name = canonical_telnyx_name_for_sales_key(sales_key)
            local_name = canonical_name or name

            if is_managed_product_remote_name(name):
                existing = db.execute(
                    select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == record_id)
                ).scalar_one_or_none()
                if existing is None:
                    merged = TelnyxWhatsappTemplateSyncService._find_local_row_to_merge(
                        db,
                        local_name=local_name,
                        language=language,
                        sales_key=sales_key,
                        record_id=record_id,
                    )
                    existing = merged
                if existing is None:
                    continue
                remote_record_ids.add(record_id)
                try:
                    with db.begin_nested():
                        _apply_managed_product_status_only(existing, item, now=now)
                        db.flush()
                except Exception:
                    continue
                synced += 1
                if status == "APPROVED":
                    approved += 1
                continue

            remote_record_ids.add(record_id)
            category = str(item.get("category") or "").strip() or None
            components = item.get("components")
            components_json = json.dumps(components, ensure_ascii=False) if components is not None else None
            waba = item.get("whatsapp_business_account")
            waba_id = str(waba.get("id") or "").strip() if isinstance(waba, dict) else None

            existing = db.execute(
                select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == record_id)
            ).scalar_one_or_none()
            if existing is None:
                merged = TelnyxWhatsappTemplateSyncService._find_local_row_to_merge(
                    db,
                    local_name=local_name,
                    language=language,
                    sales_key=sales_key,
                    record_id=record_id,
                )
                if merged is not None:
                    existing = merged
                else:
                    existing = TelnyxWhatsappTemplate(
                        telnyx_record_id=record_id,
                        template_id=send_template_id,
                        name=local_name,
                        language=language,
                        created_at=now,
                    )
                    db.add(existing)

            # If a merge candidate would steal a record_id another row already owns, keep the owner.
            owner_conflict = db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.telnyx_record_id == record_id,
                    TelnyxWhatsappTemplate.id != existing.id,
                )
            ).scalar_one_or_none()
            if owner_conflict is not None:
                if str(existing.telnyx_record_id or "").startswith(_LOCAL_ID_PREFIX):
                    if not owner_conflict.survey_type_id and existing.survey_type_id:
                        owner_conflict.survey_type_id = existing.survey_type_id
                    _detach_template_references(db, int(existing.id))
                    db.delete(existing)
                existing = owner_conflict

            duplicate_rows = list(
                db.execute(
                    select(TelnyxWhatsappTemplate).where(
                        TelnyxWhatsappTemplate.telnyx_record_id == record_id,
                        TelnyxWhatsappTemplate.id != existing.id,
                    )
                ).scalars().all()
            )
            for duplicate in duplicate_rows:
                _detach_template_references(db, int(duplicate.id))
                db.delete(duplicate)

            if is_managed_product_row(db, existing):
                try:
                    with db.begin_nested():
                        _apply_managed_product_status_only(existing, item, now=now)
                        db.flush()
                except Exception:
                    continue
                synced += 1
                if status == "APPROVED":
                    approved += 1
                continue

            try:
                with db.begin_nested():
                    existing.template_id = send_template_id
                    existing.telnyx_record_id = record_id
                    existing.name = local_name
                    existing.language = language
                    if category:
                        existing.category = category
                    existing.status = status
                    existing.sales_template_key = sales_key or existing.sales_template_key
                    # Never wipe body/components when Meta omits them — that makes the UI show
                    # template names instead of question body text.
                    if isinstance(components, list) and components:
                        preview = _body_preview(components)
                        if preview:
                            existing.body_preview = preview
                        existing.components_json = components_json
                        existing.remote_content_hash = _sync_content_hash(components)
                    elif not existing.body_preview:
                        # Last resort: keep name out of body_preview (leave null for repair pass).
                        existing.body_preview = existing.body_preview
                    elif existing.components_json and not existing.remote_content_hash:
                        from app.services.survey_whatsapp_template_service import _loads

                        stored = _loads(existing.components_json)
                        existing.remote_content_hash = _sync_content_hash(
                            stored if isinstance(stored, list) else None
                        )
                    existing.local_sync_status = _refresh_local_sync_status(existing)
                    existing.last_push_error = None
                    existing.waba_id = waba_id
                    existing.rejection_reason = str(item.get("rejection_reason") or "").strip() or None
                    existing.synced_at = now
                    existing.updated_at = now
                    db.flush()
            except Exception:
                continue
            synced += 1
            if status == "APPROVED":
                approved += 1

        removed = 0
        if remote_record_ids:
            stale_rows = list(
                db.execute(
                    select(TelnyxWhatsappTemplate).where(
                        TelnyxWhatsappTemplate.telnyx_record_id.notin_(remote_record_ids)
                    )
                ).scalars().all()
            )
            for row in stale_rows:
                if is_managed_product_row(db, row):
                    continue
                if _delete_stale_template_row(db, row):
                    removed += 1

        db.commit()
        stored = list(db.execute(select(TelnyxWhatsappTemplate).order_by(TelnyxWhatsappTemplate.name.asc())).scalars().all())
        return {
            "ok": True,
            "synced": synced,
            "approved": approved,
            "removed": removed,
            "remote_count": len(remote_record_ids),
            "templates": [template_to_dict(row) for row in stored],
        }

    @staticmethod
    def list_stored(db: Session, *, approved_only: bool = False) -> list[dict[str, Any]]:
        q = select(TelnyxWhatsappTemplate).order_by(TelnyxWhatsappTemplate.name.asc())
        rows = list(db.execute(q).scalars().all())
        if approved_only:
            rows = [row for row in rows if str(row.status or "").upper() == "APPROVED"]
        return [template_to_dict(row) for row in rows]

    @staticmethod
    def summarize_local_stored(db: Session) -> dict[str, Any]:
        """Fast read-only header counts from local DB — no Meta API round-trip."""
        rows = list(
            db.execute(
                select(
                    TelnyxWhatsappTemplate.status,
                    TelnyxWhatsappTemplate.category,
                    TelnyxWhatsappTemplate.telnyx_record_id,
                )
            ).all()
        )
        approved = pending = rejected = utility = marketing = local_only = 0
        for status_raw, category_raw, rid_raw in rows:
            status = str(status_raw or "").strip().upper()
            rid = str(rid_raw or "").strip()
            is_local = rid.startswith(_LOCAL_ID_PREFIX) or status == "LOCAL_DRAFT"
            if is_local:
                local_only += 1
                continue
            category = str(category_raw or "").strip().upper()
            if "MARKET" in category:
                marketing += 1
            else:
                utility += 1
            if status == "APPROVED":
                approved += 1
            elif status == "REJECTED" or "REJECT" in status:
                rejected += 1
            else:
                pending += 1
        remote_total = approved + pending + rejected
        return {
            "ok": True,
            "live": False,
            "total": remote_total + local_only,
            "approved": approved,
            "local_only": local_only,
            "pending": pending,
            "rejected": rejected,
            "utility": utility,
            "marketing": marketing,
            "remote_total": remote_total,
        }

    @staticmethod
    def _live_index(remote: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        by_record: dict[str, dict[str, Any]] = {}
        by_name_lang: dict[tuple[str, str], dict[str, Any]] = {}
        for item in remote or []:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip().lower()
            lang = _remote_language_code(str(item.get("language") or "en_US"))
            if rid:
                by_record[rid] = item
            if name:
                by_name_lang[(name, lang)] = item
        return by_record, by_name_lang

    @staticmethod
    def _match_live_item(
        row: TelnyxWhatsappTemplate,
        *,
        by_record: dict[str, dict[str, Any]],
        by_name_lang: dict[tuple[str, str], dict[str, Any]],
    ) -> dict[str, Any] | None:
        rid = str(row.telnyx_record_id or "").strip()
        if rid and not rid.startswith(_LOCAL_ID_PREFIX) and rid in by_record:
            return by_record[rid]
        name = str(row.name or "").strip().lower()
        lang = _remote_language_code(str(row.language or "en_US"))
        if name and (name, lang) in by_name_lang:
            return by_name_lang[(name, lang)]
        # Name-only fallback when language codes differ slightly (en vs en_GB).
        if name:
            for (n, _lang), item in by_name_lang.items():
                if n == name:
                    return item
        return None

    @staticmethod
    def summarize_live_remote(remote: list[dict[str, Any]]) -> dict[str, int]:
        """Counts from live Meta/Telnyx only — never from stale local rows."""
        approved = pending = rejected = utility = marketing = 0
        for item in remote or []:
            if not isinstance(item, dict):
                continue
            # Meta lists one row per language; count each language variant.
            status = str(item.get("status") or "").strip().upper()
            if status in _SKIP_REMOTE_STATUSES:
                continue
            category = str(item.get("category") or "").strip().upper()
            if "MARKET" in category:
                marketing += 1
            else:
                utility += 1
            if status == "APPROVED":
                approved += 1
            elif status == "REJECTED" or "REJECT" in status:
                rejected += 1
            elif status in {"PENDING", "PENDING_APPROVAL", "IN_APPEAL", "SUBMITTED", "UNKNOWN", ""}:
                pending += 1
            else:
                pending += 1
        return {
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "utility": utility,
            "marketing": marketing,
            "remote_total": approved + pending + rejected,
        }

    @staticmethod
    def apply_live_statuses(db: Session, *, remote: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Overwrite local status fields from live Meta/Telnyx. Clears stale REJECTED."""
        from datetime import datetime as _dt

        try:
            items = remote if remote is not None else TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        except Exception as exc:  # noqa: BLE001
            raise TelnyxWhatsappTemplateSyncError(str(exc)) from exc

        by_record, by_name_lang = TelnyxWhatsappTemplateSyncService._live_index(items)
        live_summary = TelnyxWhatsappTemplateSyncService.summarize_live_remote(items)
        now = _dt.utcnow()
        updated = 0
        cleared_stale_rejected = 0
        local_only = 0

        rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars().all())
        for row in rows:
            live = TelnyxWhatsappTemplateSyncService._match_live_item(
                row, by_record=by_record, by_name_lang=by_name_lang
            )
            if live is not None:
                status = str(live.get("status") or "UNKNOWN").strip().upper()
                if status in _SKIP_REMOTE_STATUSES:
                    continue
                prev = str(row.status or "").upper()
                row.status = status
                row.rejection_reason = str(live.get("rejection_reason") or "").strip() or None
                from app.services.survey_whatsapp_template_service import normalize_wa_template_category

                remote_category = normalize_wa_template_category(live.get("category"), required=False)
                if remote_category:
                    row.category = remote_category
                if status == "APPROVED":
                    row.last_push_error = None
                from app.services.survey_whatsapp_template_service import _refresh_local_sync_status

                refreshed = _refresh_local_sync_status(row)
                if status == "REJECTED":
                    row.local_sync_status = "needs_resubmit"
                elif status in {"PENDING", "PENDING_APPROVAL", "IN_APPEAL", "SUBMITTED"}:
                    row.local_sync_status = (
                        refreshed if refreshed in {"local_changes", "remote_changed"} else "pending"
                    )
                else:
                    row.local_sync_status = refreshed
                row.synced_at = now
                row.updated_at = now
                db.add(row)
                if prev != status:
                    updated += 1
                continue

            # Not on Meta/Telnyx right now.
            if _is_local_draft_row(row):
                local_only += 1
                if str(row.status or "").upper() == "REJECTED":
                    # Stale rejection — template is local-only, not rejected on Meta.
                    row.status = "LOCAL_DRAFT"
                    row.rejection_reason = None
                    row.local_sync_status = "draft"
                    row.updated_at = now
                    db.add(row)
                    cleared_stale_rejected += 1
                continue

            # Had a remote id but Meta no longer lists it — not a live rejection.
            if str(row.status or "").upper() == "REJECTED":
                row.status = "LOCAL_DRAFT"
                row.rejection_reason = None
                row.telnyx_record_id = f"{_LOCAL_ID_PREFIX}{row.id}"
                row.template_id = row.telnyx_record_id
                row.local_sync_status = "draft"
                row.updated_at = now
                db.add(row)
                cleared_stale_rejected += 1
                local_only += 1
            elif str(row.status or "").upper() not in {"LOCAL_DRAFT", "DRAFT"}:
                # Pending/approved ghost — treat as local until re-pushed.
                row.status = "LOCAL_DRAFT"
                row.local_sync_status = "draft"
                row.updated_at = now
                db.add(row)
                local_only += 1
            else:
                local_only += 1

        db.commit()
        return {
            "ok": True,
            "live": True,
            "updated": updated,
            "cleared_stale_rejected": cleared_stale_rejected,
            "local_only": local_only,
            "approved": live_summary["approved"],
            "pending": live_summary["pending"],
            "rejected": live_summary["rejected"],
            "utility": live_summary["utility"],
            "marketing": live_summary["marketing"],
            "total": live_summary["remote_total"] + local_only,
            "remote_total": live_summary["remote_total"],
        }

    @staticmethod
    def list_with_live_status(db: Session, *, approved_only: bool = False) -> dict[str, Any]:
        """List templates after applying live Meta/Telnyx statuses. Summary is live-only."""
        summary = TelnyxWhatsappTemplateSyncService.apply_live_statuses(db)
        templates = TelnyxWhatsappTemplateSyncService.list_stored(db, approved_only=approved_only)
        return {
            "ok": True,
            "live": True,
            "templates": templates,
            "summary": {
                "total": summary["total"],
                "approved": summary["approved"],
                "localOnly": summary["local_only"],
                "pending": summary["pending"],
                "rejected": summary["rejected"],
                "utility": summary["utility"],
                "marketing": summary["marketing"],
            },
            "cleared_stale_rejected": summary["cleared_stale_rejected"],
            "updated": summary["updated"],
        }

    @staticmethod
    def get_for_sales_key(db: Session, template_key: str) -> TelnyxWhatsappTemplate | None:
        key = str(template_key or "").strip().lower()
        if not key:
            return None
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate)
                .where(TelnyxWhatsappTemplate.sales_template_key == key)
                .order_by(TelnyxWhatsappTemplate.updated_at.desc())
            ).scalars().all()
        )
        interview_keys = {
            "interview_email_sent",
            "interview_booking_confirm",
            "interview_booking_cancel",
            "interview_job_closed",
        }

        def _interview_active(row: TelnyxWhatsappTemplate) -> bool:
            if key not in interview_keys:
                return True
            return bool(getattr(row, "active_for_interview", True))

        for row in rows:
            if not _interview_active(row):
                continue
            if str(row.status or "").upper() == "APPROVED":
                return row
        for row in rows:
            if _interview_active(row):
                return row
        return None

    @staticmethod
    def resolve_for_send(
        db: Session,
        *,
        template_name: str | None = None,
        template_id: str | None = None,
        sales_template_key: str | None = None,
    ) -> TelnyxWhatsappTemplate | None:
        tid = str(template_id or "").strip()
        if tid:
            row = db.execute(
                select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.template_id == tid).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = db.execute(
                    select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == tid).limit(1)
                ).scalar_one_or_none()
            if row is not None:
                return row

        name = str(template_name or "").strip()
        if name:
            name_lower = name.lower()
            rows = list(
                db.execute(
                    select(TelnyxWhatsappTemplate)
                    .where(func.lower(TelnyxWhatsappTemplate.name) == name_lower)
                    .order_by(TelnyxWhatsappTemplate.updated_at.desc())
                ).scalars().all()
            )
            for row in rows:
                if str(row.status or "").upper() == "APPROVED":
                    return row
            if rows:
                return rows[0]

        if sales_template_key:
            return TelnyxWhatsappTemplateSyncService.get_for_sales_key(db, sales_template_key)

        return None

    @staticmethod
    def build_components_for_row(
        row: TelnyxWhatsappTemplate | None,
        *,
        variables: dict[str, str] | None = None,
        db: Session | None = None,
    ) -> list[dict[str, Any]] | None:
        if row is None:
            return None
        vars_ = variables or TEST_TEMPLATE_VARIABLES
        from app.services.survey_whatsapp_template_service import _effective_components

        stored_components: list[Any] | None = _effective_components(row, db=db) or None
        if not stored_components:
            try:
                parsed = json.loads(row.components_json or "null")
                if isinstance(parsed, list):
                    stored_components = parsed
            except json.JSONDecodeError:
                stored_components = None

        url_idx = url_button_index_from_components(stored_components)
        sales_key = str(row.sales_template_key or "").strip().lower()
        url_template_keys = {"sales_offer", "sales_offer_followup", "sales_offer_keyword_confirm"}
        include_url_button = False
        if sales_key in url_template_keys:
            if url_idx is None and not stored_components:
                url_idx = 0
            if url_idx is not None:
                include_url_button = (
                    url_button_has_dynamic_suffix(stored_components) if stored_components else True
                )

        if row.sales_template_key:
            return build_telnyx_components(
                row.sales_template_key,
                vars_,
                url_button_index=url_idx if url_idx is not None else 0,
                include_url_button=include_url_button,
            )
        built = build_test_components_for_template_name(row.name)
        if built is not None:
            return built
        components = stored_components
        if components is None:
            try:
                components = json.loads(row.components_json or "null")
            except json.JSONDecodeError:
                components = None
        count = _body_variable_count(components if isinstance(components, list) else None)
        if count <= 0:
            return None
        first = str(vars_.get("first_name") or "Alex")
        org = str(
            vars_.get("organisation_name")
            or vars_.get("clinic_name")
            or vars_.get("business_name")
            or ""
        ).strip()
        filler = [
            first,
            org or str(vars_.get("offer_line") or "Your business"),
            str(vars_.get("organiser_name") or vars_.get("survey_organiser") or org or first),
            str(vars_.get("offer_summary") or "Ref"),
        ]
        values = filler[:count]
        while len(values) < count:
            values.append("—")
        return [{"type": "body", "parameters": [{"type": "text", "text": v[:1024]} for v in values]}]

    @staticmethod
    def sales_template_names() -> dict[str, str]:
        return dict(TELNYX_SALES_TEMPLATE_NAMES)
