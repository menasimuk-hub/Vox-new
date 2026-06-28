from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.telnyx_api_key import require_telnyx_api_key

TELNYX_API_BASE = "https://api.telnyx.com/v2"


def _telnyx_request(
    db: Session,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any] | list[Any] | None, str]:
    api_key, _source = require_telnyx_api_key(db)
    url = f"{TELNYX_API_BASE}{path if path.startswith('/') else '/' + path}"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    with httpx.Client(timeout=timeout, verify=httpx_ssl_verify()) as client:
        response = client.request(method.upper(), url, headers=headers, json=json_body, params=params)
    text = response.text or ""
    parsed: dict[str, Any] | list[Any] | None = None
    if text:
        try:
            parsed = response.json()
        except Exception:
            parsed = None
    return response.status_code, parsed, text


def _first_error(status_code: int, parsed: dict[str, Any] | list[Any] | None, raw: str) -> str:
    if isinstance(parsed, dict):
        errors = parsed.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                detail = str(first.get("detail") or first.get("title") or "").strip()
                if detail:
                    return detail
            text = str(first or "").strip()
            if text:
                return text
        detail = str(parsed.get("detail") or parsed.get("message") or "").strip()
        if detail:
            return detail
    if isinstance(parsed, list) and parsed:
        first = parsed[0]
        if isinstance(first, dict):
            detail = str(first.get("detail") or first.get("title") or "").strip()
            if detail:
                return detail
        text = str(first or "").strip()
        if text:
            return text
    fallback = (raw or "").strip().replace("\n", " ")
    if fallback:
        return fallback[:300]
    return f"Telnyx returned HTTP {status_code}"


def _connection_from_payload(parsed: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    if isinstance(parsed, dict):
        data = parsed.get("data")
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    return row
        return parsed
    if isinstance(parsed, list):
        for row in parsed:
            if isinstance(row, dict):
                return row
    return {}


def _serialize_connection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or "").strip(),
        "external_sip_connection": str(row.get("external_sip_connection") or "").strip().lower(),
        "active": bool(row.get("active")),
        "credential_active": row.get("credential_active"),
        "record_type": str(row.get("record_type") or "").strip() or None,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "webhook_event_url": str(row.get("webhook_event_url") or "").strip() or None,
    }


class TelnyxExternalConnectionService:
    @staticmethod
    def list_outbound_voice_profiles(db: Session, *, limit: int = 100) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page[size]": max(int(limit or 100), 1)}
        status, parsed, raw = _telnyx_request(
            db,
            "GET",
            "/outbound_voice_profiles",
            params=params,
        )
        if status >= 400:
            raise ValueError(_first_error(status, parsed, raw))
        rows: list[dict[str, Any]] = []
        if isinstance(parsed, dict):
            data = parsed.get("data")
            if isinstance(data, list):
                rows = [r for r in data if isinstance(r, dict)]
            elif isinstance(data, dict):
                rows = [data]
        elif isinstance(parsed, list):
            rows = [r for r in parsed if isinstance(r, dict)]
        result: list[dict[str, Any]] = []
        for row in rows:
            profile_id = str(row.get("id") or "").strip()
            if not profile_id:
                continue
            result.append(
                {
                    "id": profile_id,
                    "name": str(row.get("name") or "").strip() or f"Profile {profile_id[:8]}…",
                    "active": bool(row.get("active")) if row.get("active") is not None else None,
                }
            )
        return result

    @staticmethod
    def list_connections(
        db: Session,
        *,
        external_sip_connection: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page[size]": max(int(limit or 50), 1)}
        sip = str(external_sip_connection or "").strip().lower()
        if sip:
            params["filter[external_sip_connection]"] = sip
        status, parsed, raw = _telnyx_request(db, "GET", "/external_connections", params=params)
        if status >= 400:
            raise ValueError(_first_error(status, parsed, raw))
        rows: list[dict[str, Any]] = []
        if isinstance(parsed, dict):
            data = parsed.get("data")
            if isinstance(data, list):
                rows = [r for r in data if isinstance(r, dict)]
            elif isinstance(data, dict):
                rows = [data]
        elif isinstance(parsed, list):
            rows = [r for r in parsed if isinstance(r, dict)]
        return [_serialize_connection(r) for r in rows]

    @staticmethod
    def get_connection(db: Session, connection_id: str) -> dict[str, Any]:
        cid = str(connection_id or "").strip()
        if not cid:
            raise ValueError("connection_id is required")
        status, parsed, raw = _telnyx_request(
            db, "GET", f"/external_connections/{cid}"
        )
        if status >= 400:
            raise ValueError(_first_error(status, parsed, raw))
        row = _connection_from_payload(parsed)
        payload = _serialize_connection(row)
        if not payload.get("id"):
            raise ValueError("Telnyx returned an empty external connection response.")
        return payload

    @staticmethod
    def refresh_operator_connect(db: Session) -> dict[str, Any]:
        status, parsed, raw = _telnyx_request(db, "POST", "/operator_connect/actions/refresh")
        if status not in (200, 202):
            raise ValueError(_first_error(status, parsed, raw))
        data: dict[str, Any] = {}
        if isinstance(parsed, dict):
            data = parsed
            if isinstance(parsed.get("data"), dict):
                data = {**parsed, **parsed.get("data")}
        success = data.get("success")
        message = str(data.get("message") or "").strip()
        if not message:
            message = (
                "Operator Connect refresh started."
                if status == 202
                else "Operator Connect refresh accepted."
            )
        return {
            "ok": bool(success) if success is not None else True,
            "status_code": status,
            "message": message,
        }

    @staticmethod
    def test_operator_connect(db: Session, *, refresh_first: bool = True) -> dict[str, Any]:
        refresh_result: dict[str, Any] | None = None
        if refresh_first:
            refresh_result = TelnyxExternalConnectionService.refresh_operator_connect(db)
        rows = TelnyxExternalConnectionService.list_connections(
            db,
            external_sip_connection="operator_connect",
            limit=50,
        )
        active_count = sum(1 for r in rows if r.get("active"))
        ok = bool(rows) and active_count > 0
        if ok:
            message = f"Found {len(rows)} Operator Connect connection(s); active: {active_count}."
        else:
            message = (
                "Operator Connect refresh accepted but no active Microsoft Teams connection is visible yet. "
                "Wait a minute and run Test again."
            )
        return {
            "ok": ok,
            "message": message,
            "refresh": refresh_result,
            "connection_count": len(rows),
            "active_connection_count": active_count,
            "connections": rows[:5],
        }
