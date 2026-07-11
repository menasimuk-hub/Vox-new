from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.knowledge_base_file import KnowledgeBaseFile
from app.services.agents.base import AgentMessage
from app.services.knowledge_base_service import build_kb_context_text
from app.services.providers.openai_service import OpenAIProviderService

_WORKFLOW_META = """You are an expert voice-agent workflow designer for VOXBULK.
Return ONLY valid JSON with one string field:
- "call_workflow": numbered step-by-step call flow (greeting through close), when to ask questions, escalation, callback confirmation.

British English. Be specific and operational. No markdown fences."""

_PROMPT_META = """You are an expert prompt engineer for VOXBULK voice and chat agents.
Return ONLY valid JSON with one string field:
- "system_prompt": role, tone, constraints, knowledge usage, safety. Must align with the approved call workflow.

British English. Be specific and operational. No markdown fences."""

_BOTH_META = """You are an expert prompt engineer for VOXBULK voice and chat agents.
Return ONLY valid JSON with exactly two string fields:
- "system_prompt": role, tone, constraints, knowledge usage, safety
- "call_workflow": numbered call flow (greeting through close), when to ask questions, escalation

British English. Be specific and operational. No markdown fences."""

_WORKFLOW_META_AR_FUSHA = """أنت خبير في تصميم سير مكالمات وكلاء الصوت لمنصة VOXBULK.
أرجع JSON صالحًا فقط بحقل نصي واحد:
- "call_workflow": خطوات مرقّمة لسير المكالمة (من بعد التحية حتى الإغلاق)، متى تُطرح الأسئلة، التصعيد، تأكيد الموعد البديل.

اكتب بالعربية الفصحى الحديثة فقط — ليست خليجية وليست مصرية عامية.
ممنوع تمامًا: وش، الحين، تبي، زين، إزيك، دلوقتي، إيه، ماشي، عايز، هتعمل.
ملاحظة: الكلام الحي على الهاتف سيُحوَّل للهجة المحلية في وقت التشغيل؛ النص المُولَّد هنا يبقى فصحى.
كن عمليًا ومحددًا. بلا أسوار markdown."""

_PROMPT_META_AR_FUSHA = """أنت خبير في هندسة التعليمات لوكلاء الصوت في VOXBULK.
أرجع JSON صالحًا فقط بحقل نصي واحد:
- "system_prompt": الدور، النبرة، القيود، استخدام المعرفة، السلامة — متوافق مع سير المكالمة المعتمد.

اكتب بالعربية الفصحى الحديثة فقط — ليست خليجية وليست مصرية عامية.
ممنوع تمامًا: وش، الحين، تبي، زين، إزيك، دلوقتي، إيه، ماشي، عايز، هتعمل.
ضمّن ملاحظة قصيرة أن الكلام الحي على الهاتف يُنفَّذ باللهجة المحلية عبر قواعد التشغيل، بينما هذا النص يبقى فصحى.
لا تصف الوكيل بأنه «مساعد ذكي» أو روبوت — قدّمه باسمه فقط.
كن عمليًا ومحددًا. بلا أسوار markdown."""

_BOTH_META_AR_FUSHA = """أنت خبير في هندسة التعليمات لوكلاء الصوت في VOXBULK.
أرجع JSON صالحًا فقط بحقلين نصيين:
- "system_prompt": الدور، النبرة، القيود، استخدام المعرفة، السلامة
- "call_workflow": سير المكالمة المرقّم (من بعد التحية حتى الإغلاق)، متى تُطرح الأسئلة، التصعيد

اكتب بالعربية الفصحى الحديثة فقط — ليست خليجية وليست مصرية عامية.
ممنوع تمامًا: وش، الحين، تبي، زين، إزيك، دلوقتي، إيه، ماشي، عايز، هتعمل.
الكلام الحي على الهاتف سيُحوَّل للهجة المحلية في وقت التشغيل؛ النص المُولَّد هنا يبقى فصحى.
كن عمليًا ومحددًا. بلا أسوار markdown."""

# Live-call Admin generation must match the spoken dialect (not Fusha).
_WORKFLOW_META_AR_EG = """أنت خبير في تصميم سير مكالمات وكلاء الصوت لمنصة VOXBULK.
أرجع JSON صالحًا فقط بحقل نصي واحد:
- "call_workflow": خطوات مرقّمة لسير المكالمة (من بعد التحية حتى الإغلاق).

اكتب بمصري عامية طبيعية فقط — زي موظف توظيف على التليفون. ممنوع الفصحى الرسمية.
استخدم: تمام، ماشي، دلوقتي، إزاي، نبدأ. ممنوع تقول «نكمل» في بداية المقابلة — قول «نبدأ».
كن عمليًا ومحددًا. بلا أسوار markdown."""

