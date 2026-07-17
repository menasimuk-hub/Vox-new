from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_services import SERVICE_APPOINTMENTS, SERVICE_INTERVIEW, SERVICE_SURVEY
from app.models.agent import AgentDefinition
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.voice_agent_platform_settings import DEFAULT_OPENING_DISCLOSURE, VoiceAgentPlatformSettings
from app.services.interview_dialect_packs import (
    ARABIC_FORBIDDEN_PHRASES,
    CANONICAL_OPENING_AR,
    CANONICAL_OPENING_EN,
    dialect_code_for_agent,
    interview_call_workflow_for_dialect,
    interview_dialect_lexicon_block,
    interview_duration_spoken,
    interview_human_behavior_for_dialect,
    interview_opening_template_for_dialect,
    interview_timeframe_spoken,
)
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

# Interview opening = identity check only. Intro / duration / recording live in the canonical workflow.
DEFAULT_INTERVIEW_OPENING_FALLBACK = CANONICAL_OPENING_EN
DEFAULT_INTERVIEW_OPENING_FALLBACK_AR = CANONICAL_OPENING_AR

# Legacy alias — recording is no longer appended to the opening for interviews.
ARABIC_RECORD_AVAILABILITY = (
    "ممتاز. قبل أن نبدأ، أود التذكير بأن هذه المكالمة مسجّلة لأغراض الجودة، هل هذا مناسب؟"
)

# Professional real-interview behaviour — dialect packs (see interview_dialect_packs).
INTERVIEW_HUMAN_BEHAVIOR_EN = interview_human_behavior_for_dialect("GB")
INTERVIEW_HUMAN_BEHAVIOR_AR = interview_human_behavior_for_dialect("SA")
INTERVIEW_CALL_WORKFLOW_EN = interview_call_workflow_for_dialect("GB")

# Arabic runtime layers used when an Arabic agent (e.g. Jammal) is selected but the
# stored system prompt / call workflow are still copied from an English template.
ARABIC_BASE_ROLE = (
    "تكلم كأنك موظف توظيف خليجي محترف على جوال — مو روبوت ولا مذيع أخبار. "
    "عربي خليجي طبيعي (سعودي/إماراتي). جمل قصيرة. "
    "اسمع بذكاء: إذا ما فهمت أو الجواب برا الموضوع، اسأل يوضح — لا تقل فهمت عليك وتنتقل. "
    "افهم المرشّح بكل اللهجات: خليجي، مصري، شامي/لبناني — ورد بخليجي واضح. "
    "توقف بعد كل سؤال. احترم المقاطعات."
)
ARABIC_EGYPTIAN_BASE_ROLE = (
    "تكلم كأنك موظف توظيف مصري محترف على التليفون — مو روبوت ولا فصحى. "
    "مصري طبيعي وواضح. جمل قصيرة. "
    "اسمع بذكاء: لو الإجابة مش واضحة أو برا الموضوع، اسأل «ممكن توضح قصدك؟» — متقولش تمام وتنقل. "
    "افهم لو المرشّح تكلم خليجي أو شامي أو مصري — ورد بمصري محترم. "
    "توقف بعد كل سؤال. احترم المقاطعات."
)
ARABIC_GULF_HUMAN_SPEECH_RULES = (
    "أسلوب الكلام (إلزامي — أولوية بعد اللغة):\n"
    "- تكلم خليجي مهني دافئ — ممثل شركة، مو كلام أصحاب.\n"
    "- لا تستخدم فصحى رسمية جامدة. لا تتكلم كأنك تقرأ بيانًا.\n"
    "- ممنوع أو تجنّب: «هل يمكنك»، «أود أن»، «إذن»، «حضرة»، «لقد»، «بالتأكيد سيدي»، «سوف أقوم»، «يرجى التكرم».\n"
    f"- {ARABIC_FORBIDDEN_PHRASES}\n"
    "- استخدم: تمام، مفهوم، شكراً، الحين، وش، طيب، زين — نوّع الردود القصيرة.\n"
    "- إذا السؤال في النص المعتمد مكتوب فصحى، قل المعنى نفسه بخليجي طبيعي قبل ما تنتظر الإجابة.\n"
    "- ردودك ١–٢ جملة غالبًا. اتبع سير المكالمة الكنسي خطوة بخطوة.\n"
    "- ممنوع ترد بـ «تمام» أو «مفهوم» لوحدها وتنتقل — اسمع، وضّح، أو اسأل بعمق.\n"
    "- الرد الآلي / البريد الصوتي: لا تقول شيء وأنهِ فورًا."
)
ARABIC_EGYPTIAN_HUMAN_SPEECH_RULES = (
    "أسلوب الكلام (إلزامي — أولوية بعد اللغة):\n"
    "- تكلم مصري مهني دافئ طول المكالمة — ممثل شركة، مش كلام أصحاب. ممنوع فصحى رسمية جامدة.\n"
    "- ممنوع أو تجنّب: «هل يمكنك»، «أود أن»، «حضرة»، «سوف أقوم»، «يرجى التكرم»، «إذن»، «لقد».\n"
    f"- {ARABIC_FORBIDDEN_PHRASES}\n"
    "- استخدم: تمام، مفهوم، شكراً، دلوقتي، إزاي — نوّع الردود القصيرة.\n"
    "- إذا السؤال في النص المعتمد مكتوب فصحى، قل المعنى نفسه بمصري طبيعي قبل ما تنتظر الإجابة.\n"
    "- ردودك ١–٢ جملة غالبًا. اتبع سير المكالمة الكنسي خطوة بخطوة.\n"
    "- ممنوع ترد بـ «تمام» أو «مفهوم» لوحدها وتنتقل — اسمع، وضّح، أو اسأل بعمق.\n"
    "- الرد الآلي / البريد الصوتي: متقولش حاجة وانهِ فورًا."
)
ARABIC_HUMAN_SPEECH_RULES = ARABIC_GULF_HUMAN_SPEECH_RULES
ARABIC_INTERVIEW_SERVICE_ROLE = (
    "أجرِ مقابلات هاتفية منظمة حسب سير المكالمة الكنسي فقط.\n"
    "بعد تأكيد الهوية والوقت والإفصاح عن التسجيل: اطرح أسئلة النص المعتمد بالترتيب.\n"
    "السؤال 1–2: ارجع لسيرة المرشّح عند الحاجة. السؤال 3+: من دور الوظيفة ومعايير الحملة.\n"
    "قيّم الإجابات من حيث الوضوح والملاءمة. لا تقل أبدًا «استبيان». "
    "قل: أتصل بخصوص مقابلة {role} — لا تخترع أوصافًا غريبة."
)
ARABIC_INTERVIEW_CALL_WORKFLOW = interview_call_workflow_for_dialect("SA")
ARABIC_EGYPTIAN_INTERVIEW_CALL_WORKFLOW = interview_call_workflow_for_dialect("EG")

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def _contains_arabic(text: str | None) -> bool:
    return bool(_ARABIC_RE.search(str(text or "")))


