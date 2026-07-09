"""Tests for marketing → utility purge pipeline (Qwen / multilang / discovery)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.customer_feedback.feedback_telnyx_push_service import suggest_next_cfs_version_name
from app.services.survey_wa_utility_rewrite_service import (
    DEFAULT_UTILITY_LLM_MODEL,
    rewrite_body_for_utility,
)
from app.services.wa_marketing_purge_service import manifest_items_to_plan
from app.services.wa_marketing_utility_multilang_service import (
    LangVariant,
    TemplateGroup,
    build_groups_from_candidates,
    parse_group_key,
)
from app.services.wa_template_product_scope import is_managed_product_remote_name, is_protected_template_name


def test_managed_product_remote_names():
    assert is_managed_product_remote_name("was_restaurant_overall_002_en")
    assert is_managed_product_remote_name("cfs_hotel_overall_experience_en_v1")
    assert is_managed_product_remote_name("voxbulk_survey_food_quality_abc_d85d5a")
    assert not is_managed_product_remote_name("voxbulk_interview_email_sent_v2")
    assert is_protected_template_name("voxbulk_interview_email_sent_v2")


def test_parse_group_key_was_and_cfs():
    assert parse_group_key("was_restaurant_overall_experience_002_en", product="survey") == (
        "was_restaurant_overall_experience_002"
    )
    assert parse_group_key("cfs_hotel_overall_experience_en_v1", product="feedback") == (
        "cfs_hotel_overall_experience_v1"
    )


def test_build_groups_from_candidates_clusters_langs():
    candidates = [
        {
            "actionable": True,
            "product": "survey",
            "remote_name": "was_restaurant_overall_002_en",
            "name": "was_restaurant_overall_002_en",
            "remote_language": "en_gb",
            "id": 1,
            "full_body": "How was your visit?",
            "buttons": ["Good", "OK", "Bad"],
        },
        {
            "actionable": True,
            "product": "survey",
            "remote_name": "was_restaurant_overall_002_ar",
            "name": "was_restaurant_overall_002_ar",
            "remote_language": "ar",
            "id": 2,
            "full_body": "كيف كانت زيارتك؟",
            "buttons": ["Good", "OK", "Bad"],
        },
    ]
    groups = build_groups_from_candidates(candidates)
    assert len(groups) == 1
    assert len(groups[0].variants) == 2


def test_suggest_next_cfs_version_name():
    used = {"cfs_hotel_overall_experience_en_v2"}
    assert (
        suggest_next_cfs_version_name("cfs_hotel_overall_experience_en_v1", used_names=used)
        == "cfs_hotel_overall_experience_en_v3"
    )


def test_manifest_items_to_plan_filters_approved_push_only():
    manifest = {
        "batch_id": "testbatch",
        "groups": [
            {
                "group_key": "was_x_001",
                "items": [
                    {
                        "status": "approved_push",
                        "action": "survey_rewrite_push",
                        "product": "survey",
                        "label": "was_x_001_en",
                        "remote_name": "was_x_001_en",
                        "new_meta_name": "was_x_002_en",
                        "local_template_id": 10,
                        "language": "en_gb",
                        "body_before": "before",
                        "body_after": "after",
                        "delete_old_remote_name": "was_x_001_en",
                    },
                    {
                        "status": "rewritten",
                        "action": "survey_rewrite_push",
                        "product": "survey",
                        "label": "was_x_001_ar",
                        "remote_name": "was_x_001_ar",
                        "new_meta_name": "was_x_002_ar",
                        "local_template_id": 11,
                        "language": "ar",
                        "body_before": "قبل",
                        "body_after": "بعد",
                    },
                ],
            }
        ],
    }
    plan = manifest_items_to_plan(manifest, approved_only=True)
    assert len(plan) == 1
    assert plan[0].label == "was_x_001_en"
    assert plan[0].dry_preview.get("body_after") == "after"


def test_rewrite_body_for_utility_passes_deepinfra_model():
    class _FakeDb:
        pass

    captured: dict = {}

    def _fake_complete(db, **kwargs):
        captured.update(kwargs)
        result = MagicMock()
        result.assistant_text = '{"body":"Following your recent visit, how was the service?","notes":"utility"}'
        return result

    with patch(
        "app.services.survey_wa_utility_rewrite_service.OpenAIProviderService.complete",
        side_effect=_fake_complete,
    ):
        out = rewrite_body_for_utility(
            _FakeDb(),
            original_body="Would you recommend us to a friend?",
            button_labels=["Yes", "No"],
            template_name="was_test_topic_001_en",
            use_llm=True,
            llm_provider="deepinfra",
            llm_model=DEFAULT_UTILITY_LLM_MODEL,
        )
    assert "recent visit" in out.lower() or "service" in out.lower()
    assert captured.get("provider") == "deepinfra"
    assert captured.get("model") == DEFAULT_UTILITY_LLM_MODEL


def test_discover_remote_marketing_templates_filters_protected(monkeypatch):
    from app.services import survey_wa_utility_rewrite_service as svc

    def _fake_fetch(db, **kwargs):
        return [
            {"name": "was_test_001_en", "category": "MARKETING", "language": "en_GB", "status": "APPROVED"},
            {"name": "cfs_hotel_topic_en_v1", "category": "MARKETING", "language": "en_GB", "status": "APPROVED"},
            {"name": "voxbulk_interview_email_sent_v2", "category": "MARKETING", "language": "en_GB", "status": "APPROVED"},
        ]

    class _FakeSync:
        @staticmethod
        def collect_survey_mirror_templates(db):
            return []

        @staticmethod
        def _find_local_row_for_meta_live_name(local_rows, remote_name, lang):
            return None

    monkeypatch.setattr(
        "app.services.telnyx_whatsapp_template_sync_service.TelnyxWhatsappTemplateSyncService.fetch_remote_templates",
        _fake_fetch,
    )
    monkeypatch.setattr(
        "app.services.wa_template_sync_service.WaTemplateSyncService",
        _FakeSync,
    )

    class _FakePush:
        @staticmethod
        def resolve_primary_connection_profile_id(db, service_code="survey"):
            return "meta99"

        @staticmethod
        def resolve_backup_connection_profile_id(db, service_code="survey"):
            return "telnyx55"

    monkeypatch.setattr(
        "app.services.wa_template_profile_push_service.WaTemplateProfilePushService",
        _FakePush,
    )

    def _fake_summary(db, pid, service_code="survey"):
        return {
            "ok": True,
            "provider": "meta" if pid == "meta99" else "telnyx",
            "summary": {"marketing": 2},
            "profile_label": pid,
        }

    monkeypatch.setattr(
        "app.services.wa_template_sync_profile.summarize_for_connection_profile",
        _fake_summary,
    )

    overview, candidates = svc.discover_remote_marketing_templates(MagicMock())
    names = {c.get("remote_name") or c.get("name") for c in candidates}
    assert "was_test_001_en" in names
    assert "cfs_hotel_topic_en_v1" in names
    assert not any("voxbulk_interview" in str(n) for n in names)
