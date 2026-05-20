from __future__ import annotations

import base64
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services.provider_settings import ProviderSettingsService


class ZoomService:
    TOKEN_URL = "https://zoom.us/oauth/token"

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="zoom")
        if not cfg or not enabled:
            raise ValueError("Zoom is not configured")
        account_id = str(cfg.get("account_id") or "").strip()
        client_id = str(cfg.get("client_id") or "").strip()
        client_secret = str(cfg.get("client_secret") or "").strip()
        if not account_id or not client_id or not client_secret:
            raise ValueError("Zoom account_id, client_id and client_secret are required")
        return {
            "account_id": account_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "base_url": str(cfg.get("base_url") or "https://api.zoom.us/v2").strip().rstrip("/"),
        }

    @staticmethod
    def get_access_token(db: Session) -> str:
        cfg = ZoomService._config(db)
        auth = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
        url = f"{ZoomService.TOKEN_URL}?grant_type=account_credentials&account_id={cfg['account_id']}"
        with httpx.Client(timeout=20.0) as client:
            res = client.post(url, headers={"Authorization": f"Basic {auth}"})
        if res.status_code >= 400:
            raise ValueError(f"Zoom token request failed: {res.text[:300]}")
        data = res.json()
        token = str(data.get("access_token") or "").strip()
        if not token:
            raise ValueError("Zoom token response missing access_token")
        return token

    @staticmethod
    def test_connection(db: Session) -> dict[str, Any]:
        token = ZoomService.get_access_token(db)
        cfg = ZoomService._config(db)
        with httpx.Client(timeout=20.0) as client:
            res = client.get(f"{cfg['base_url']}/users/me", headers={"Authorization": f"Bearer {token}"})
        if res.status_code >= 400:
            return {"ok": False, "detail": res.text[:300]}
        user = res.json()
        return {
            "ok": True,
            "email": user.get("email"),
            "account_id": user.get("account_id"),
            "type": user.get("type"),
        }

    @staticmethod
    def create_meeting(db: Session, *, topic: str, start_time_iso: str | None = None, duration_min: int = 30) -> dict[str, Any]:
        token = ZoomService.get_access_token(db)
        cfg = ZoomService._config(db)
        payload: dict[str, Any] = {
            "topic": topic,
            "type": 2,
            "duration": max(int(duration_min or 30), 15),
            "settings": {"join_before_host": True, "waiting_room": False},
        }
        if start_time_iso:
            payload["start_time"] = start_time_iso
        with httpx.Client(timeout=20.0) as client:
            res = client.post(
                f"{cfg['base_url']}/users/me/meetings",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
        if res.status_code >= 400:
            raise ValueError(f"Zoom meeting create failed: {res.text[:300]}")
        data = res.json()
        return {
            "id": data.get("id"),
            "join_url": data.get("join_url"),
            "start_url": data.get("start_url"),
            "password": data.get("password"),
        }