def arabic_dialect_runtime_for_agent(agent: AgentDefinition | None) -> dict[str, str]:
    """Runtime dialect blocks for Arabic interview calls — agent-specific (Gulf vs Egyptian)."""
    from app.services.interview_agent_display_service import interview_agent_dialect_meta

    dialect_code = "SA"
    if agent is not None:
        dialect_code = str(interview_agent_dialect_meta(agent).get("dialect_code") or "SA").upper()

    if dialect_code == "EG":
        return {
            "language_priority": (
                "تعليمات اللغة (أولوية قصوى): أجرِ المكالمة بالكامل بالعربية المصرية الطبيعية — "
                "التحية وجميع الأسئلة والمتابعات وكل ردودك. ممنوع الفصحى الرسمية. ممنوع خلط فصحى مع عامية. "
                "الأسئلة في النص المعتمد قد تكون فصحى — قلّها بمصري طبيعي بنفس المعنى. "
                "لا تتحدث الإنجليزية إلا إذا طلب المرشّح ذلك صراحةً."
            ),
            "speech_rules": ARABIC_EGYPTIAN_HUMAN_SPEECH_RULES,
            "base_role": ARABIC_EGYPTIAN_BASE_ROLE,
            "call_workflow": interview_call_workflow_for_dialect("EG"),
            "dialect_code": "EG",
            "lexicon": interview_dialect_lexicon_block("EG"),
        }
    return {
        "language_priority": (
            "تعليمات اللغة (أولوية قصوى): أجرِ المكالمة بالكامل بالعربية الخليجية (أسلوب سعودي/إماراتي طبيعي) — "
            "التحية وجميع الأسئلة والمتابعات وكل ردودك. لا تستخدم فصحى رسمية في كلامك. "
            "الأسئلة في النص المعتمد قد تكون فصحى — قلّها بخليجي طبيعي بنفس المعنى. "
            "لا تتحدث الإنجليزية إلا إذا طلب المرشّح ذلك صراحةً."
        ),
        "speech_rules": ARABIC_GULF_HUMAN_SPEECH_RULES,
        "base_role": ARABIC_BASE_ROLE,
        "call_workflow": interview_call_workflow_for_dialect("SA"),
        "dialect_code": "SA",
        "lexicon": interview_dialect_lexicon_block("SA"),
    }


