from __future__ import annotations

import base64
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services.provider_settings import ProviderSettingsService


class ZoomService:
    TOKEN_URL = "https://zoom.us/oauth/token"

    @staticmethod
    def _env_credentials() -> tuple[str, str, str, str]:
        from app.core.config import get_settings

        settings = get_settings()
        return (
            str(getattr(settings, "zoom_account_id", "") or "").strip(),
            str(getattr(settings, "zoom_client_id", "") or "").strip(),
            str(getattr(settings, "zoom_client_secret", "") or "").strip(),
            str(getattr(settings, "zoom_base_url", "") or "").strip().rstrip("/"),
        )

    @staticmethod
    def _db_has_any_zoom_data(
        zoom_cfg: dict[str, Any],
        telnyx_cfg: dict[str, Any],
    ) -> bool:
        """True when either provider row has any Zoom credential field stored."""
        for key in ("account_id", "client_id", "client_secret", "base_url"):
            if str(zoom_cfg.get(key) or "").strip():
                return True
        for key in ("zoom_account_id", "zoom_client_id", "zoom_client_secret", "zoom_base_url"):
            if str(telnyx_cfg.get(key) or "").strip():
                return True
        return False

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        """Resolve Zoom OAuth credentials — DB-first, provider=zoom row is canonical."""
        zoom_cfg, _zoom_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="zoom")
        zoom_cfg = zoom_cfg or {}
        zoom_account = str(zoom_cfg.get("account_id") or "").strip()
        zoom_client = str(zoom_cfg.get("client_id") or "").strip()
        zoom_secret = str(zoom_cfg.get("client_secret") or "").strip()
        zoom_base = str(zoom_cfg.get("base_url") or "").strip().rstrip("/")
        zoom_complete = bool(zoom_account and zoom_client and zoom_secret)

        telnyx_cfg, _telnyx_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        telnyx_cfg = telnyx_cfg or {}
        telnyx_account = str(telnyx_cfg.get("zoom_account_id") or "").strip()
        telnyx_client = str(telnyx_cfg.get("zoom_client_id") or "").strip()
        telnyx_secret = str(telnyx_cfg.get("zoom_client_secret") or "").strip()
        telnyx_base = str(telnyx_cfg.get("zoom_base_url") or "").strip().rstrip("/")
        telnyx_complete = bool(telnyx_account and telnyx_client and telnyx_secret)

        default_base = "https://api.zoom.us/v2"

        # Single source of truth: prefer the standalone zoom provider row when complete.
        if zoom_complete:
            account_id = zoom_account
            client_id = zoom_client
            client_secret = zoom_secret
            base_url = zoom_base or default_base
        elif telnyx_complete:
            account_id = telnyx_account
            client_id = telnyx_client
            client_secret = telnyx_secret
            base_url = telnyx_base or default_base
        else:
            # Partial merge from both DB rows (no .env yet).
            account_id = zoom_account or telnyx_account
            client_id = zoom_client or telnyx_client
            client_secret = zoom_secret or telnyx_secret
            base_url = zoom_base or telnyx_base or default_base

        # .env bootstrap only when both DB sources are completely empty.
        if not ZoomService._db_has_any_zoom_data(zoom_cfg, telnyx_cfg):
            env_account, env_client, env_secret, env_base = ZoomService._env_credentials()
            account_id = account_id or env_account
            client_id = client_id or env_client
            client_secret = client_secret or env_secret
            base_url = base_url or env_base or default_base

        if not account_id or not client_id or not client_secret:
            raise ValueError("Zoom account_id, client_id and client_secret are required")
        return {
            "account_id": account_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "base_url": base_url or default_base,
        }

    @staticmethod
    def _telnyx_zoom_config(db: Session) -> dict[str, Any] | None:
        """Secondary credential candidate for token retry (telnyx.zoom_* row)."""
        telnyx_cfg, _telnyx_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        telnyx_cfg = telnyx_cfg or {}
        account_id = str(telnyx_cfg.get("zoom_account_id") or "").strip()
        client_id = str(telnyx_cfg.get("zoom_client_id") or "").strip()
        client_secret = str(telnyx_cfg.get("zoom_client_secret") or "").strip()
        if not client_secret and account_id and client_id:
            zoom_cfg, _zoom_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="zoom")
            mirror_secret = str((zoom_cfg or {}).get("client_secret") or "").strip()
            if mirror_secret:
                client_secret = mirror_secret
        if not account_id or not client_id or not client_secret:
            return None
        base_url = str(telnyx_cfg.get("zoom_base_url") or "https://api.zoom.us/v2").strip().rstrip("/")
        return {
            "account_id": account_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "base_url": base_url or "https://api.zoom.us/v2",
        }

    @staticmethod
    def _request_access_token(cfg: dict[str, Any]) -> tuple[int, dict[str, Any] | None, str]:
        auth = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
        url = f"{ZoomService.TOKEN_URL}?grant_type=account_credentials&account_id={cfg['account_id']}"
        with httpx.Client(timeout=20.0) as client:
            res = client.post(url, headers={"Authorization": f"Basic {auth}"})
        text = res.text or ""
        parsed: dict[str, Any] | None = None
        if text:
            try:
                payload = res.json()
                if isinstance(payload, dict):
                    parsed = payload
            except Exception:
                parsed = None
        return res.status_code, parsed, text

    @staticmethod
    def _token_error_detail(status: int, parsed: dict[str, Any] | None, raw: str) -> str:
        if isinstance(parsed, dict):
            reason = str(parsed.get("reason") or parsed.get("error_description") or "").strip()
            error = str(parsed.get("error") or "").strip()
            if reason and error:
                return f"{reason} ({error})"
            if reason:
                return reason
            if error:
                return error
        text = str(raw or "").strip()
        return text[:300] if text else f"HTTP {status}"

    @staticmethod
    def _is_invalid_client_error(status: int, parsed: dict[str, Any] | None, raw: str) -> bool:
        if status not in (400, 401):
            return False
        if isinstance(parsed, dict):
            err = str(parsed.get("error") or "").strip().lower()
            reason = str(parsed.get("reason") or parsed.get("error_description") or "").strip().lower()
            if err == "invalid_client" or "invalid client" in reason:
                return True
        return "invalid client" in str(raw or "").strip().lower()

    @staticmethod
    def _auth_context(db: Session) -> tuple[str, dict[str, Any], str]:
        primary = ZoomService._config(db)
        candidates: list[tuple[str, dict[str, Any]]] = [("zoom", primary)]
        telnyx = ZoomService._telnyx_zoom_config(db)
        if telnyx is not None:
            primary_key = (str(primary["account_id"]), str(primary["client_id"]), str(primary["client_secret"]))
            telnyx_key = (str(telnyx["account_id"]), str(telnyx["client_id"]), str(telnyx["client_secret"]))
            if telnyx_key != primary_key:
                candidates.append(("telnyx.zoom_*", telnyx))

        errors: list[tuple[str, str]] = []
        for idx, (source, cfg) in enumerate(candidates):
            status, parsed, raw = ZoomService._request_access_token(cfg)
            if status < 400:
                token = str((parsed or {}).get("access_token") or "").strip()
                if token:
                    return token, cfg, source
                errors.append((source, "Zoom token response missing access_token"))
                continue
            detail = ZoomService._token_error_detail(status, parsed, raw)
            errors.append((source, detail))
            should_try_next = (
                idx == 0
                and len(candidates) > 1
                and ZoomService._is_invalid_client_error(status, parsed, raw)
            )
            if not should_try_next:
                break

        if not errors:
            raise ValueError("Zoom token request failed")
        if len(errors) == 1:
            raise ValueError(f"Zoom token request failed: {errors[0][1]}")
        joined = " ; ".join(f"{source}: {detail}" for source, detail in errors)
        raise ValueError(f"Zoom token request failed: {joined}")

    @staticmethod
    def get_access_token(db: Session) -> str:
        token, _cfg, _source = ZoomService._auth_context(db)
        return token

    @staticmethod
    def test_connection(db: Session) -> dict[str, Any]:
        token, cfg, _source = ZoomService._auth_context(db)
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
        token, cfg, _source = ZoomService._auth_context(db)
        payload: dict[str, Any] = {
            "topic": topic,
            "type": 2,
            "duration": max(int(duration_min or 30), 15),
            "settings": {
                "join_before_host": True,
                "waiting_room": False,
                "auto_recording": "cloud",
            },
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
            "uuid": data.get("uuid"),
        }

    @staticmethod
    def is_configured(db: Session) -> bool:
        try:
            ZoomService._config(db)
            return True
        except ValueError:
            return False

    @staticmethod
    def is_interview_delivery_enabled(db: Session) -> bool:
        """True when Admin → Integrations → Zoom is enabled with valid OAuth credentials."""
        return ZoomService.is_configured(db)

    @staticmethod
    def _vtt_to_text(raw: str) -> str:
        lines: list[str] = []
        for line in str(raw or "").splitlines():
            s = line.strip()
            if not s or s.upper().startswith("WEBVTT"):
                continue
            if s.isdigit() or "-->" in s:
                continue
            lines.append(s)
        return "\n".join(lines).strip()

    @staticmethod
    def fetch_meeting_artifacts(db: Session, meeting_id: str) -> dict[str, Any]:
        """Fetch cloud recording + transcript for a completed Zoom meeting."""
        mid = str(meeting_id or "").strip()
        if not mid:
            return {"ready": False, "error": "missing meeting id", "provider": "zoom_oauth"}

        token, cfg, _source = ZoomService._auth_context(db)
        with httpx.Client(timeout=30.0) as client:
            res = client.get(
                f"{cfg['base_url']}/meetings/{mid}/recordings",
                headers={"Authorization": f"Bearer {token}"},
            )
        if res.status_code == 404:
            return {
                "ready": False,
                "provider": "zoom_oauth",
                "error": "Zoom recording not ready yet (404)",
            }
        if res.status_code >= 400:
            return {
                "ready": False,
                "provider": "zoom_oauth",
                "error": f"Zoom recordings API HTTP {res.status_code}: {res.text[:200]}",
            }

        body = res.json()
        files = body.get("recording_files") if isinstance(body, dict) else None
        if not isinstance(files, list):
            files = []

        recording_url = ""
        transcript = ""
        for item in files:
            if not isinstance(item, dict):
                continue
            file_type = str(item.get("file_type") or "").upper()
            download_url = str(item.get("download_url") or "").strip()
            if not download_url:
                continue
            if file_type in {"MP4", "M4A", "AUDIO_ONLY", "SHARED_SCREEN_WITH_SPEAKER_VIEW"} and not recording_url:
                recording_url = download_url
            if file_type in {"TRANSCRIPT", "CC", "CHAT_FILE"} or "TRANSCRIPT" in file_type:
                try:
                    with httpx.Client(timeout=30.0) as client:
                        tr = client.get(download_url, headers={"Authorization": f"Bearer {token}"})
                    if tr.status_code < 400 and tr.text.strip():
                        transcript = ZoomService._vtt_to_text(tr.text)
                except Exception:
                    pass

        ready = bool(recording_url) or len(transcript) >= 20
        return {
            "ready": ready,
            "provider": "zoom_oauth",
            "transcript": transcript or None,
            "recording_url": recording_url or None,
            "error": None if ready else "Zoom cloud recording/transcript not ready yet",
        }
