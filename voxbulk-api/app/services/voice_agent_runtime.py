from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_services import SERVICE_APPOINTMENTS, SERVICE_INTERVIEW, SERVICE_SURVEY
from app.models.agent import AgentDefinition
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.voice_agent_platform_settings import DEFAULT_OPENING_DISCLOSURE, VoiceAgentPlatformSettings
from app.services.survey_dispatch_service import _first_name, _personalize

logger = logging.getLogger(__name__)

_INVALID_SPOKEN_ORG_NAMES = frozenset(
    {
        "",
        "company",
        "the company",
        "your company",
        "organisation",
        "the organisation",
        "organization",
        "the organization",
        "business",
        "your business",
        "client",
        "the client",
        "employer",
        "the employer",
    }
)

DEFAULT_INTERVIEW_OPENING_FALLBACK = (
    "Hello {first_name}, this is {agent_name} calling on behalf of {company_name} about the {role} role. "
    "This call is recorded for quality and assessment purposes. "
    "Can you hear me clearly, and is now still a good time to continue?"
)

DEFAULT_SURVEY_LOW_RATING_THRESHOLD = 3


def survey_anonymous_enabled(config: dict[str, Any]) -> bool:
    from app.services.wa_template_privacy import PRIVACY_MODE_ON, normalize_privacy_mode

    if config.get("anonymous_responses") in (True, "true", "1", 1):
        return True
    return normalize_privacy_mode(config.get("privacy_mode")) == PRIVACY_MODE_ON


def is_ai_call_survey_config(config: dict[str, Any]) -> bool:
    from app.services.platform_catalog_service import PlatformCatalogService

    try:
        return PlatformCatalogService.resolve_survey_channel(config) == "ai_call"
    except Exception:
        delivery = str(config.get("delivery") or config.get("survey_channel") or "").strip().lower()
        channels = config.get("channels") if isinstance(config.get("channels"), list) else []
        if any(str(c).lower() == "whatsapp" for c in channels):
            return False
        return delivery in {"ai_call", "call", "phone"} or any(str(c).lower() == "ai_call" for c in channels)


def survey_low_rating_threshold(config: dict[str, Any]) -> int:
    from app.services.survey_builder_runtime_service import load_builder_runtime, runtime_low_rating_threshold

    if load_builder_runtime(config) is not None:
        return runtime_low_rating_threshold(config)
    return DEFAULT_SURVEY_LOW_RATING_THRESHOLD


def build_survey_call_negative_followup_rule(config: dict[str, Any]) -> str:
    if not is_ai_call_survey_config(config):
        return ""
    threshold = survey_low_rating_threshold(config)
    return (
        f"After any rating or satisfaction question, if the answer is low (score {threshold} or below on a "
        "5-point scale, or clearly negative such as \"bad\", \"poor\", or \"not happy\"), politely ask one "
        'brief follow-up: "Can I ask what led to that rating?" Listen to the reason, acknowledge briefly, '
        "then continue with the remaining questions or closing. Do not argue or sell."
    )


def _survey_interrupt_behavior_rules(*, anonymous: bool) -> list[str]:
    rules = [
        "If the recipient interrupts during the opening disclosure, pause and repeat the full opening "
        "disclosure verbatim, including that the call is recorded, before continuing.",
        "If interrupted during the INTRO or a survey question, repeat that step clearly from the start.",
        "Do not proceed to survey questions until the callee has heard the opening disclosure "
        "(including the recording notice).",
    ]
    if anonymous:
        rules.append(
            "After the INTRO, mention once that responses are anonymous and will not be linked to the "
            "individual in customer reports."
        )
    return rules

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
    if service_key == SERVICE_APPOINTMENTS:
        return str(agent.service_appointment_role or "").strip()
    return ""