_PROMPT_META_AR_EG = """أنت خبير في هندسة التعليمات لوكلاء الصوت في VOXBULK.
أرجع JSON صالحًا فقط بحقل نصي واحد:
- "system_prompt": الدور، النبرة، القيود، السلامة — متوافق مع سير المكالمة.

اكتب بمصري عامية طبيعية فقط. ممنوع الفصحى. ممنوع خلط فصحى/عامية.
الوكيل يتكلم زي موظف توظيف ودود على التليفون — مش روبوت.
بعد موافقة المرشّح: وضّح إن دي مقابلة قصيرة بخصوص الوظيفة واسأله «جاهز؟ يلا نبدأ» — متقولش «نكمل».
الاستماع الذكي: وضّح («تقصد إيه بالضبط؟») / تابع / اذكر تفصيلة — ممنوع تمام لوحدها وتنقل.
الإغلاق: شكر + الشركة هتراجع وهتتواصل + مع السلامة.
لا تصف الوكيل بأنه مساعد ذكي. كن عمليًا. بلا أسوار markdown."""

_BOTH_META_AR_EG = """أنت خبير في هندسة التعليمات لوكلاء الصوت في VOXBULK.
أرجع JSON صالحًا فقط بحقلين نصيين: system_prompt و call_workflow.
اكتب بمصري عامية طبيعية فقط. ممنوع الفصحى. قول نبدأ مش نكمل. بلا أسوار markdown."""

_WORKFLOW_META_AR_SA = """أنت خبير في تصميم سير مكالمات وكلاء الصوت لمنصة VOXBULK.
أرجع JSON صالحًا فقط بحقل نصي واحد:
- "call_workflow": خطوات مرقّمة لسير المكالمة (من بعد التحية حتى الإغلاق).

اكتب بعربي خليجي طبيعي فقط (سعودي/إماراتي). ممنوع الفصحى الرسمية.
استخدم: تمام، زين، الحين، وش، نبدأ. كن عمليًا. بلا أسوار markdown."""

_PROMPT_META_AR_SA = """أنت خبير في هندسة التعليمات لوكلاء الصوت في VOXBULK.
أرجع JSON صالحًا فقط بحقل نصي واحد:
- "system_prompt": الدور، النبرة، القيود، السلامة.

اكتب بعربي خليجي طبيعي فقط. ممنوع الفصحى. زي موظف توظيف على جوال — مو روبوت.
بعد الموافقة: وضّح إن هذي مقابلة قصيرة بخصوص الوظيفة واسأله جاهز؟ نبدأ.
الاستماع الذكي: وضّح / تابع / اذكر تفصيلة — ممنوع تمام لوحدها وتنتقل.
الإغلاق: شكر + الشركة بتراجع وتتواصل + في أمان الله.
لا تصف الوكيل بأنه مساعد ذكي. كن عمليًا. بلا أسوار markdown."""

_BOTH_META_AR_SA = """أنت خبير في هندسة التعليمات لوكلاء الصوت في VOXBULK.
أرجع JSON صالحًا فقط بحقلين نصيين: system_prompt و call_workflow.
اكتب بعربي خليجي طبيعي فقط. ممنوع الفصحى. بلا أسوار markdown."""


def _extract_json_object(raw: str) -> dict:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("DeepSeek response must be a JSON object")
    return data


def _parse_json_field(raw: str, field: str) -> str:
    data = _extract_json_object(raw)
    value = str(data.get(field) or "").strip()
    if not value:
        raise ValueError(f"Generated JSON must include non-empty {field}")
    return value


def _parse_both_fields(raw: str) -> dict[str, str]:
    data = _extract_json_object(raw)
    system_prompt = str(data.get("system_prompt") or "").strip()
    call_workflow = str(data.get("call_workflow") or "").strip()
    if not system_prompt or not call_workflow:
        raise ValueError("Generated JSON must include non-empty system_prompt and call_workflow")
    return {"system_prompt": system_prompt, "call_workflow": call_workflow}


def _kb_section(files: list[KnowledgeBaseFile]) -> str:
    body = build_kb_context_text(files)
    if not body:
        return "No knowledge base files selected."
    return (
        "Knowledge base file contents (authoritative — base workflow and prompt on these facts only; "
        "do not invent pricing or policy):\n\n"
        f"{body}"
    )


def _user_block(*, agent_name: str, description: str, knowledge_files: list[KnowledgeBaseFile], call_workflow: str | None = None) -> str:
    parts = [
        f"Agent name: {agent_name or 'Unnamed agent'}",
        f"Operator description (what this agent should do):\n{description}",
        _kb_section(knowledge_files),
    ]
    if call_workflow:
        parts.append(f"Approved call workflow (system prompt must follow this):\n{call_workflow}")
    return "\n\n".join(parts)