def _config_script_text(config: dict[str, Any]) -> str:
    """Best-effort approved interview/survey script text used to detect the call language."""
    return str(
        config.get("approved_script")
        or config.get("generated_script_draft")
        or config.get("survey_runtime_prompt")
        or ""
    )


def agent_language(agent: AgentDefinition | None) -> str:
    """Return 'ar' or 'en' for the selected interview agent."""
    return "ar" if agent_is_arabic(agent) else "en"


def resolve_interview_language(config: dict[str, Any]) -> str:
    """Interview language from explicit config, else majority script detection.

    Prefer ``script_language_code`` / ``language_code`` set by the wizard.
    Fallback uses letter-ratio detection so a brand token like ``BBC عربي``
    inside an English script does not flip the interview to Arabic.
    """
    for key in ("script_language_code", "language_code", "interview_language"):
        raw = str(config.get(key) or "").strip().lower()
        if raw.startswith("ar"):
            return "ar"
        if raw.startswith("en"):
            return "en"
    return detect_config_language(config)


def detect_config_language(config: dict[str, Any]) -> str:
    """Resolve language from script text using majority Arabic letters (not any-char).

    Used when the order has no explicit ``script_language_code``. Voice runtime
    only supports ``ar`` / ``en`` (French maps to English for TTS/STT).
    """
    from app.utils.script_language import detect_script_language

    detected = detect_script_language(_config_script_text(config))
    return "ar" if detected == "ar" else "en"


def agent_is_arabic(agent: AgentDefinition | None) -> bool:
    """True when the selected agent is an Arabic agent (e.g. "Jammal - Ar").

    Detected from the agent's Arabic opening disclosure / system prompt, or an
    ``ar``/``arabic`` marker in its name/voice label.
    """
    if agent is None:
        return False
    if _contains_arabic(getattr(agent, "opening_disclosure_template", "") or ""):
        return True
    if _contains_arabic(getattr(agent, "system_prompt", "") or ""):
        return True
    blob = " ".join(
        str(getattr(agent, attr, "") or "")
        for attr in ("name", "voice_label", "voice_type_label", "slug")
    ).lower()
    if "عرب" in blob:
        return True
    return bool(re.search(r"(?:^|[^a-z])(ar|arabic)(?:$|[^a-z])", blob))


class InterviewAgentLanguageMismatch(ValueError):
    """Interview language and selected agent language do not match."""


def interview_agent_language_mismatch_message(*, interview_lang: str, agent_lang: str) -> str:
    interview_lang = "ar" if str(interview_lang or "").startswith("ar") else "en"
    agent_lang = "ar" if str(agent_lang or "").startswith("ar") else "en"
    if interview_lang == "en" and agent_lang == "ar":
        return (
            "Interview language is English but an Arabic agent is selected. "
            "Choose an English agent."
        )
    if interview_lang == "ar" and agent_lang == "en":
        return (
            "Interview language is Arabic but an English agent is selected. "
            "Choose an Arabic agent."
        )
    return "Interview language and selected agent language do not match. Choose a different agent."


def assert_interview_agent_language_match(
    config: dict[str, Any],
    agent: AgentDefinition | None,
    *,
    require_agent: bool = False,
) -> str:
    """Ensure interview language and agent language match. Returns interview language."""
    interview_lang = resolve_interview_language(config)
    if agent is None:
        if require_agent:
            raise InterviewAgentLanguageMismatch("Select an AI voice agent for this interview.")
        return interview_lang
    agent_lang = agent_language(agent)
    if agent_lang != interview_lang:
        raise InterviewAgentLanguageMismatch(
            interview_agent_language_mismatch_message(
                interview_lang=interview_lang, agent_lang=agent_lang
            )
        )
    return interview_lang


def detect_interview_language(config: dict[str, Any], agent: AgentDefinition | None = None) -> str:
    """Resolve spoken interview language from explicit config (strict match with agent).

    Interview language is authoritative. When an agent is present it must match;
    mismatches raise ``InterviewAgentLanguageMismatch``. Brand tokens in the script
    alone do not flip English interviews to Arabic.
    """
    return assert_interview_agent_language_match(config, agent, require_agent=False)