def disclosure_mandatory(
    platform: VoiceAgentPlatformSettings,
    agent: AgentDefinition | None,
) -> bool:
    """Opening disclosure must be included when enabled for the service."""
    if not platform.disclosure_mandatory:
        return False
    if agent is not None and not agent.disclosure_mandatory:
        return False
    return True


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
    if agent is not None and service_key == SERVICE_APPOINTMENTS and not agent.disclosure_for_appointment:
        return False
    return True


def is_invalid_spoken_company_name(name: str | None) -> bool:
    return str(name or "").strip().lower() in _INVALID_SPOKEN_ORG_NAMES


def resolve_voice_call_company_name(
    db: Session,
    *,
    config: dict[str, Any],
    org_id: str | None = None,
    order: ServiceOrder | None = None,
) -> str:
    """Resolve the spoken hiring organisation name — never return the literal word 'company'."""
    resolved_org_id = org_id or (order.org_id if order else None)
    candidates: list[str] = []
    if resolved_org_id:
        try:
            from app.services.recovery_service import OrganisationService

            org = OrganisationService.get_org(db, resolved_org_id)
            if org and str(org.name or "").strip():
                candidates.append(str(org.name).strip())
        except Exception:
            pass
    for key in ("company_name", "client_name", "organisation_name", "clinic_name"):
        val = str(config.get(key) or "").strip()
        if val:
            candidates.append(val)
    for name in candidates:
        cleaned = name.strip()
        low = cleaned.lower()
        if not cleaned or low in _INVALID_SPOKEN_ORG_NAMES:
            continue
        if "voxbulk" in low or "retover" in low:
            continue
        return cleaned
    return "the hiring team"


def enrich_voice_call_config(
    db: Session,
    *,
    config: dict[str, Any],
    org_id: str | None = None,
    order: ServiceOrder | None = None,
) -> dict[str, Any]:
    """Ensure live-call config carries a real company name and role before prompt assembly."""
    out = dict(config)
    company = resolve_voice_call_company_name(db, config=out, org_id=org_id, order=order)
    out["company_name"] = company
    out["organisation_name"] = company
    role = str(out.get("role") or out.get("goal") or out.get("position") or "").strip()
    if not role and order is not None:
        role = str(order.title or "").strip()
    out["role"] = role or "this role"
    return out


