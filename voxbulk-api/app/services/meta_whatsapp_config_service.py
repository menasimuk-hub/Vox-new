from __future__ import annotations

import re
from typing import Any

_DEFAULT_GRAPH_API_VERSION = "v25.0"
_META_WEBHOOK_SUFFIX = "/webhooks/meta/whatsapp"


class MetaWhatsappConfigError(ValueError):
    pass


def _normalize_webhook_base(url: str) -> str:
    base = str(url or "").strip().rstrip("/")
    if not base:
        return ""
    lower = base.lower()
    if lower.endswith(_META_WEBHOOK_SUFFIX):
        base = base[: -len(_META_WEBHOOK_SUFFIX)].rstrip("/")
    return base


def _normalize_e164(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    return f"+{digits}" if not raw.startswith("+") else f"+{digits}"


def validate_meta_whatsapp_config(config: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(config or {})
    cfg["graph_api_version"] = str(cfg.get("graph_api_version") or _DEFAULT_GRAPH_API_VERSION).strip() or _DEFAULT_GRAPH_API_VERSION
    cfg["app_id"] = str(cfg.get("app_id") or "").strip()
    cfg["waba_id"] = str(cfg.get("waba_id") or "").strip()
    cfg["phone_number_id"] = str(cfg.get("phone_number_id") or "").strip()
    cfg["whatsapp_from"] = _normalize_e164(str(cfg.get("whatsapp_from") or ""))
    cfg["webhook_base_url"] = _normalize_webhook_base(str(cfg.get("webhook_base_url") or ""))
    cfg["webhook_url"] = (
        f"{cfg['webhook_base_url']}{_META_WEBHOOK_SUFFIX}" if cfg["webhook_base_url"] else ""
    )
    return cfg


def graph_api_base(config: dict[str, Any]) -> str:
    version = str(config.get("graph_api_version") or _DEFAULT_GRAPH_API_VERSION).strip() or _DEFAULT_GRAPH_API_VERSION
    if not version.startswith("v"):
        version = f"v{version}"
    return f"https://graph.facebook.com/{version}"
