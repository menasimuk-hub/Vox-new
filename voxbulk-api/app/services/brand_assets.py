"""Central VOXBULK logo, icon, and favicon assets (voxbulk-api/logos/)."""

from __future__ import annotations

import base64
import mimetypes
from functools import lru_cache
from pathlib import Path

_LOGOS_DIR = Path(__file__).resolve().parent.parent.parent / "logos"

# Dashboard theme — beige + deep navy (matches dashboard-web/src/styles.css)
BRAND_COLORS = {
    "background": "#f5f1ea",
    "surface": "#fbf8f3",
    "ink": "#2a2824",
    "ink_muted": "#6b6560",
    "primary": "#1a2d5c",
    "primary_light": "#e6edf8",
    "accent": "#185fa5",
    "success": "#3b6d11",
    "border": "#e5e0d8",
}

PUBLIC_ASSETS: dict[str, str] = {
    "logo-black": "logo-black.svg",
    "logo-white": "logo-white.svg",
    "icon-black": "icon-black.svg",
    "icon-white": "icon-white.svg",
    "favicon": "favicon.ico",
}


def logos_dir() -> Path:
    return _LOGOS_DIR


def asset_path(name: str) -> Path | None:
    key = str(name or "").strip().lower()
    filename = PUBLIC_ASSETS.get(key)
    if not filename:
        return None
    path = _LOGOS_DIR / filename
    return path if path.is_file() else None


def asset_media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


@lru_cache(maxsize=16)
def asset_data_uri(name: str) -> str | None:
    path = asset_path(name)
    if path is None:
        return None
    raw = path.read_bytes()
    mime = asset_media_type(path)
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def logo_data_uri(*, variant: str = "logo-black") -> str | None:
    return asset_data_uri(variant)


def api_public_origin() -> str:
    """Public API base URL for absolute links in emails and PDFs."""
    from app.core.config import get_settings

    settings = get_settings()
    dash = str(settings.dashboard_app_origin or settings.public_app_origin or "").strip().rstrip("/")
    if dash and "dashboard." in dash:
        return dash.replace("dashboard.", "api.", 1)
    env = str(settings.env or "").lower()
    if env in {"production", "prod", "staging"}:
        return "https://api.voxbulk.com"
    return "http://127.0.0.1:8000"


def email_logo_url(*, variant: str = "logo-black") -> str:
    return public_brand_url(api_public_origin(), variant)


def public_brand_url(api_origin: str, name: str) -> str:
    origin = str(api_origin or "").rstrip("/")
    return f"{origin}/public/brand/{name}"