def is_arabic_interview_prompt_target(
    *,
    agent: Any | None = None,
    agent_name: str = "",
    description: str = "",
    supports_interview: bool | None = None,
) -> bool:
    """True when Admin Generate Prompt should emit spoken Arabic dialect for an Arabic interview agent."""
    interview = supports_interview
    if interview is None and agent is not None:
        interview = bool(getattr(agent, "supports_interview", False))
    if not interview:
        return False

    blob = " ".join(
        [
            str(agent_name or ""),
            str(description or ""),
            str(getattr(agent, "name", "") or "") if agent is not None else "",
            str(getattr(agent, "slug", "") or "") if agent is not None else "",
            str(getattr(agent, "voice_label", "") or "") if agent is not None else "",
            str(getattr(agent, "voice_type_label", "") or "") if agent is not None else "",
            str(getattr(agent, "description", "") or "") if agent is not None else "",
            str(getattr(agent, "system_prompt", "") or "")[:400] if agent is not None else "",
        ]
    )
    if re.search(r"[\u0600-\u06FF]", blob):
        return True
    low = blob.lower()
    markers = (
        "arabic",
        "egypt",
        "saudi",
        "gulf",
        "jammal",
        "jamal",
        "sultan",
        "interview-ar",
        "interview_ar",
        "مصري",
        "خليجي",
        "سعود",
    )
    return any(m in low for m in markers)


def resolve_arabic_interview_dialect(
    *,
    agent: Any | None = None,
    agent_name: str = "",
    description: str = "",
    supports_interview: bool | None = None,
) -> str | None:
    """Return 'EG' or 'SA' for Arabic interview agents, else None."""
    if not is_arabic_interview_prompt_target(
        agent=agent,
        agent_name=agent_name,
        description=description,
        supports_interview=supports_interview,
    ):
        return None
    if agent is not None:
        try:
            from app.services.interview_agent_display_service import interview_agent_dialect_meta

            code = str(interview_agent_dialect_meta(agent).get("dialect_code") or "").upper()
            if code == "EG":
                return "EG"
            if code in {"SA", "AR"}:
                return "SA"
        except Exception:
            pass
    blob = f"{agent_name} {description} {getattr(agent, 'slug', '')} {getattr(agent, 'name', '')}".lower()
    if any(m in blob for m in ("jammal", "jamal", "egypt", "مصري", "eg")):
        return "EG"
    return "SA"


def _meta_for(*, kind: str, arabic_fusha: bool = False, arabic_dialect: str | None = None) -> str:
    # Prefer live dialect generation for interview agents (Fusha made calls sound robotic).
    dialect = str(arabic_dialect or "").upper() or None
    if dialect == "EG":
        if kind == "workflow":
            return _WORKFLOW_META_AR_EG
        if kind == "both":
            return _BOTH_META_AR_EG
        return _PROMPT_META_AR_EG
    if dialect == "SA":
        if kind == "workflow":
            return _WORKFLOW_META_AR_SA
        if kind == "both":
            return _BOTH_META_AR_SA
        return _PROMPT_META_AR_SA
    if arabic_fusha:
        if kind == "workflow":
            return _WORKFLOW_META_AR_FUSHA
        if kind == "both":
            return _BOTH_META_AR_FUSHA
        return _PROMPT_META_AR_FUSHA
    if kind == "workflow":
        return _WORKFLOW_META
    if kind == "both":
        return _BOTH_META
    return _PROMPT_META


def _complete_json(db: Session, *, meta: str, user: str, instruction: str) -> str:
    result = OpenAIProviderService.complete(
        db,
        system_prompt=meta,
        messages=[AgentMessage(role="user", content=f"{user}\n\n{instruction}")],
        max_tokens=2500,
        temperature=0.4,
        provider="deepseek",
    )
    return result.assistant_text