def call_should_use_arabic(
    agent: AgentDefinition | None,
    *,
    script: str = "",
    survey_prompt: str = "",
    criteria: str = "",
    config: dict[str, Any] | None = None,
) -> bool:
    """True when the whole call (layers + speech) must run in Arabic.

    Prefer explicit interview language on ``config``. Agent language is only used
    when config has no language and no script text to score.
    """
    if isinstance(config, dict) and config:
        return resolve_interview_language(config) == "ar"
    if agent is not None:
        return agent_is_arabic(agent)
    from app.utils.script_language import detect_script_language

    blob = "\n".join(str(x or "") for x in (script, survey_prompt, criteria))
    return detect_script_language(blob) == "ar"


def _layer_text_for_call_language(text: str, *, arabic_default: str, use_arabic: bool) -> str:
    """Keep Arabic layer text as-is; replace English template layers with Arabic defaults."""
    raw = str(text or "").strip()
    if not use_arabic:
        return raw
    if _contains_arabic(raw):
        return raw
    return arabic_default


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
    duration: str = "",
    timeframe: str = "",
    job_title: str = "",
    reschedule_link: str = "",
) -> str:
    """Replace all runtime voice placeholders used in agent templates, KB, and scripts."""
    organiser = str(organiser_name or agent_name or company_name).strip()
    agent = str(agent_name or organiser or "the recruiter").strip()
    role_line = str(role or job_title or "this role").strip()
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
        "job_title": role_line,
        "organiser_name": organiser,
        "position": role_line,
        "goal": role_line,
        "duration": str(duration or "").strip(),
        "timeframe": str(timeframe or "").strip(),
        "reschedule_link": str(reschedule_link or "").strip(),
    }
    for key, value in mapping.items():
        if value:
            out = out.replace(f"{{{key}}}", value)
    if first_name:
        out = out.replace("{first_name}", first).replace("{candidate_name}", first)
    return out.strip()


