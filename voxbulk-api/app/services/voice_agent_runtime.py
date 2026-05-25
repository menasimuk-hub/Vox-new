from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_services import SERVICE_INTERVIEW, SERVICE_SURVEY
from app.models.agent import AgentDefinition
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.voice_agent_platform_settings import DEFAULT_OPENING_DISCLOSURE, VoiceAgentPlatformSettings
from app.services.survey_dispatch_service import _first_name, _personalize


def _platform_settings(db: Session) -> VoiceAgentPlatformSettings:
    from app.services.survey_voice_agent_service import get_platform_voice_settings

    return get_platform_voice_settings(db)


@dataclass
class VoiceRuntimeLayers:
    compliance: str
    base_role: str
    service_role: str
    call_workflow: str
    opening_disclosure: str
    kb_context: str
    interruption_notes: str
    opt_out_notes: str
    retry_notes: str
    voicemail_notes: str
    campaign_system_prompt: str


def _service_role(agent: AgentDefinition | None, service_key: str) -> str:
    if agent is None:
        return ""
    if service_key == SERVICE_SURVEY:
        return str(agent.service_survey_role or "").strip()
    if service_key == SERVICE_INTERVIEW:
        return str(agent.service_interview_role or "").strip()
    return ""


def disclosure_enabled(
    platform: VoiceAgentPlatformSettings,
    agent: AgentDefinition | None,
    *,
    service_key: str,
) -> bool:
    if service_key == SERVICE_SURVEY and not platform.disclosure_for_survey:
        return False
    if service_key == SERVICE_INTERVIEW and not platform.disclosure_for_interview:
        return False
    if agent is not None and service_key == SERVICE_SURVEY and not agent.disclosure_for_survey:
        return False
    if agent is not None and service_key == SERVICE_INTERVIEW and not agent.disclosure_for_interview:
        return False
    return True


def resolve_opening_disclosure_template(
    db: Session,
    *,
    agent: AgentDefinition | None,
    config: dict[str, Any],
    service_key: str = SERVICE_SURVEY,
    org_id: str | None = None,
) -> str:
    platform = _platform_settings(db)
    if not disclosure_enabled(platform, agent, service_key=service_key):
        return ""

    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "the organisation").strip()
    agent_name = str((agent.voice_label if agent else None) or (agent.name if agent else None) or "your AI assistant").strip()

    org_template = ""
    if org_id:
        from app.models.organisation_ai_config import OrganisationComplianceConfig

        compliance = db.execute(
            select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id)
        ).scalar_one_or_none()
        if compliance and str(compliance.ai_disclosure_wording or "").strip():
            org_template = str(compliance.ai_disclosure_wording).strip()

    template = ""
    if agent and str(agent.opening_disclosure_template or "").strip():
        template = str(agent.opening_disclosure_template).strip()
    elif org_template:
        template = org_template
    elif platform.opening_disclosure_template:
        template = str(platform.opening_disclosure_template).strip()
    else:
        template = DEFAULT_OPENING_DISCLOSURE

    rendered = _personalize(template, first_name="", org_name=org_name, organiser=agent_name)
    return rendered.replace("{agent_name}", agent_name).replace("{company_name}", org_name)


def build_voice_runtime_layers(
    db: Session,
    *,
    agent: AgentDefinition | None,
    config: dict[str, Any],
    service_key: str,
    org_id: str | None = None,
) -> VoiceRuntimeLayers:
    platform = _platform_settings(db)
    base = str((agent.base_role if agent else None) or (agent.system_prompt if agent else "") or "").strip()
    service_role = _service_role(agent, service_key)
    campaign_prompt = str(config.get("system_prompt") or "").strip()

    opt_out = ""
    if agent and str(agent.opt_out_policy_notes or "").strip():
        opt_out = str(agent.opt_out_policy_notes).strip()
    elif org_id:
        from app.models.organisation_ai_config import OrganisationComplianceConfig

        compliance = db.execute(
            select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id)
        ).scalar_one_or_none()
        if compliance and str(compliance.opt_out_wording or "").strip():
            opt_out = str(compliance.opt_out_wording).strip()

    return VoiceRuntimeLayers(
        compliance=str(platform.global_compliance_role or "").strip(),
        base_role=base,
        service_role=service_role,
        call_workflow=str(agent.call_workflow or "").strip() if agent else "",
        opening_disclosure=resolve_opening_disclosure_template(
            db, agent=agent, config=config, service_key=service_key, org_id=org_id
        ),
        kb_context=str(agent.kb_context or "").strip() if agent else "",
        interruption_notes=str(agent.interruption_behavior_notes or "").strip() if agent else "",
        opt_out_notes=opt_out,
        retry_notes=str(agent.retry_policy_notes or "").strip() if agent else "",
        voicemail_notes=str(agent.voicemail_behavior or "").strip() if agent else "",
        campaign_system_prompt=campaign_prompt,
    )


