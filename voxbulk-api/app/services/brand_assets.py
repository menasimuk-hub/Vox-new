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

PUBLIC_ASSET_KEYS: tuple[str, ...] = (
    "logo-black",
    "logo-white",
    "logo-dark",
    "logo-light",
    "icon-black",
    "icon-white",
    "icon-dark",
    "icon-light",
    "favicon",
)

# Backwards-compatible alias map (legacy filenames without extension in PUBLIC_ASSETS).
PUBLIC_ASSETS: dict[str, str] = {key: key for key in PUBLIC_ASSET_KEYS}

_ASSET_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "favicon": (".ico", ".png", ".svg"),
    "logo-black": (".png", ".svg", ".webp", ".jpg", ".jpeg"),
    "logo-white": (".png", ".svg", ".webp", ".jpg", ".jpeg"),
    "logo-dark": (".png", ".svg", ".webp", ".jpg", ".jpeg"),
    "logo-light": (".png", ".svg", ".webp", ".jpg", ".jpeg"),
    "icon-black": (".png", ".svg", ".webp", ".jpg", ".jpeg"),
    "icon-white": (".png", ".svg", ".webp", ".jpg", ".jpeg"),
    "icon-dark": (".png", ".svg", ".webp", ".jpg", ".jpeg"),
    "icon-light": (".png", ".svg", ".webp", ".jpg", ".jpeg"),
}

_STRIP_EXTENSIONS = (".svg", ".png", ".ico", ".jpg", ".jpeg", ".webp")


def logos_dir() -> Path:
    return _LOGOS_DIR


def normalize_asset_name(name: str) -> str:
    key = str(name or "").strip().lower()
    for ext in _STRIP_EXTENSIONS:
        if key.endswith(ext):
            return key[: -len(ext)]
    return key


def asset_extensions(name: str) -> tuple[str, ...]:
    key = normalize_asset_name(name)
    return _ASSET_EXTENSIONS.get(key, (".png", ".svg", ".webp", ".jpg", ".jpeg", ".ico"))


_CALENDAR_ICON_KEYS: tuple[str, ...] = (
    "calendar-google",
    "calendar-outlook",
    "calendar-apple",
)


def asset_path(name: str) -> Path | None:
    key = normalize_asset_name(name)
    if key in _CALENDAR_ICON_KEYS:
        path = _LOGOS_DIR / "calendar" / f"{key}.png"
        return path if path.is_file() else None
    if key not in PUBLIC_ASSETS:
        return None
    for ext in asset_extensions(key):
        path = _LOGOS_DIR / f"{key}{ext}"
        if path.is_file():
            return path
    return None


def list_available_assets() -> dict[str, str]:
    """Return asset key -> filename on disk (for /public/brand listing)."""
    out: dict[str, str] = {}
    for key in (*PUBLIC_ASSET_KEYS, *_CALENDAR_ICON_KEYS):
        path = asset_path(key)
        if path is not None:
            out[key] = path.name
    return out


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
    """HTTPS URL for email clients. Uses .png in URL when a PNG file is on disk."""
    path = asset_path(variant)
    key = normalize_asset_name(variant)
    if path is not None and path.suffix.lower() == ".png":
        return public_brand_url(api_public_origin(), f"{key}.png")
    return public_brand_url(api_public_origin(), key)


def public_brand_url(api_origin: str, name: str) -> str:
    origin = str(api_origin or "").rstrip("/")
    return f"{origin}/public/brand/{name}"
