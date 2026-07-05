"""Immutable builder WA survey runtime — single source of truth for preview and live send."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_step_bank_service import normalize_step_role
from app.services.survey_wa_flow_constants import TELL_US_MORE_TRIGGER_ROLES

logger = logging.getLogger(__name__)
LOG_PREFIX = "[builder-runtime]"


class SurveyBuilderFlowError(ValueError):
    """Builder runtime cannot resolve or send outside the immutable template sequence."""

RUNTIME_VERSION = 1
RUNTIME_SOURCE = "order.config_json.builder_runtime"


def _welcome_start_triggers(db: Session, welcome_template_id: int) -> list[str]:
    """Button labels/ids from welcome template — valid Start actions for this survey."""
    import json

    row = db.get(TelnyxWhatsappTemplate, int(welcome_template_id))
    if row is None:
        return []
    try:
        components = json.loads(row.components_json or "[]")
    except Exception:
        components = []
    if not isinstance(components, list):
        return []
    triggers: list[str] = []
    for comp in components:
        if str(comp.get("type") or "").upper() != "BUTTONS":
            continue
        for btn in comp.get("buttons") or []:
            if not isinstance(btn, dict):
                continue
            for key in ("text", "title", "label", "button_text"):
                label = str(btn.get(key) or "").strip()
                if label and label not in triggers:
                    triggers.append(label)
            for key in ("id", "payload"):
                val = str(btn.get(key) or "").strip()
                if val and val not in triggers:
                    triggers.append(val)
    return triggers


STALE_GRAPH_KEYS = (
    "flow_snapshot",
    "flow_snapshot_json",
    "flow_definition_id",
    "flow_branches",
    "order_config_flow",
)


def compute_runtime_hash(payload: dict[str, Any]) -> str:
    """Stable hash over selected template IDs and middle order (preview == runtime proof)."""
    canonical = {
        "version": payload.get("version"),
        "welcome_template_id": payload.get("welcome_template_id"),
        "middle_template_ids": list(payload.get("middle_template_ids") or []),
        "tell_us_more_template_id": payload.get("tell_us_more_template_id"),
        "thank_you_template_id": payload.get("thank_you_template_id"),
        "selected_template_ids": list(payload.get("selected_template_ids") or []),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_builder_runtime(
    db: Session,
    *,
    industry_id: str | None,
    survey_type_id: str,
    survey_type_name: str,
    privacy_mode: str,
    welcome_template_id: int | str,
    middle_template_ids: list[int | str],
    tell_us_more_template_id: int | str | None = None,
    thank_you_template_id: int | str | None = None,
    business_name: str = "Your business",
    first_name: str = "Alex",
    allow_final_additional_feedback: bool = False,
    final_feedback_yes_no_question: str | None = None,
    final_feedback_open_text_prompt: str | None = None,
) -> dict[str, Any]:
    """Build immutable runtime payload from wizard-selected template IDs (same object preview uses)."""
    from app.services.survey_builder_flow_service import (
        build_builder_step_sequence,
        build_builder_template_ids,
    )

    from app.services.survey_wa_final_feedback_service import build_final_feedback_branch

    middles = [int(x) for x in middle_template_ids if x is not None]
    step_sequence = build_builder_step_sequence(
        db,
        middle_template_ids=middles,
        business_name=business_name,
        first_name=first_name,
        survey_type_name=str(survey_type_name or ""),
    )
    for step in step_sequence:
        step["source"] = RUNTIME_SOURCE

    welcome_id = int(welcome_template_id)
    selected_ids = build_builder_template_ids(
        welcome_template_id=welcome_id,
        middle_template_ids=middles,
        tell_us_more_template_id=tell_us_more_template_id,
        thank_you_template_id=thank_you_template_id,
    )
    selected_names: list[str] = []
    for tid in selected_ids:
        row = db.get(TelnyxWhatsappTemplate, tid)
        selected_names.append(str(row.display_name or row.name or "") if row else str(tid))

    from app.services.survey_builder_flow_service import step_sequence_has_tell_us_more_trigger

    has_tell_us_more_trigger_step = step_sequence_has_tell_us_more_trigger(step_sequence)
    tell_id = int(tell_us_more_template_id) if tell_us_more_template_id else None
    thank_id = int(thank_you_template_id) if thank_you_template_id else None
    start_triggers = _welcome_start_triggers(db, welcome_id)

    runtime: dict[str, Any] = {
        "version": RUNTIME_VERSION,
        "generated_at": datetime.utcnow().isoformat(),
        "industry_id": str(industry_id or "").strip() or None,
        "survey_type_id": str(survey_type_id),
        "survey_type_name": str(survey_type_name or ""),
        "privacy_mode": str(privacy_mode or "off"),
        "welcome_template_id": welcome_id,
        "middle_template_ids": middles,
        "tell_us_more_template_id": tell_id,
        "thank_you_template_id": thank_id,
        "selected_template_ids": selected_ids,
        "selected_template_names": selected_names,
        "start_triggers": start_triggers,
        "step_sequence": step_sequence,
        "branches": {
            "tell_us_more_on_low_rating": {
                "enabled": bool(tell_id and has_tell_us_more_trigger_step),
                "threshold": 6,
                "template_id": tell_id,
                "from_step_roles": sorted(TELL_US_MORE_TRIGGER_ROLES),
            },
            "final_additional_feedback": build_final_feedback_branch(
                enabled=allow_final_additional_feedback,
                yes_no_question=final_feedback_yes_no_question,
                open_text_prompt=final_feedback_open_text_prompt,
            ),
        },
    }
    runtime["hash"] = compute_runtime_hash(runtime)
    logger.info(
        "%s built hash=%s survey_type=%s middle_ids=%s selected_ids=%s",
        LOG_PREFIX,
        runtime["hash"],
        survey_type_id,
        middles,
        selected_ids,
    )
    return runtime


def _migrate_legacy_runtime(config: dict[str, Any]) -> dict[str, Any] | None:
    from app.services.survey_wa_final_feedback_service import build_final_feedback_branch

    seq = config.get("builder_step_sequence")
    ids = config.get("builder_template_ids")
    if not isinstance(seq, list) or not seq or not isinstance(ids, list) or not ids:
        return None
    middles = [int(q["template_id"]) for q in seq if isinstance(q, dict) and q.get("template_id")]
    from app.services.survey_builder_flow_service import step_sequence_has_tell_us_more_trigger

    legacy_has_trigger_step = step_sequence_has_tell_us_more_trigger(
        [q for q in seq if isinstance(q, dict)]
    )
    runtime: dict[str, Any] = {
        "version": RUNTIME_VERSION,
        "generated_at": None,
        "industry_id": config.get("industry_id"),
        "survey_type_id": config.get("survey_type_id"),
        "survey_type_name": config.get("survey_type_name") or "",
        "privacy_mode": config.get("privacy_mode") or "off",
        "welcome_template_id": int(config.get("wa_template_id") or config.get("welcome_template_id") or 0),
        "middle_template_ids": middles,
        "tell_us_more_template_id": int(config["tell_us_more_template_id"])
        if config.get("tell_us_more_template_id")
        else None,
        "thank_you_template_id": int(config["thank_you_template_id"])
        if config.get("thank_you_template_id")
        else None,
        "selected_template_ids": [int(x) for x in ids],
        "selected_template_names": [
            str(q.get("template_name") or q.get("display_name") or "")
            for q in seq
            if isinstance(q, dict)
        ],
        "step_sequence": [q for q in seq if isinstance(q, dict)],
        "branches": {
            "tell_us_more_on_low_rating": {
                "enabled": bool(config.get("tell_us_more_template_id") and legacy_has_trigger_step),
                "threshold": 6,
                "template_id": int(config["tell_us_more_template_id"])
                if config.get("tell_us_more_template_id")
                else None,
                "from_step_roles": sorted(TELL_US_MORE_TRIGGER_ROLES),
            },
            "final_additional_feedback": build_final_feedback_branch(
                enabled=bool(config.get("allow_final_additional_feedback")),
            ),
        },
        "migrated_from_legacy": True,
    }
    runtime["hash"] = compute_runtime_hash(runtime)
    return runtime


def load_builder_runtime(config: dict[str, Any]) -> dict[str, Any] | None:
    """THE runtime reader — preview and live send must use only this object when present."""
    if not isinstance(config, dict):
        return None
    raw = config.get("builder_runtime")
    if isinstance(raw, dict) and isinstance(raw.get("step_sequence"), list) and raw.get("selected_template_ids"):
        survey_type_name = str(raw.get("survey_type_name") or config.get("survey_type_name") or "")
        seq = sanitize_runtime_step_sequence(
            [q for q in (raw.get("step_sequence") or []) if isinstance(q, dict)],
            survey_type_name=survey_type_name,
        )
        if seq != raw.get("step_sequence"):
            patched = dict(raw)
            patched["step_sequence"] = seq
            return patched
        return raw
    migrated = _migrate_legacy_runtime(config)
    if migrated is None:
        return None
    survey_type_name = str(migrated.get("survey_type_name") or config.get("survey_type_name") or "")
    migrated["step_sequence"] = sanitize_runtime_step_sequence(
        [q for q in (migrated.get("step_sequence") or []) if isinstance(q, dict)],
        survey_type_name=survey_type_name,
    )
    return migrated


def has_builder_runtime(config: dict[str, Any]) -> bool:
    return load_builder_runtime(config) is not None


def sanitize_runtime_step_sequence(
    steps: list[dict[str, Any]],
    *,
    survey_type_name: str = "",
    campaign_title: str = "",
    campaign_goal: str = "",
) -> list[dict[str, Any]]:
    """Ensure every runtime middle step has display_name / template_name (Step 1 = survey type when blank)."""
    from app.services.survey_builder_flow_service import ensure_question_display_name

    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(steps):
        if not isinstance(raw, dict):
            continue
        out.append(
            ensure_question_display_name(
                dict(raw),
                sequence=idx,
                survey_type_name=survey_type_name,
                campaign_title=campaign_title,
                campaign_goal=campaign_goal,
            )
        )
    return out


def runtime_step_sequence(config: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = load_builder_runtime(config)
    if runtime is None:
        return []
    survey_type_name = str(
        runtime.get("survey_type_name") or (config.get("survey_type_name") if isinstance(config, dict) else "") or ""
    )
    steps = [q for q in (runtime.get("step_sequence") or []) if isinstance(q, dict)]
    return sanitize_runtime_step_sequence(steps, survey_type_name=survey_type_name)


def runtime_allowed_template_ids(config: dict[str, Any]) -> set[int]:
    runtime = load_builder_runtime(config)
    if runtime is None:
        return set()
    return {int(x) for x in (runtime.get("selected_template_ids") or [])}


def attach_builder_runtime_to_config(
    config: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """Persist runtime and sync legacy mirror fields without recomposing from survey type."""
    out = dict(config)
    out["builder_runtime"] = runtime
    out["builder_runtime_hash"] = runtime.get("hash")
    out["flow_engine"] = "linear"
    for key in STALE_GRAPH_KEYS:
        out.pop(key, None)
    seq = runtime_step_sequence({"builder_runtime": runtime})
    out["builder_step_sequence"] = seq
    out["builder_template_ids"] = list(runtime.get("selected_template_ids") or [])
    out["wa_template_id"] = runtime.get("welcome_template_id")
    out["welcome_template_id"] = runtime.get("welcome_template_id")
    out["tell_us_more_template_id"] = runtime.get("tell_us_more_template_id")
    out["thank_you_template_id"] = runtime.get("thank_you_template_id")
    ff_branch = (runtime.get("branches") or {}).get("final_additional_feedback") or {}
    out["allow_final_additional_feedback"] = bool(ff_branch.get("enabled"))
    wa = dict(out.get("whatsapp_flow") or {})
    wa["questions"] = seq
    out["whatsapp_flow"] = wa
    return out


def sanitize_order_config_for_builder(config: dict[str, Any]) -> dict[str, Any]:
    runtime = load_builder_runtime(config)
    if runtime is None:
        return dict(config) if isinstance(config, dict) else {}
    return attach_builder_runtime_to_config(dict(config), runtime)


def assert_runtime_template_send(
    db: Session,
    config: dict[str, Any],
    template_id: Any,
    *,
    context: str,
    order_id: str | None = None,
    session_id: str | None = None,
    preview_hash: str | None = None,
) -> TelnyxWhatsappTemplate:
    """Hard guard before any outbound builder message after welcome."""
    runtime = load_builder_runtime(config)
    if runtime is None:
        raise SurveyBuilderFlowError(f"builder runtime missing for {context}")

    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        msg = f"builder flow violation: missing template_id in {context} order={order_id}"
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)

    allow = runtime_allowed_template_ids(config)
    if tid not in allow:
        msg = (
            f"builder flow violation: attempted template {tid} not in selected_template_ids "
            f"{sorted(allow)} context={context} order={order_id} session={session_id}"
        )
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)

    row = db.get(TelnyxWhatsappTemplate, tid)
    if row is None:
        msg = f"Template {tid} missing (context={context})"
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)
    if not bool(row.active_for_survey):
        msg = f"Template {tid} is hidden/disabled (context={context})"
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)
    from app.services.survey_whatsapp_template_service import (
        resolve_sendable_template_row,
        template_row_must_send_as_session_text,
        template_row_needs_meta_approval,
    )

    if template_row_must_send_as_session_text(row):
        runtime_hash = str(runtime.get("hash") or "")
        hash_match = preview_hash is None or preview_hash == runtime_hash
        log_runtime_outbound(
            phase=context,
            order_id=order_id,
            session_id=session_id,
            config=config,
            runtime=runtime,
            template_id=int(row.id),
            template_name=str(row.display_name or row.name or ""),
            source=RUNTIME_SOURCE,
            hash_match=hash_match,
            preview_hash=preview_hash,
        )
        return row

    outbound = row
    if template_row_needs_meta_approval(row):
        sendable = resolve_sendable_template_row(db, row)
        if sendable is None:
            msg = f"Template {tid} missing or not APPROVED on Meta (context={context})"
            logger.error("%s %s", LOG_PREFIX, msg)
            raise SurveyBuilderFlowError(msg)
        outbound = sendable

    runtime_hash = str(runtime.get("hash") or "")
    stored_hash = str(config.get("builder_runtime_hash") or runtime_hash)
    hash_match = preview_hash is None or preview_hash == runtime_hash
    log_runtime_outbound(
        phase=context,
        order_id=order_id,
        session_id=session_id,
        config=config,
        runtime=runtime,
        template_id=int(outbound.id),
        template_name=str(outbound.display_name or outbound.name or ""),
        source=RUNTIME_SOURCE,
        hash_match=hash_match,
        preview_hash=preview_hash,
    )
    return outbound


def log_runtime_outbound(
    *,
    phase: str,
    order_id: str | None,
    session_id: str | None,
    config: dict[str, Any],
    runtime: dict[str, Any],
    template_id: int,
    template_name: str,
    source: str,
    step_index: int | None = None,
    hash_match: bool = True,
    preview_hash: str | None = None,
) -> None:
    conv = {}
    logger.info(
        "%s %s order=%s session=%s step=%s industry=%s survey_type=%s survey_type_name=%s "
        "selected_template_ids=%s template_id=%s template_name=%s source=%s runtime_hash=%s "
        "preview_hash=%s hash_match=%s payload_source=builder_step_sequence",
        LOG_PREFIX,
        phase,
        order_id,
        session_id,
        step_index,
        runtime.get("industry_id"),
        runtime.get("survey_type_id"),
        runtime.get("survey_type_name"),
        runtime.get("selected_template_ids"),
        template_id,
        template_name,
        source,
        runtime.get("hash"),
        preview_hash or config.get("builder_runtime_hash"),
        hash_match,
    )


def reject_stale_graph_session(
    db: Session,
    *,
    recipient_id: str,
    order_id: str | None,
    runtime: dict[str, Any],
) -> None:
    """Graph sessions must never drive builder runtime — invalidate contaminated session rows."""
    from app.models.survey_session import SurveySession
    from app.services.survey_session_service import SurveySessionService

    from app.services.survey_flow_constants import FLOW_MODE_GRAPH

    session = SurveySessionService.get_active_by_recipient(db, recipient_id)
    if session is None:
        return
    mode = str(session.flow_mode or "").strip().lower()
    # Linear sessions store awaiting_start metadata in flow_snapshot_json — that is not graph contamination.
    contaminated = mode in {FLOW_MODE_GRAPH, "graph"}
    if not contaminated:
        return
    now = datetime.utcnow()
    session.status = "completed"
    session.completed_at = now
    session.updated_at = now
    db.add(session)
    db.commit()
    logger.error(
        "%s graph_session_invalidated order=%s session=%s recipient=%s runtime_hash=%s",
        LOG_PREFIX,
        order_id,
        session.id,
        recipient_id,
        runtime.get("hash"),
    )


def resolve_runtime_step(
    config: dict[str, Any],
    step: int,
    *,
    order_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """1-based index into immutable runtime.step_sequence — the only builder resolver."""
    steps = runtime_step_sequence(config)
    if step < 1 or step > len(steps):
        msg = f"No runtime step {step} (len={len(steps)}) order={order_id} session={session_id}"
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)
    q = dict(steps[step - 1])
    q["source"] = RUNTIME_SOURCE
    from app.services.survey_builder_flow_service import ensure_question_display_name

    runtime = load_builder_runtime(config)
    survey_type_name = str((runtime or {}).get("survey_type_name") or config.get("survey_type_name") or "")
    return ensure_question_display_name(q, sequence=step - 1, survey_type_name=survey_type_name)


def question_from_runtime_tell_us_more(
    db: Session,
    config: dict[str, Any],
    *,
    business_name: str = "Your business",
    first_name: str = "Alex",
    order_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    runtime = load_builder_runtime(config)
    if runtime is None:
        raise SurveyBuilderFlowError("builder runtime missing for tell-us-more")
    branch = (runtime.get("branches") or {}).get("tell_us_more_on_low_rating") or {}
    if not branch.get("enabled"):
        raise SurveyBuilderFlowError("tell-us-more branch not enabled in builder runtime")
    tid = branch.get("template_id")
    row = assert_runtime_template_send(
        db,
        config,
        tid,
        context="tell_us_more_branch",
        order_id=order_id,
        session_id=session_id,
    )
    from app.services.survey_builder_flow_service import question_from_template_row

    q = question_from_template_row(
        db,
        row,
        sequence=-1,
        business_name=business_name,
        first_name=first_name,
    )
    q["node_key"] = f"builder_tell_{row.id}"
    q["step_role"] = "reason"
    q["source"] = RUNTIME_SOURCE
    from app.services.survey_builder_flow_service import as_open_text_tell_us_more_question

    return as_open_text_tell_us_more_question(q)


def runtime_tell_us_more_enabled(config: dict[str, Any]) -> bool:
    runtime = load_builder_runtime(config)
    if runtime is None:
        return False
    branch = (runtime.get("branches") or {}).get("tell_us_more_on_low_rating") or {}
    return bool(branch.get("enabled"))


def runtime_tell_us_more_configured(config: dict[str, Any]) -> bool:
    """True when a tell-us-more template is bound to this survey (even before branch enable check)."""
    runtime = load_builder_runtime(config)
    if runtime is not None:
        branch = (runtime.get("branches") or {}).get("tell_us_more_on_low_rating") or {}
        tid = runtime.get("tell_us_more_template_id") or branch.get("template_id")
        if tid:
            return True
    return bool(config.get("tell_us_more_template_id"))


def tell_us_more_blocks_vague_followup(
    config: dict[str, Any],
    conv: dict[str, Any] | None = None,
) -> bool:
    """Vague auto-followup must not run when tell-us-more is configured or pending."""
    c = conv or {}
    if c.get("tell_us_more_pending"):
        return True
    if runtime_tell_us_more_enabled(config):
        return True
    return runtime_tell_us_more_configured(config)


def hydrate_missing_tell_us_more_on_config(db: Session, config: dict[str, Any]) -> dict[str, Any]:
    """
    Repair orders created when system tell-us-more resolution failed (e.g. duplicate SurveyType rows).
    Session-text tell-us-more is always sent from the local server — never Meta HSM.
    """
    if not isinstance(config, dict):
        return {}
    if runtime_tell_us_more_enabled(config):
        return config

    from app.services.survey_builder_flow_service import step_sequence_has_tell_us_more_trigger
    from app.services.survey_system_template_service import SurveySystemTemplateService

    privacy_cfg = {
        "privacy_mode": config.get("privacy_mode"),
        "anonymous_responses": bool(config.get("anonymous_responses")),
    }
    resolved_tid = SurveySystemTemplateService.resolve_tell_us_more_template_id(db, privacy_cfg)
    if resolved_tid is None:
        return config

    runtime = load_builder_runtime(config)
    out = dict(config)
    if runtime is None:
        out["tell_us_more_template_id"] = int(resolved_tid)
        return out

    seq = [q for q in (runtime.get("step_sequence") or []) if isinstance(q, dict)]
    has_trigger_step = step_sequence_has_tell_us_more_trigger(seq)
    patched = dict(runtime)
    patched["tell_us_more_template_id"] = int(resolved_tid)
    branches = dict(patched.get("branches") or {})
    tum = dict(branches.get("tell_us_more_on_low_rating") or {})
    tum["enabled"] = bool(has_trigger_step)
    tum["template_id"] = int(resolved_tid)
    tum["from_step_roles"] = sorted(TELL_US_MORE_TRIGGER_ROLES)
    branches["tell_us_more_on_low_rating"] = tum
    patched["branches"] = branches
    return attach_builder_runtime_to_config(out, patched)


def runtime_low_rating_threshold(config: dict[str, Any]) -> int:
    runtime = load_builder_runtime(config)
    if runtime is None:
        return 6
    branch = (runtime.get("branches") or {}).get("tell_us_more_on_low_rating") or {}
    try:
        return int(branch.get("threshold") or 6)
    except (TypeError, ValueError):
        return 6