def build_script_generation_agent_block(
    db: Session,
    *,
    agent: AgentDefinition | None,
    config: dict[str, Any],
    service_key: str,
    org_id: str | None = None,
) -> str:
    """Agent + platform rules injected into dashboard script generation."""
    layers = build_voice_runtime_layers(db, agent=agent, config=config, service_key=service_key, org_id=org_id)
    parts: list[str] = ["## Agent configuration (must follow on calls and in generated script)"]

    if layers.compliance:
        parts.append(f"Platform compliance:\n{layers.compliance}")
    if layers.base_role:
        parts.append(f"Agent base role:\n{layers.base_role}")
    if layers.service_role:
        parts.append(f"Service role:\n{layers.service_role}")
    if layers.call_workflow:
        parts.append(
            "Call workflow (include in script INTRO — e.g. ask if they have time now before questions):\n"
            + layers.call_workflow
        )
    if layers.opening_disclosure:
        parts.append(
            "Opening disclosure (spoken first on the phone call as a separate greeting — "
            "put this verbatim under OPENING DISCLOSURE in script_text, do NOT repeat in INTRO):\n"
            + layers.opening_disclosure
        )
    if layers.kb_context:
        parts.append(f"Reference knowledge:\n{layers.kb_context}")
    if layers.interruption_notes:
        parts.append(f"Interruption handling:\n{layers.interruption_notes}")
    if layers.opt_out_notes:
        parts.append(f"Opt-out policy:\n{layers.opt_out_notes}")
    if layers.campaign_system_prompt:
        parts.append(f"Campaign notes:\n{layers.campaign_system_prompt}")

    if service_key == SERVICE_SURVEY:
        parts.append(
            "Survey scripts must use sections in this order inside script_text:\n"
            "OPENING DISCLOSURE\n...\nINTRO\n...\nQUESTIONS\n1. ...\nCLOSING\n...\n"
            "INTRO must follow the call workflow (availability check) and must NOT repeat the disclosure."
        )
    return "\n\n".join(parts)


def build_service_runtime_instructions(
    db: Session,
    *,
    order: ServiceOrder | None,
    config: dict[str, Any],
    recipient: ServiceOrderRecipient | None,
    agent: AgentDefinition | None,
    service_key: str = SERVICE_SURVEY,
) -> str:
    org_id = order.org_id if order else None
    layers = build_voice_runtime_layers(db, agent=agent, config=config, service_key=service_key, org_id=org_id)

    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "the organisation").strip()
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
    first = _first_name(recipient.name if recipient else "")
    goal = str(config.get("goal") or config.get("role") or "").strip()
    script = str(config.get("approved_script") or config.get("generated_script_draft") or "").strip()
    survey_prompt = str(config.get("survey_runtime_prompt") or script).strip()

    parts: list[str] = []
    if layers.compliance:
        parts.append(layers.compliance)
    if layers.base_role:
        parts.append(layers.base_role)
    if layers.service_role:
        parts.append(layers.service_role)
    if layers.call_workflow:
        parts.append("Call workflow (follow exactly after opening):\n" + layers.call_workflow)
    if layers.kb_context:
        parts.append("Reference knowledge:\n" + layers.kb_context)

    parts.append(f"Organisation name: {org_name}")
    if service_key == SERVICE_SURVEY:
        parts.append(f"Survey organiser: {organiser}")
        parts.append(f"Contact first name: {first}")
        if goal:
            parts.append(f"Survey goal: {goal}")
        parts.append(
            "This is an anonymous survey. Answers are aggregated without identifying individuals in customer reports."
        )
    elif goal:
        parts.append(f"Role / goal: {goal}")

    if layers.campaign_system_prompt:
        parts.append("Campaign notes:\n" + layers.campaign_system_prompt)

    if survey_prompt:
        label = "Approved survey script" if service_key == SERVICE_SURVEY else "Approved script"
        parts.append(
            f"{label} (follow this structure):\n"
            + _personalize(survey_prompt, first_name=first, org_name=org_name, organiser=organiser)
        )

    if layers.opening_disclosure:
        parts.append(
            "The opening disclosure has already been spoken to the recipient as the call greeting. "
            "Do NOT repeat the disclosure. Continue with the INTRO section from the approved script "
            "(availability check / call workflow), then the survey questions."
        )
    else:
        parts.append(
            "Begin with the INTRO section from the approved script, including any availability check from the call workflow."
        )

    behavior: list[str] = []
    if layers.interruption_notes:
        behavior.append(layers.interruption_notes)
    behavior.append(
        "If the recipient interrupts before you finish the opening, pause and repeat the current step clearly from the start."
    )
    if layers.opt_out_notes:
        behavior.append(layers.opt_out_notes)
    else:
        behavior.append(
            "If the recipient asks to be removed, stop calling, or opts out, acknowledge politely, end the call, "
            "and do not continue."
        )
    if layers.retry_notes:
        behavior.append(f"Retry policy notes: {layers.retry_notes}")
    if layers.voicemail_notes:
        behavior.append(f"Voicemail behavior: {layers.voicemail_notes}")

    parts.append("Behavior rules:\n" + "\n".join(f"- {line}" for line in behavior if line))
    return "\n\n".join(parts)


def build_service_opening_greeting(
    db: Session,
    *,
    agent: AgentDefinition | None,
    config: dict[str, Any],
    recipient_name: str,
    service_key: str = SERVICE_SURVEY,
    org_id: str | None = None,
) -> str:
    disclosure = resolve_opening_disclosure_template(
        db, agent=agent, config=config, service_key=service_key, org_id=org_id
    )
    if disclosure:
        first = _first_name(recipient_name)
        if first and "{first_name}" in disclosure.lower():
            return _personalize(disclosure, first_name=first, org_name=_org_name(config), organiser=_agent_name(agent))
        return disclosure

    org_name = _org_name(config)
    first = _first_name(recipient_name)
    agent_name = _agent_name(agent)
    if service_key == SERVICE_SURVEY:
        return (
            f"Hi {first}, this is {agent_name}, an AI assistant calling from {org_name} "
            f"for a short anonymous survey. Your answers are confidential. This call may be recorded for quality."
        )
    return f"Hi {first}, this is {agent_name} calling from {org_name}."


def _org_name(config: dict[str, Any]) -> str:
    return str(config.get("organisation_name") or config.get("clinic_name") or "the organisation").strip()


def _agent_name(agent: AgentDefinition | None) -> str:
    if agent is None:
        return "your AI assistant"
    return str(agent.voice_label or agent.name or "your AI assistant").strip()
