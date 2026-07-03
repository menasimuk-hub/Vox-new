from __future__ import annotations

from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config


def test_validate_meta_whatsapp_config_builds_webhook_url():
    cfg = validate_meta_whatsapp_config(
        {
            "webhook_base_url": "https://api.voxbulk.com/webhooks/meta/whatsapp",
            "graph_api_version": "v25.0",
        }
    )
    assert cfg["webhook_base_url"] == "https://api.voxbulk.com"
    assert cfg["webhook_url"] == "https://api.voxbulk.com/webhooks/meta/whatsapp"
    assert cfg["graph_api_version"] == "v25.0"