def resolve_opening_disclosure_template(
    db: Session,
    *,
    agent: AgentDefinition | None,
    config: dict[str, Any],
    service_key: str = SERVICE_SURVEY,
    org_id: str | None = None,
    first_name: str = "",
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
    agent_name = str((agent.voice_label if agent else None) or (agent.name if agent else None) or "the recruiter").strip()
    role = str(config.get("role") or config.get("goal") or config.get("position") or "this role").strip()
    use_arabic = call_should_use_arabic(agent, config=config)
    duration = interview_duration_spoken(use_arabic=use_arabic, config=config)
    timeframe = interview_timeframe_spoken(use_arabic=use_arabic, config=config)

    org_template = ""
    if org_id:
        from app.models.organisation_ai_config import OrganisationComplianceConfig

        compliance = db.execute(
            select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id)
        ).scalar_one_or_none()
        if compliance and str(compliance.ai_disclosure_wording or "").strip():
            org_template = str(compliance.ai_disclosure_wording).strip()

    template = ""
    if service_key == SERVICE_INTERVIEW:
        # Canonical interview opening = identity check only (recording then time are later workflow steps).
        dialect = dialect_code_for_agent(agent) if agent else ("SA" if use_arabic else "GB")
        if use_arabic:
            template = interview_opening_template_for_dialect(
                dialect if dialect in {"EG", "SA"} else "SA"
            )
        else:
            template = interview_opening_template_for_dialect(
                dialect if dialect not in {"EG", "SA", "AR"} else "GB"
            )
    elif agent and str(agent.opening_disclosure_template or "").strip():
        template = str(agent.opening_disclosure_template).strip()
    elif org_template:
        template = org_template
    elif platform.opening_disclosure_template:
        template = str(platform.opening_disclosure_template).strip()
    else:
        template = DEFAULT_OPENING_DISCLOSURE

    if mandatory and not template.strip():
        if service_key == SERVICE_INTERVIEW:
            template = DEFAULT_INTERVIEW_OPENING_FALLBACK_AR if use_arabic else DEFAULT_INTERVIEW_OPENING_FALLBACK
        else:
            template = DEFAULT_OPENING_DISCLOSURE

    script_ar = use_arabic
    if script_ar and service_key != SERVICE_INTERVIEW:
        from app.services.service_script_generator import _localize_disclosure_for_script_language

        template = _localize_disclosure_for_script_language(
            template,
            language_code="ar",
            agent_name=agent_name,
            company_name=company_name,
        )

    rendered = substitute_voice_placeholders(
        template,
        company_name=company_name,
        organiser_name=organiser_name,
        agent_name=agent_name,
        role=role,
        first_name=first_name,
        duration=duration,
        timeframe=timeframe,
    )
    if mandatory and not rendered.strip():
        rendered = substitute_voice_placeholders(
            DEFAULT_OPENING_DISCLOSURE if service_key != SERVICE_INTERVIEW else (
                DEFAULT_INTERVIEW_OPENING_FALLBACK_AR if use_arabic else DEFAULT_INTERVIEW_OPENING_FALLBACK
            ),
            company_name=company_name,
            organiser_name=organiser_name,
            agent_name=agent_name,
            role=role,
            first_name=first_name or "",
            duration=duration,
            timeframe=timeframe,
        )
    if service_key == SERVICE_INTERVIEW:
        # Do not append recording or time-ask to the opening — those are workflow steps after identity.
        return rendered
    if service_key == SERVICE_SURVEY and mandatory and "record" not in rendered.lower():
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
    # Prefer colloquial Arabic system_prompt over a stale English base_role for Arabic agents.
    agent_system = str((agent.system_prompt if agent else None) or "").strip()
    agent_base = str((agent.base_role if agent else None) or "").strip()
    if agent_system and _contains_arabic(agent_system) and (not agent_base or not _contains_arabic(agent_base)):
        base = agent_system
    else:
        base = agent_base or agent_system
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
    if layers.base_role and service_key != SERVICE_INTERVIEW:
        parts.append(f"Agent base role:\n{layers.base_role}")
    elif layers.base_role and service_key == SERVICE_INTERVIEW:
        parts.append(
            "Agent persona (live calls only): the agent speaks in their natural colloquial dialect on the phone. "
            "Do NOT write QUESTIONS in dialect — QUESTIONS must stay in Fusha for customer review."
        )
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
            "This is a job interview — never call it a survey.\n"
            "For Arabic scripts: all QUESTIONS must be Modern Standard Arabic (Fusha) for customer review. "
            "The live agent will speak colloquially on the call — do not write questions in Gulf or Egyptian dialect."
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
    use_arabic_preview = call_should_use_arabic(
        agent, script=script, survey_prompt=survey_prompt, criteria=criteria, config=config
    )
    duration = interview_duration_spoken(use_arabic=use_arabic_preview, config=config)
    timeframe = interview_timeframe_spoken(use_arabic=use_arabic_preview, config=config)
    reschedule_link = str(config.get("reschedule_link") or config.get("booking_link") or "").strip()
    placeholder_kwargs = {
        "company_name": company_name,
        "organiser_name": organiser,
        "agent_name": agent_name,
        "role": role,
        "first_name": first,
        "duration": duration,
        "timeframe": timeframe,
        "job_title": role,
        "reschedule_link": reschedule_link,
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
    use_arabic = call_should_use_arabic(
        agent, script=script, survey_prompt=survey_prompt, criteria=criteria, config=config
    )
    dialect_runtime = arabic_dialect_runtime_for_agent(agent) if use_arabic else None
    dialect_code = dialect_code_for_agent(agent) if service_key == SERVICE_INTERVIEW else "GB"
    base_role = _layer_text_for_call_language(
        layers.base_role,
        arabic_default=(dialect_runtime or {}).get("base_role") or ARABIC_BASE_ROLE,
        use_arabic=use_arabic,
    )
    service_role = layers.service_role
    if use_arabic and service_key == SERVICE_INTERVIEW:
        service_role = _layer_text_for_call_language(
            layers.service_role, arabic_default=ARABIC_INTERVIEW_SERVICE_ROLE, use_arabic=True
        )
    call_workflow = layers.call_workflow
    if service_key == SERVICE_INTERVIEW:
        # Canonical interviewer workflow from dialect pack (brief → listen → closing).
        if use_arabic:
            call_workflow = (dialect_runtime or {}).get("call_workflow") or interview_call_workflow_for_dialect("SA")
        else:
            call_workflow = interview_call_workflow_for_dialect(dialect_code)

    if use_arabic and dialect_runtime:
        parts.append(dialect_runtime["language_priority"])
        parts.append(dialect_runtime["speech_rules"])
        if dialect_runtime.get("lexicon"):
            parts.append(dialect_runtime["lexicon"])
        if agent and str(getattr(agent, "conversation_style", "") or "").strip():
            parts.append(
                "أسلوب المحادثة:\n"
                + substitute_voice_placeholders(str(agent.conversation_style).strip(), **placeholder_kwargs)
            )
    elif service_key == SERVICE_INTERVIEW and not use_arabic:
        parts.append(interview_dialect_lexicon_block(dialect_code))
    # Interview pacing / no-interrupt / mandatory closing — early so truncation cannot drop it.
    if service_key == SERVICE_INTERVIEW:
        behavior = interview_human_behavior_for_dialect(
            (dialect_runtime or {}).get("dialect_code") if use_arabic else dialect_code
        )
        parts.append(substitute_voice_placeholders(behavior, **placeholder_kwargs))
    if layers.compliance and not (use_arabic and not _contains_arabic(layers.compliance)):
        parts.append(substitute_voice_placeholders(layers.compliance, **placeholder_kwargs))
    if base_role:
        parts.append(substitute_voice_placeholders(base_role, **placeholder_kwargs))
    if service_role:
        parts.append(substitute_voice_placeholders(service_role, **placeholder_kwargs))
    if call_workflow:
        workflow_label = "سير المكالمة (اتبعه حرفيًا بعد التحية):" if use_arabic else "Call workflow (follow exactly after opening):"
        parts.append(
            f"{workflow_label}\n" + substitute_voice_placeholders(call_workflow, **placeholder_kwargs)
        )
    if layers.kb_context:
        kb_label = "مرجع معرفة (تحدث عن هذا المحتوى بالعربية فقط):" if use_arabic else "Reference knowledge:"
        parts.append(
            f"{kb_label}\n" + substitute_voice_placeholders(layers.kb_context, **placeholder_kwargs)
        )

    if use_arabic:
        parts.append(f"اسم المنظمة (استخدم هذا الاسم بالضبط في المكالمة): {company_name}")
    else:
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
        if use_arabic:
            parts.append(f"تتصل بالنيابة عن: {organiser}")
            parts.append(f"الاسم الأول للمرشّح: {first}")
            if goal:
                parts.append(f"الوظيفة / المنصب: {role}")
            if criteria:
                parts.append(f"معايير المقابلة:\n{criteria}")
            if cv_snippet:
                parts.append(f"ملخص السيرة الذاتية (استخدمه في السؤالين الأولين):\n{cv_snippet}")
            parts.append(
                "هذه مكالمة مقابلة توظيف منظمة — وليست استبيانًا. "
                f"أنت تتصل بالنيابة عن {company_name} بخصوص مقابلة {role}. "
                "اتبع سير المكالمة الكنسي حرفيًا: بعد تأكيد الهوية → التعريف والوقت → "
                "إذا وافق: الإفصاح عن التسجيل ثم الأسئلة؛ إذا رفض الوقت: رابط البريد فقط وأنهِ. "
                "لا تقل كلمة «شركة» بشكل عام دون ذكر اسم المنظمة الفعلي. "
                "لا تعِد سؤال الهوية — سُئل بالفعل في بداية المكالمة."
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
                "This is a structured job interview screening call — NOT a survey. "
                f"You are calling on behalf of {company_name} regarding the {role} interview. "
                "Follow the canonical call workflow exactly: after identity confirm → same-person check → "
                "recording consent (wait) → time ask (wait) → questions; "
                "if they decline recording: end; if not a good time: email-link only and end. "
                "Never say the generic word 'company' without the actual organisation name. "
                "Do not re-ask the identity check — it was already spoken in the opening."
            )

    if layers.campaign_system_prompt and not (use_arabic and not _contains_arabic(layers.campaign_system_prompt)):
        parts.append(
            "Campaign notes:\n"
            + substitute_voice_placeholders(layers.campaign_system_prompt, **placeholder_kwargs)
        )

    if survey_prompt:
        live_script = survey_prompt
        if service_key == SERVICE_INTERVIEW:
            live_script = strip_opening_and_intro_from_script(survey_prompt) or survey_prompt
        if use_arabic:
            if service_key == SERVICE_SURVEY:
                script_heading = "نص الاستبيان المعتمد (اتبع هذا الهيكل):"
            else:
                script_heading = (
                    "نص المقابلة المعتمد (أسئلة وإغلاق فقط — التحية والمقدمة سُئلتا بالفعل، لا تقرأهما):"
                )
        else:
            if service_key == SERVICE_SURVEY:
                script_heading = "Approved survey script (follow this structure):"
            else:
                script_heading = (
                    "Approved interview script (QUESTIONS and CLOSING only — "
                    "OPENING DISCLOSURE and INTRO were already spoken; do not read them):"
                )
        parts.append(script_heading + "\n" + substitute_voice_placeholders(live_script, **placeholder_kwargs))

    platform = _platform_settings(db)
    mandatory = disclosure_mandatory(platform, agent)
    question_label = "survey questions" if service_key == SERVICE_SURVEY else "confirmation steps" if service_key == SERVICE_APPOINTMENTS else "interview questions"
    if layers.opening_disclosure:
        if service_key == SERVICE_INTERVIEW:
            if use_arabic:
                parts.append(
                    "تمت خطوة الهوية فقط في أول المكالمة (مرحباً، ممكن اتكلم مع المرشّح؟). "
                    "لا تكرر سؤال الهوية. "
                    "انتظر الرد: إذا نفي → اعتذر وأنهِ. إذا نعم → تأكد نفس الشخص (ممنوع بديل)، "
                    "ثم التعريف + الإفصاح عن التسجيل فقط واستنى، "
                    "ثم سؤال الوقت فقط واستنى. "
                    "إذا رفض التسجيل → أنهِ بلا إعادة جدولة. "
                    "إذا الوقت غير مناسب → جملة رابط البريد الإلكتروني فقط ثم أنهِ (ممنوع طلب معاد شفهي). "
                    "إذا الوقت مناسب → الأسئلة. "
                    "ممنوع دمج التسجيل والوقت في نفس الدور. "
                    "ممنوع اختراع أوصاف مثل «مقابلة فرد» أو «فرز»."
                )
            else:
                parts.append(
                    "Only the identity check was already spoken (Hello, is this the candidate?). "
                    "Do NOT repeat the identity check. "
                    "Wait: if wrong person → apologise and end. If yes → same-person only "
                    "(do not interview a substitute), then introduce yourself, company, role interview, "
                    "and ask recording consent only — wait for yes/no. "
                    "If they decline recording → end (no reschedule). "
                    "If they consent → ask if now is a good time only — wait. "
                    "If not a good time → email-link reschedule line only, then end (no verbal callback). "
                    "If yes → proceed to interview questions. "
                    "FORBIDDEN: combining recording consent and the time ask in one turn."
                )
        elif use_arabic:
            parts.append(
                "تمت التحية الافتتاحية مع المرشّح بالفعل. لا تكرر التحية. تابع بقسم المقدمة من النص المعتمد "
                "(التحقق من التوفر / سير المكالمة)، ثم أسئلة المقابلة."
            )
        else:
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
    if layers.interruption_notes and not (use_arabic and not _contains_arabic(layers.interruption_notes)):
        behavior.append(layers.interruption_notes)
    if service_key == SERVICE_SURVEY and is_ai_call_survey_config(config):
        behavior.extend(_survey_interrupt_behavior_rules(anonymous=survey_anonymous_enabled(config)))
        followup = build_survey_call_negative_followup_rule(config)
        if followup:
            behavior.append(followup)
    elif service_key == SERVICE_INTERVIEW:
        # Full behaviour already injected early; keep short interrupt + availability reminders here.
        behavior.append(
            "إذا قاطعك المرشّح وسط جملة، أعد الجملة الناقصة فقط — لا تعِد المقدمة كاملة."
            if use_arabic
            else "If interrupted mid-sentence, restate only the unfinished sentence — never restart the full introduction."
        )
        behavior.append(
            "لا تنتقل إلى أسئلة المقابلة حتى: (1) تأكيد نفس الشخص و(2) موافقة التسجيل و(3) الوقت مناسب. "
            "اسأل بوابة واحدة في كل مرة واستنى."
            if use_arabic
            else "Do not continue to interview questions until (1) same person is confirmed, "
            "(2) recording disclosure has been acknowledged, and (3) now is a good time. "
            "Ask only one gate question per turn and wait."
        )
        behavior.append(
            "لو سلّم الخط لحد تاني أو جاوب بديل عن المرشّح: اعتذر وأنهِ — ممنوع تكمّل المقابلة مع شخص آخر."
            if use_arabic
            else "If they hand the phone to someone else or a substitute answers for the candidate: "
            "apologise and end — do not continue the interview with another person."
        )
        behavior.append(
            "بعد آخر سؤال: اشكر المرشّح وقل إن الفريق سيراجع الإجابات ويتواصل خلال الإطار الزمني — ثم ودّع. لا تنهِ قبل ذلك."
            if use_arabic
            else "After the last question: thank the candidate, say the team will review and be in touch "
            "within the timeframe, then say goodbye. Do not end the call before that closing."
        )
        behavior.append(
            "الرد الآلي / البريد الصوتي: لا تقل أي شيء وأنهِ المكالمة فورًا."
            if use_arabic
            else "Voicemail / answering machine: say nothing and end the call immediately."
        )
        if layers.interruption_notes and not (use_arabic and not _contains_arabic(layers.interruption_notes)):
            # Prefer wait-for-full-answer wording over thin "restate unfinished" only notes.
            notes = str(layers.interruption_notes).strip()
            if "never interrupt" not in notes.lower() and "لا تقاطع" not in notes:
                behavior.append(
                    "لا تقاطع المرشّح أثناء إجابته — انتظر حتى ينهي."
                    if use_arabic
                    else "Never interrupt the candidate while they are answering — wait until they finish."
                )
    else:
        behavior.append(
            "إذا قاطعك المرشّح قبل إنهاء المقدمة، توقف وكرر الخطوة الحالية بوضوح من البداية."
            if use_arabic
            else "If the recipient interrupts before you finish the opening, pause and repeat the current step clearly from the start."
        )
    if layers.opt_out_notes and not (use_arabic and not _contains_arabic(layers.opt_out_notes)):
        behavior.append(layers.opt_out_notes)
    else:
        behavior.append(
            "إذا طلب المرشّح الإزالة من القائمة أو التوقف عن الاتصال، اعترف بلباقة وأنهِ المكالمة ولا تتابع."
            if use_arabic
            else "If the recipient asks to be removed, stop calling, or opts out, acknowledge politely, end the call, "
            "and do not continue."
        )
    if layers.retry_notes and not (use_arabic and not _contains_arabic(layers.retry_notes)):
        behavior.append(f"Retry policy notes: {layers.retry_notes}")
    if layers.voicemail_notes and not (use_arabic and not _contains_arabic(layers.voicemail_notes)):
        behavior.append(f"Voicemail behavior: {layers.voicemail_notes}")

    behavior_label = "قواعد السلوك:" if use_arabic else "Behavior rules:"
    parts.append(behavior_label + "\n" + "\n".join(f"- {line}" for line in behavior if line))
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
    use_arabic = call_should_use_arabic(agent, config=config)
    duration = interview_duration_spoken(use_arabic=use_arabic, config=config)
    timeframe = interview_timeframe_spoken(use_arabic=use_arabic, config=config)
    placeholder_kwargs = {
        "company_name": company_name,
        "organiser_name": organiser_name,
        "agent_name": agent_name,
        "role": role,
        "first_name": first,
        "duration": duration,
        "timeframe": timeframe,
        "job_title": role,
    }

    disclosure = resolve_opening_disclosure_template(
        db, agent=agent, config=config, service_key=service_key, org_id=org_id, first_name=first
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
            f"Hi {first}, this is {agent_name} calling from {company_name} "
            f"for a short survey.{anon_clause} This call is recorded for quality."
        )
    if service_key == SERVICE_APPOINTMENTS:
        appt_dt = str(config.get("appointment_datetime") or "your upcoming appointment").strip()
        return (
            f"Hello {first}, this is {agent_name} calling from {company_name} "
            f"about your appointment on {appt_dt}. This call is recorded for quality. "
            f"Am I speaking with {first}?"
        )
    interview_fallback = (
        DEFAULT_INTERVIEW_OPENING_FALLBACK_AR
        if use_arabic
        else DEFAULT_INTERVIEW_OPENING_FALLBACK
    )
    return substitute_voice_placeholders(interview_fallback, **placeholder_kwargs)


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
        return "the recruiter"
    return str(agent.voice_label or agent.name or "the recruiter").strip()


def strip_opening_and_intro_from_script(script: str) -> str:
    """Keep QUESTIONS/CLOSING for live interview calls — opening was already spoken as greeting."""
    text = str(script or "").strip()
    if not text:
        return ""
    match = re.search(r"(?im)^\s*QUESTIONS\b", text)
    if match:
        return text[match.start() :].strip()
    # No QUESTIONS header — drop OPENING DISCLOSURE / INTRO blocks if present
    text = re.sub(
        r"(?is)^\s*OPENING\s+DISCLOSURE\s*\r?\n.*?(?=^\s*(?:INTRO|QUESTIONS|CLOSING)\b)",
        "",
        text,
    )
    text = re.sub(r"(?is)^\s*INTRO\s*\r?\n.*?(?=^\s*(?:QUESTIONS|CLOSING)\b)", "", text)
    return text.strip()