def substitute_voice_placeholders(
    text: str,
    *,
    company_name: str,
    organiser_name: str = "",
    agent_name: str = "",
    role: str = "",
    first_name: str = "",
) -> str:
    """Replace all runtime voice placeholders used in agent templates, KB, and scripts."""
    organiser = str(organiser_name or agent_name or company_name).strip()
    agent = str(agent_name or organiser or "your AI assistant").strip()
    role_line = str(role or "this role").strip()
    first = str(first_name or "there").strip() or "there"
    out = _personalize(
        str(text or ""),
        first_name=first,
        org_name=company_name,
        organiser=organiser,
    )
    mapping = {
        "company_name": company_name,
        "agent_name": agent,
        "role": role_line,
        "organiser_name": organiser,
        "position": role_line,
        "goal": role_line,
    }
    for key, value in mapping.items():
        if value:
            out = out.replace(f"{{{key}}}", value)
    return out.strip()


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

    mandatory = disclosure_mandatory(platform, agent)
    company_name = resolve_voice_call_company_name(db, config=config, org_id=org_id)
    organiser_name = str(
        config.get("organiser_name")
        or config.get("survey_organiser_name")
        or config.get("client_name")
        or company_name
    ).strip()
    agent_name = str((agent.voice_label if agent else None) or (agent.name if agent else None) or "your AI assistant").strip()
    role = str(config.get("role") or config.get("goal") or config.get("position") or "this role").strip()

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

    if mandatory and not template.strip():
        template = DEFAULT_OPENING_DISCLOSURE

    rendered = substitute_voice_placeholders(
        template,
        company_name=company_name,
        organiser_name=organiser_name,
        agent_name=agent_name,
        role=role,
        first_name="",
    )
    if mandatory and not rendered.strip():
        rendered = substitute_voice_placeholders(
            DEFAULT_OPENING_DISCLOSURE,
            company_name=company_name,
            organiser_name=organiser_name,
            agent_name=agent_name,
            role=role,
            first_name="",
        )
    if service_key == SERVICE_INTERVIEW and "record" not in rendered.lower():
        rendered = (
            f"{rendered} This call is recorded for quality and assessment purposes. "
            "Can you hear me clearly, and is now still a good time to continue?"
        ).strip()
    elif service_key == SERVICE_INTERVIEW and "good time" not in rendered.lower() and "hear me" not in rendered.lower():
        rendered = f"{rendered} Can you hear me clearly, and is now still a good time to continue?".strip()
    elif service_key == SERVICE_SURVEY and mandatory and "record" not in rendered.lower():
        rendered = f"{rendered} This call is recorded for quality purposes.".strip()
    elif service_key == SERVICE_APPOINTMENTS and mandatory and "record" not in rendered.lower():
        rendered = f"{rendered} This call is recorded for quality purposes.".strip()
    return rendered


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
    platform = _platform_settings(db)
    mandatory = disclosure_mandatory(platform, agent)
    if layers.opening_disclosure:
        mandatory_note = (
            " This section is mandatory — do not omit or shorten it."
            if mandatory
            else ""
        )
        parts.append(
            "Opening disclosure (spoken first on the phone call as a separate greeting — "
            "put this verbatim under OPENING DISCLOSURE in script_text, do NOT repeat in INTRO"
            + mandatory_note
            + "):\n"
            + layers.opening_disclosure
        )
    elif mandatory and disclosure_enabled(platform, agent, service_key=service_key):
        parts.append(
            "Opening disclosure is mandatory. Include an OPENING DISCLOSURE section using the platform default wording."
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
        if is_ai_call_survey_config(config):
            if survey_anonymous_enabled(config):
                parts.append(
                    "This survey uses anonymous responses — mention once after INTRO that answers are not "
                    "linked to individuals in reports."
                )
            parts.append(
                "For rating questions: if the respondent gives a low score or clearly negative answer, "
                'include a polite follow-up such as "Can I ask what led to that rating?" before continuing.'
            )
    elif service_key == SERVICE_INTERVIEW:
        parts.append(
            "Interview scripts must use sections in this order inside script_text:\n"
            "OPENING DISCLOSURE\n...\nINTRO\n...\nQUESTIONS\n1. ...\nCLOSING\n...\n"
            "The first TWO questions must reference the candidate CV (experience, achievement, or gap). "
            "Remaining questions must come from the role and screening criteria. "
            "This is a job interview — never call it a survey."
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
    config = enrich_voice_call_config(db, config=config, org_id=org_id, order=order)
    layers = build_voice_runtime_layers(db, agent=agent, config=config, service_key=service_key, org_id=org_id)

    company_name = resolve_voice_call_company_name(db, config=config, org_id=org_id, order=order)
    organiser = str(
        config.get("organiser_name")
        or config.get("survey_organiser_name")
        or config.get("client_name")
        or company_name
    ).strip()
    agent_name = _agent_name(agent)
    first = _first_name(recipient.name if recipient else "")
    goal = str(config.get("goal") or config.get("role") or "").strip()
    role = str(config.get("role") or goal or "this role").strip()
    criteria = str(config.get("screening_criteria") or config.get("criteria") or "").strip()
    script = str(config.get("approved_script") or config.get("generated_script_draft") or "").strip()
    survey_prompt = str(config.get("survey_runtime_prompt") or script).strip()
    placeholder_kwargs = {
        "company_name": company_name,
        "organiser_name": organiser,
        "agent_name": agent_name,
        "role": role,
        "first_name": first,
    }
    cv_snippet = ""
    if recipient is not None:
        cv_snippet = str(recipient.cv_text or "").strip()[:2500]
        if not cv_snippet and recipient.cv_parsed_json:
            try:
                import json

                parsed = json.loads(recipient.cv_parsed_json or "{}")
                if isinstance(parsed, dict):
                    cv_snippet = str(parsed.get("summary") or parsed.get("raw_text") or "")[:2500]
            except Exception:
                pass

    parts: list[str] = []
    if layers.compliance:
        parts.append(substitute_voice_placeholders(layers.compliance, **placeholder_kwargs))
    if layers.base_role:
        parts.append(substitute_voice_placeholders(layers.base_role, **placeholder_kwargs))
    if layers.service_role:
        parts.append(substitute_voice_placeholders(layers.service_role, **placeholder_kwargs))
    if layers.call_workflow:
        parts.append(
            "Call workflow (follow exactly after opening):\n"
            + substitute_voice_placeholders(layers.call_workflow, **placeholder_kwargs)
        )
    if layers.kb_context:
        parts.append(
            "Reference knowledge:\n" + substitute_voice_placeholders(layers.kb_context, **placeholder_kwargs)
        )

    parts.append(f"Organisation name (always use this exact name on the call): {company_name}")
    if service_key == SERVICE_SURVEY:
        parts.append(f"Survey organiser: {organiser}")
        parts.append(f"Contact first name: {first}")
        if goal:
            parts.append(f"Survey goal: {goal}")
        if survey_anonymous_enabled(config):
            parts.append(
                "This is an anonymous survey. After the INTRO, mention once that answers are aggregated "
                "without identifying individuals in customer reports."
            )
    elif service_key == SERVICE_APPOINTMENTS:
        parts.append(f"Contact first name: {first}")
        appt_dt = str(config.get("appointment_datetime") or "").strip()
        if appt_dt:
            parts.append(f"Appointment date and time: {appt_dt}")
        loc = str(config.get("location") or "").strip()
        if loc:
            parts.append(f"Location: {loc}")
        branch = str(config.get("branch") or "").strip()
        if branch:
            parts.append(f"Branch: {branch}")
        svc = str(config.get("service_type") or "").strip()
        if svc:
            parts.append(f"Service: {svc}")
        parts.append(
            f"When introducing yourself, say you are calling from {company_name}. "
            "Confirm identity, then confirm or help reschedule/cancel the appointment."
        )
    else:
        parts.append(f"Calling on behalf of: {organiser}")
        parts.append(f"Candidate first name: {first}")
        if goal:
            parts.append(f"Role / position: {role}")
        if criteria:
            parts.append(f"Screening criteria:\n{criteria}")
        if cv_snippet:
            parts.append(f"Candidate CV summary (use for the first two questions):\n{cv_snippet}")
        parts.append(
            "This is a job interview screening call — NOT a survey. Ask the approved interview questions in order. "
            f"When introducing yourself, say you are calling on behalf of {company_name}. "
            "Never say the generic word 'company' without the actual organisation name."
        )

    if layers.campaign_system_prompt:
        parts.append(
            "Campaign notes:\n"
            + substitute_voice_placeholders(layers.campaign_system_prompt, **placeholder_kwargs)
        )

    if survey_prompt:
        label = "Approved survey script" if service_key == SERVICE_SURVEY else "Approved interview script"
        parts.append(
            f"{label} (follow this structure):\n"
            + substitute_voice_placeholders(survey_prompt, **placeholder_kwargs)
        )

    platform = _platform_settings(db)
    mandatory = disclosure_mandatory(platform, agent)
    question_label = "survey questions" if service_key == SERVICE_SURVEY else "confirmation steps" if service_key == SERVICE_APPOINTMENTS else "interview questions"
    if layers.opening_disclosure:
        parts.append(
            "The opening disclosure has already been spoken to the recipient as the call greeting. "
            "Do NOT repeat the disclosure. Continue with the INTRO section from the approved script "
            f"(availability check / call workflow), then the {question_label}."
        )
    elif mandatory and disclosure_enabled(platform, agent, service_key=service_key):
        parts.append(
            "Opening disclosure is mandatory for this agent. If it was not spoken yet, deliver it verbatim "
            "before continuing with the INTRO section."
        )
    else:
        parts.append(
            "Begin with the INTRO section from the approved script, including any availability check from the call workflow."
        )

    behavior: list[str] = []
    if layers.interruption_notes:
        behavior.append(layers.interruption_notes)
    if service_key == SERVICE_SURVEY and is_ai_call_survey_config(config):
        behavior.extend(_survey_interrupt_behavior_rules(anonymous=survey_anonymous_enabled(config)))
        followup = build_survey_call_negative_followup_rule(config)
        if followup:
            behavior.append(followup)
    else:
        behavior.append(
            "If the recipient interrupts before you finish the opening, pause and repeat the current step clearly from the start."
        )
    if service_key == SERVICE_INTERVIEW:
        behavior.append(
            "Do not continue to interview questions until the callee confirms they heard the introduction "
            "and that now is still a good time."
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
    order: ServiceOrder | None = None,
) -> str:
    config = enrich_voice_call_config(db, config=config, org_id=org_id, order=order)
    company_name = resolve_voice_call_company_name(db, config=config, org_id=org_id, order=order)
    organiser_name = str(
        config.get("organiser_name")
        or config.get("survey_organiser_name")
        or config.get("client_name")
        or company_name
    ).strip()
    agent_name = _agent_name(agent)
    first = _first_name(recipient_name)
    role = str(config.get("role") or config.get("goal") or "this role").strip()
    placeholder_kwargs = {
        "company_name": company_name,
        "organiser_name": organiser_name,
        "agent_name": agent_name,
        "role": role,
        "first_name": first,
    }

    disclosure = resolve_opening_disclosure_template(
        db, agent=agent, config=config, service_key=service_key, org_id=org_id
    )
    if disclosure:
        greeting = substitute_voice_placeholders(disclosure, **placeholder_kwargs)
        if "{first_name}" in greeting:
            greeting = substitute_voice_placeholders(greeting, **placeholder_kwargs)
        return greeting

    if service_key == SERVICE_SURVEY:
        anonymous = survey_anonymous_enabled(config)
        anon_clause = (
            " This is an anonymous survey — your answers will not be linked to you in reports."
            if anonymous
            else ""
        )
        return (
            f"Hi {first}, this is {agent_name}, an AI assistant calling from {company_name} "
            f"for a short survey.{anon_clause} This call is recorded for quality."
        )
    if service_key == SERVICE_APPOINTMENTS:
        appt_dt = str(config.get("appointment_datetime") or "your upcoming appointment").strip()
        return (
            f"Hello {first}, this is {agent_name} calling from {company_name} "
            f"about your appointment on {appt_dt}. This call is recorded for quality. "
            f"Am I speaking with {first}?"
        )
    return substitute_voice_placeholders(DEFAULT_INTERVIEW_OPENING_FALLBACK, **placeholder_kwargs)


def log_voice_call_prompt(
    *,
    service_key: str,
    order_id: str | None,
    recipient_id: str | None,
    company_name: str,
    greeting: str,
    instructions: str,
) -> None:
    logger.info(
        "voice_call_prompt_built",
        extra={
            "service_key": service_key,
            "order_id": order_id,
            "recipient_id": recipient_id,
            "company_name": company_name,
            "greeting": greeting[:800],
            "instructions_preview": instructions[:1200],
        },
    )


def _org_name(config: dict[str, Any]) -> str:
    company = str(config.get("company_name") or "").strip()
    if company and not is_invalid_spoken_company_name(company):
        return company
    org = str(config.get("organisation_name") or config.get("clinic_name") or config.get("client_name") or "").strip()
    if org and not is_invalid_spoken_company_name(org):
        return org
    return "the hiring team"


def _agent_name(agent: AgentDefinition | None) -> str:
    if agent is None:
        return "your AI assistant"
    return str(agent.voice_label or agent.name or "your AI assistant").strip()
