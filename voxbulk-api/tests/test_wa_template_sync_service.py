"""Industry force-push sync — local DB to Meta."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import pytest

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_whatsapp_template_service import (
    SYNC_BRANCH_APPROVED_UPDATE,
    SurveyWhatsappTemplateService,
    VARIANT_STANDARD,
    _loads,
    _sync_content_hash,
)
from app.services.wa_template_sync_service import WaTemplateSyncService


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _seed_survey_type(db):
    SurveyTypeService.ensure_defaults(db)
    row = SurveyTypeService.get_by_slug(db, "customer_satisfaction")
    assert row is not None
    return row


def _link(db, survey_type, template, **kwargs):
    return SurveyTypeTemplateService.upsert_mapping(
        db,
        survey_type_id=survey_type.id,
        template_id=template.id,
        usable_as_standard=True,
        **kwargs,
    )


def _template(
    db,
    *,
    name: str,
    local_sync_status: str = "in_sync",
    draft_text: str = "Hello {{1}} thanks",
    remote_text: str | None = None,
) -> TelnyxWhatsappTemplate:
    remote_text = remote_text if remote_text is not None else draft_text
    components = [{"type": "BODY", "text": remote_text, "example": {"body_text": [["Alex"]]}}]
    draft = [{"type": "BODY", "text": draft_text, "example": {"body_text": [["Alex"]]}}]
    now = datetime.utcnow()
    record_id = str(uuid.uuid4())
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=record_id,
        template_id=record_id,
        name=name,
        display_name=name,
        language="en_US",
        category="UTILITY",
        status="APPROVED",
        variant_type=VARIANT_STANDARD,
        step_role="start",
        body_preview=draft_text[:40],
        components_json=json.dumps(components),
        draft_components_json=json.dumps(draft),
        example_values_json=json.dumps(["Alex"]),
        remote_content_hash=_sync_content_hash(_loads(json.dumps(components))),
        local_sync_status=local_sync_status,
        active_for_survey=True,
        created_at=now,
        updated_at=now,
        synced_at=now,
    )
    db.add(row)
    db.flush()
    return row


def test_template_counts_for_survey_type_only_includes_sendable_active():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        approved = _template(db, name="voxbulk_survey_sendable_ok")
        pending = _template(db, name="voxbulk_survey_sendable_pending", local_sync_status="local_changes")
        pending.status = "PENDING"
        disabled = _template(db, name="voxbulk_survey_sendable_disabled")
        disabled.active_for_survey = False
        _link(db, survey_type, approved, is_default_standard=True)
        _link(db, survey_type, pending)
        _link(db, survey_type, disabled)
        db.commit()

        counts = SurveyTypeTemplateService.template_counts_for_survey_type(db, survey_type.id)
        assert counts["standard"] == 1
        assert counts["anonymous"] == 0


def test_force_push_collects_in_sync_industry_templates():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        industry_id = survey_type.industry_id
        assert industry_id

        in_sync = _template(db, name="voxbulk_survey_force_in_sync", local_sync_status="in_sync")
        out_of_sync = _template(
            db,
            name="voxbulk_survey_force_out_sync",
            local_sync_status="local_changes",
            draft_text="Updated body for {{1}} thanks",
            remote_text="Original body for {{1}} thanks",
        )
        _link(db, survey_type, in_sync, is_default_standard=True)
        _link(db, survey_type, out_of_sync)
        db.commit()

        changed_only = WaTemplateSyncService._collect_push_work(db, industry_id=industry_id)
        all_rows, skipped = WaTemplateSyncService._collect_all_industry_templates(db, industry_id)
        assert len(changed_only) == 1
        assert changed_only[0].id == out_of_sync.id
        assert len(all_rows) == 2
        assert skipped == []


def test_push_changed_batch_force_push_pagination(monkeypatch):
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        industry_id = survey_type.industry_id
        work_rows = []
        for i in range(12):
            row = _template(db, name=f"voxbulk_survey_force_batch_{i}")
            _link(db, survey_type, row)
            work_rows.append(row)
        db.commit()

        calls: list[int] = []

        def fake_push(db, row, **kwargs):
            calls.append(int(row.id))
            return {
                "ok": True,
                "sync_branch": "approved_update",
                "message": "patched",
            }

        monkeypatch.setattr(
            "app.services.wa_template_sync_service.SurveyWhatsappTemplateService.push_to_telnyx",
            fake_push,
        )
        monkeypatch.setattr(
            "app.services.wa_template_sync_service._prefetch_remote_templates_for_push",
            lambda db: [],
        )
        monkeypatch.setattr(
            WaTemplateSyncService,
            "_collect_all_industry_templates",
            lambda db, iid: (work_rows, []),
        )

        first = WaTemplateSyncService.push_changed_batch(
            db,
            industry_id=industry_id,
            offset=0,
            limit=10,
            force_push=True,
        )
        assert first["total"] == 12
        assert first["has_more"] is True
        assert len(calls) == 10

        second = WaTemplateSyncService.push_changed_batch(
            db,
            industry_id=industry_id,
            offset=first["next_offset"],
            limit=10,
            force_push=True,
        )

        assert second["has_more"] is False
        assert len(calls) == 12
        assert first["force_push"] is True


def test_force_push_in_sync_approved_uses_patch(monkeypatch):
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        body = [{"type": "BODY", "text": "Same approved body for {{1}} thanks", "example": {"body_text": [["Alex"]]}}]
        row = _template(db, name="voxbulk_survey_force_in_sync_patch", local_sync_status="in_sync")
        row.draft_components_json = json.dumps(body)
        row.components_json = json.dumps(body)
        row.remote_content_hash = _sync_content_hash(body)
        _link(db, survey_type, row, is_default_standard=True)
        db.commit()

        captured: dict[str, Any] = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "data": {
                        "id": row.telnyx_record_id,
                        "template_id": row.template_id,
                        "status": "PENDING",
                        "category": "UTILITY",
                        "components": captured["patch_payload"]["components"],
                    }
                }

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, headers=None, json=None):
                raise AssertionError("POST must not run for in-sync force push — use PATCH")

            def patch(self, url, headers=None, json=None):
                captured["patch_payload"] = json
                return FakeResponse()

        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.httpx.Client",
            lambda *a, **k: FakeClient(),
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
            lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
        )

        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row, force_approved_update=True)
        assert result["ok"] is True
        assert result["sync_branch"] == SYNC_BRANCH_APPROVED_UPDATE
        assert result["telnyx_request_mode"] == "patch_template"
        assert captured["patch_payload"]["category"] == "UTILITY"


def test_pull_statuses_never_overwrites_local_draft_body(monkeypatch):
    remote = [
        {
            "id": "meta-remote-99",
            "template_id": "888",
            "name": "voxbulk_survey_test_pull_standard",
            "language": "en_GB",
            "category": "UTILITY",
            "status": "APPROVED",
            "components": [{"type": "BODY", "text": "Old Meta body text"}],
        }
    ]

    monkeypatch.setattr(
        "app.services.telnyx_whatsapp_template_sync_service.TelnyxWhatsappTemplateSyncService.fetch_remote_templates",
        lambda db: remote,
    )

    with get_sessionmaker()() as db:
        row = TelnyxWhatsappTemplate(
            telnyx_record_id="meta-remote-99",
            template_id="888",
            name="voxbulk_survey_test_pull_standard",
            display_name="Pull test",
            language="en_GB",
            category="UTILITY",
            status="PENDING",
            variant_type=VARIANT_STANDARD,
            body_preview="My new local body",
            components_json=json.dumps([{"type": "BODY", "text": "Old Meta body text"}]),
            draft_components_json=json.dumps([{"type": "BODY", "text": "My new local body"}]),
            local_sync_status="local_changes",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        result = WaTemplateSyncService.pull_statuses(db, row_ids=[int(row.id)])
        assert result["ok"] is True
        db.refresh(row)
        assert row.status == "APPROVED"
        draft = _loads(row.draft_components_json)
        assert draft[0]["text"] == "My new local body"
        assert row.body_preview == "My new local body"


def test_pull_statuses_reconciles_stale_remote_hash():
    """Refresh-only must not flip in-sync approved rows to local_changes (hash algo mismatch)."""
    from app.services.survey_whatsapp_template_service import _refresh_local_sync_status
    from app.services.wa_template_sync_service import _apply_live_meta_to_row

    body_text = "Approved body for {{1}} thanks"
    components = [{"type": "BODY", "text": body_text, "example": {"body_text": [["Alex"]]}}]
    with get_sessionmaker()() as db:
        row = _template(
            db,
            name="voxbulk_survey_hash_reconcile",
            local_sync_status="in_sync",
            draft_text=body_text,
            remote_text=body_text,
        )
        row.remote_content_hash = "legacywronghash000000000000000000000000000000000000000000000000"
        db.commit()
        db.refresh(row)
        assert _refresh_local_sync_status(row) in {"local_changes", "remote_changed"}

        live = {
            "id": row.telnyx_record_id,
            "status": "APPROVED",
            "category": "UTILITY",
            "components": components,
        }
        _apply_live_meta_to_row(db, row, live, mirror_remote_body=True)
        db.commit()
        db.refresh(row)
        assert row.local_sync_status == "in_sync"
        assert row.remote_content_hash == _sync_content_hash(components)