def generate_call_workflow(
    db: Session,
    *,
    agent_name: str,
    description: str,
    knowledge_files: list[KnowledgeBaseFile],
    agent: Any | None = None,
    arabic_fusha: bool | None = None,
) -> dict[str, str]:
    description = str(description or "").strip()
    if not description:
        raise ValueError("description is required to generate workflow")
    dialect = resolve_arabic_interview_dialect(agent=agent, agent_name=agent_name, description=description)
    # Ignore legacy arabic_fusha=True for live interview agents — dialect prompts only.
    use_legacy_fusha = bool(arabic_fusha) and dialect is None
    user = _user_block(agent_name=agent_name, description=description, knowledge_files=knowledge_files)
    if dialect == "EG":
        instruction = (
            "أنتج call_workflow بمصري طبيعي لمكالمات صوتية حية. التحية اتسألت بالفعل — "
            "ابدأ من انتظار تأكيد الوقت، بعدين جهّز المرشّح وقول نبدأ مش نكمل، بعدين الأسئلة."
        )
    elif dialect == "SA":
        instruction = (
            "أنتج call_workflow بخليجي طبيعي لمكالمات صوتية حية. التحية سُئلت بالفعل — "
            "ابدأ من انتظار تأكيد الوقت ثم تجهيز المرشّح ثم الأسئلة."
        )
    elif use_legacy_fusha:
        instruction = (
            "أنتج call_workflow مناسبًا لمكالمات صوتية حية. التحية سُئلت بالفعل في بداية المكالمة — "
            "ابدأ السير من انتظار تأكيد الوقت ثم الأسئلة."
        )
    else:
        instruction = (
            "Produce call_workflow suitable for live phone or browser voice calls. "
            "The opening greeting is already spoken — start after time confirmation, then questions."
        )
    raw = _complete_json(
        db,
        meta=_meta_for(kind="workflow", arabic_fusha=use_legacy_fusha, arabic_dialect=dialect),
        user=user,
        instruction=instruction,
    )
    try:
        workflow = _parse_json_field(raw, "call_workflow")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("DeepSeek returned invalid JSON for workflow generation") from exc
    return {"call_workflow": workflow}


def generate_system_prompt(
    db: Session,
    *,
    agent_name: str,
    description: str,
    knowledge_files: list[KnowledgeBaseFile],
    call_workflow: str,
    agent: Any | None = None,
    arabic_fusha: bool | None = None,
) -> dict[str, str]:
    description = str(description or "").strip()
    workflow = str(call_workflow or "").strip()
    if not description:
        raise ValueError("description is required to generate prompt")
    if not workflow:
        raise ValueError("call_workflow is required before generating system prompt")
    dialect = resolve_arabic_interview_dialect(agent=agent, agent_name=agent_name, description=description)
    use_legacy_fusha = bool(arabic_fusha) and dialect is None
    user = _user_block(
        agent_name=agent_name,
        description=description,
        knowledge_files=knowledge_files,
        call_workflow=workflow,
    )
    if dialect == "EG":
        instruction = (
            "أنتج system_prompt بمصري طبيعي لمكالمات صوتية حية. "
            "لا تكرر التحية. بعد الموافقة جهّز المرشّح وقول جاهز نبدأ؟ — متقولش نكمل."
        )
    elif dialect == "SA":
        instruction = (
            "أنتج system_prompt بخليجي طبيعي لمكالمات صوتية حية. "
            "لا تعِد التحية. بعد الموافقة جهّز المرشّح واسأله جاهز نبدأ؟"
        )
    elif use_legacy_fusha:
        instruction = (
            "أنتج system_prompt مناسبًا لمكالمات صوتية حية. اكتب فصحى فقط. "
            "لا تكرر التحية؛ الكلام الحي سيكون باللهجة المحلية عبر قواعد التشغيل."
        )
    else:
        instruction = "Produce system_prompt suitable for live phone or browser voice calls."
    raw = _complete_json(
        db,
        meta=_meta_for(kind="prompt", arabic_fusha=use_legacy_fusha, arabic_dialect=dialect),
        user=user,
        instruction=instruction,
    )
    try:
        prompt = _parse_json_field(raw, "system_prompt")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("DeepSeek returned invalid JSON for prompt generation") from exc
    return {"system_prompt": prompt}


def generate_agent_prompts(
    db: Session,
    *,
    agent_name: str,
    description: str,
    knowledge_files: list[KnowledgeBaseFile],
    agent: Any | None = None,
    arabic_fusha: bool | None = None,
) -> dict[str, str]:
    """Legacy: generate workflow and prompt together."""
    description = str(description or "").strip()
    if not description:
        raise ValueError("description is required to generate prompts")
    dialect = resolve_arabic_interview_dialect(agent=agent, agent_name=agent_name, description=description)
    use_legacy_fusha = bool(arabic_fusha) and dialect is None
    user = _user_block(agent_name=agent_name, description=description, knowledge_files=knowledge_files)
    if dialect == "EG":
        instruction = "أنتج system_prompt و call_workflow بمصري طبيعي لمكالمات صوتية حية. قول نبدأ مش نكمل."
    elif dialect == "SA":
        instruction = "أنتج system_prompt و call_workflow بخليجي طبيعي لمكالمات صوتية حية."
    elif use_legacy_fusha:
        instruction = "أنتج system_prompt و call_workflow بالعربية الفصحى لمكالمات صوتية حية."
    else:
        instruction = "Produce system_prompt and call_workflow suitable for live phone or browser voice calls."
    raw = _complete_json(
        db,
        meta=_meta_for(kind="both", arabic_fusha=use_legacy_fusha, arabic_dialect=dialect),
        user=user,
        instruction=instruction,
    )
    try:
        return _parse_both_fields(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("DeepSeek returned invalid JSON for prompt generation") from exc
