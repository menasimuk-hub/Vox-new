from unittest.mock import patch

from app.services.script_moderation_service import apply_script_moderation_gate


def test_unchanged_approved_arabic_script_skips_re_moderation():
    arabic_script = "\n".join(
        [
            "OPENING DISCLOSURE",
            "مرحبًا، هذه المكالمة مسجّلة.",
            "",
            "INTRO",
            "هل الوقت مناسب للمقابلة؟",
            "",
            "QUESTIONS",
            "1. عرّف بنفسك باختصار.",
            "2. لماذا تقدمت لهذه الوظيفة؟",
            "",
            "CLOSING",
            "شكرًا لوقتك.",
        ]
    )
    prev = {
        "approved_script": arabic_script,
        "script_approved": True,
        "script_moderation_status": "approved",
        "script_language_code": "ar",
    }
    patch_body = {
        "approved_script": arabic_script,
        "script_approved": True,
        "script_language_code": "ar",
    }

    with patch("app.services.script_moderation_service.moderate_content") as mock_moderate:
        result = apply_script_moderation_gate(
            service_code="interview",
            config_patch=patch_body,
            previous_cfg=prev,
            db=None,
        )
        mock_moderate.assert_not_called()

    assert result["script_approved"] is True
    assert result["script_moderation_status"] == "approved"


def test_moderate_content_accepts_language_hint():
    from app.services.moderation import moderate_content

    captured: dict = {}

    def fake_post(url, json=None, headers=None):
        captured["user_content"] = json["messages"][1]["content"]
        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": '{"safe": true, "category": "safe", "reason": ""}'}}]}

        return Resp()

    with patch("app.services.moderation._moderation_runtime_config", return_value={"api_key": "k", "base_url": "http://x", "model": "m"}):
        with patch("app.services.providers.openai_service.OpenAIProviderService._http_client") as mock_client:
            mock_client.return_value.post = fake_post
            result = moderate_content("مرحبًا، هذه مقابلة مهنية.", db=None, language_code="ar")

    assert result["safe"] is True
    assert "Script language: Arabic" in captured["user_content"]
