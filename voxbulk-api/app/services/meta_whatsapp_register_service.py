"""Meta Cloud API phone number register / verify (Connection Profile ops)."""

from __future__ import annotations

import json
from typing import Any

import httpx

DEFAULT_GRAPH_VERSION = "v25.0"

_PIN_ERROR_MARKERS = (
    "pin",
    "two step",
    "two-step",
    "verification",
    "133005",
    "133006",
    "133008",
    "100",
)


def graph_url(*, phone_number_id: str, path: str, graph_version: str) -> str:
    version = graph_version if graph_version.startswith("v") else f"v{graph_version}"
    base = f"https://graph.facebook.com/{version}"
    return f"{base}/{phone_number_id}/{path}"


def meta_phone_post(
    *,
    access_token: str,
    phone_number_id: str,
    path: str,
    body: dict[str, Any],
    graph_version: str = DEFAULT_GRAPH_VERSION,
    phone_e164: str | None = None,
) -> dict[str, Any]:
    url = graph_url(phone_number_id=phone_number_id, path=path, graph_version=graph_version)
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "status_code": 0,
            "phone": phone_e164,
            "url": url,
            "error": str(exc),
            "payload": None,
        }
    try:
        payload: dict[str, Any] | str = response.json()
    except ValueError:
        payload = response.text
    return {
        "ok": response.status_code < 400,
        "status_code": response.status_code,
        "phone": phone_e164,
        "url": url,
        "payload": payload,
        "needs_sms_verify": response.status_code >= 400 and _pin_or_verify_error(response.status_code, payload),
    }


def request_verification_code(
    *,
    access_token: str,
    phone_number_id: str,
    phone_e164: str | None = None,
    graph_version: str = DEFAULT_GRAPH_VERSION,
    code_method: str = "SMS",
) -> dict[str, Any]:
    method = str(code_method or "SMS").strip().upper()
    if method not in {"SMS", "VOICE"}:
        method = "SMS"
    return meta_phone_post(
        access_token=access_token,
        phone_number_id=phone_number_id,
        path="request_code",
        body={"code_method": method, "language": "en"},
        graph_version=graph_version,
        phone_e164=phone_e164,
    )


def verify_verification_code(
    *,
    access_token: str,
    phone_number_id: str,
    code: str,
    phone_e164: str | None = None,
    graph_version: str = DEFAULT_GRAPH_VERSION,
) -> dict[str, Any]:
    return meta_phone_post(
        access_token=access_token,
        phone_number_id=phone_number_id,
        path="verify_code",
        body={"code": str(code or "").strip()},
        graph_version=graph_version,
        phone_e164=phone_e164,
    )


def register_phone_number(
    *,
    access_token: str,
    phone_number_id: str,
    pin: str,
    phone_e164: str | None = None,
    graph_version: str = DEFAULT_GRAPH_VERSION,
) -> dict[str, Any]:
    return meta_phone_post(
        access_token=access_token,
        phone_number_id=phone_number_id,
        path="register",
        body={"messaging_product": "whatsapp", "pin": str(pin or "").strip()},
        graph_version=graph_version,
        phone_e164=phone_e164,
    )


def get_phone_number_status(
    *,
    access_token: str,
    phone_number_id: str,
    graph_version: str = DEFAULT_GRAPH_VERSION,
) -> dict[str, Any]:
    version = graph_version if graph_version.startswith("v") else f"v{graph_version}"
    url = f"https://graph.facebook.com/{version}/{phone_number_id}"
    params = {
        "fields": "id,display_phone_number,verified_name,code_verification_status,quality_rating,status",
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers, params=params)
        payload = response.json() if response.content else {}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc), "payload": None}
    return {
        "ok": response.status_code < 400,
        "status_code": response.status_code,
        "url": url,
        "payload": payload if isinstance(payload, dict) else {"raw": payload},
    }


def _pin_or_verify_error(status: int, payload: dict[str, Any] | str) -> bool:
    if status < 400:
        return False
    text = json.dumps(payload).lower() if isinstance(payload, dict) else str(payload).lower()
    return any(marker in text for marker in _PIN_ERROR_MARKERS)
