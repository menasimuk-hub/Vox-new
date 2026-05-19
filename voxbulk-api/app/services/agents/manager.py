from __future__ import annotations

import base64
import json
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import AgentAssignment, AgentDefinition
from app.models.call_log import CallLog
from app.models.category import Category
from app.models.organisation import Organisation
from app.services.agents.base import AgentMessage, AgentRunRequest, AgentRunResult, AgentRuntimeContext, AgentToolCall
from app.services.agents.registry import AgentRegistry
from app.services.agents.tools import AgentToolRegistry
from app.services.providers.azure_speech import AzureSpeechProviderService
from app.services.providers.openai_service import OpenAIProviderService


class AgentManager:
    @staticmethod
    def resolve_agent(db: Session, *, org_id: str, agent_id: str | None = None) -> AgentDefinition:
        AgentRegistry.ensure_default_agents(db)
        if agent_id:
            agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id, AgentDefinition.is_active.is_(True))).scalar_one_or_none()
            if agent is None:
                raise ValueError("Agent not found or inactive")
            return agent

        assigned = db.execute(
            select(AgentDefinition)
            .join(AgentAssignment, AgentAssignment.agent_id == AgentDefinition.id)
            .where(AgentAssignment.org_id == org_id, AgentDefinition.is_active.is_(True))
        ).scalar_one_or_none()
        if assigned is not None:
            return assigned

        org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
        if org is not None and org.category_id:
            business = db.execute(
                select(AgentDefinition)
                .join(AgentAssignment, AgentAssignment.agent_id == AgentDefinition.id)
                .where(AgentAssignment.category_id == org.category_id, AgentDefinition.is_active.is_(True))
            ).scalar_one_or_none()
            if business is not None:
                return business

        default = db.execute(select(AgentDefinition).where(AgentDefinition.slug == "british-clinic-assistant")).scalar_one()
        return default

    @staticmethod
    def build_system_prompt(
        db: Session,
        *,
        agent: AgentDefinition,
        context: AgentRuntimeContext,
        extra_context: str | None = None,
    ) -> str:
        category_name = None
        if agent.category_id:
            category_name = db.execute(select(Category.name).where(Category.id == agent.category_id)).scalar_one_or_none()
        parts = [
            agent.system_prompt,
            f"Conversation style: {agent.conversation_style or 'Warm, concise British English.'}",
            f"Workflow type: {context.workflow_type}.",
        ]
        workflow = str(agent.call_workflow or "").strip()
        if workflow:
            parts.append(f"## Call workflow\n{workflow}")
        kb = str(agent.kb_context or "").strip()
        if kb:
            parts.append(f"## Knowledge base\n{kb}")
        if category_name or agent.business_type:
            parts.append(f"Business type: {category_name or agent.business_type}.")
        if context.appointment_id:
            parts.append(f"Appointment context id: {context.appointment_id}.")
        if context.patient_id:
            parts.append(f"Patient context id: {context.patient_id}.")
        if extra_context and str(extra_context).strip():
            parts.append(str(extra_context).strip())
        return "\n\n".join(parts)

    @staticmethod
    def format_lead_context(
        *,
        contact_name: str | None = None,
        company_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> str:
        lines = [
            "## Lead on this call",
            "You are speaking with a website visitor who just submitted the Talk to us form.",
            "Greet them by first name when natural.",
            "There is no human sales team — you handle qualification and next steps; CRM logging comes later.",
        ]
        if contact_name:
            lines.append(f"- Contact name: {contact_name}")
        if company_name:
            lines.append(f"- Company: {company_name}")
        if email:
            lines.append(f"- Email: {email}")
        if phone:
            lines.append(
                f"- Phone on file: {phone}. Read it back once and ask if it is still correct — do not ask again if they confirm."
            )
        else:
            lines.append(
                "- No phone provided — ask once for the best callback number."
            )
        lines.append(
            "Use the form details above immediately — do not ask them to repeat name, company, or email unless confirming."
        )
        lines.append(
            "Confirm whether they want a callback from our AI team or to continue the conversation now."
        )
        return "\n".join(lines)

    @staticmethod
    def _history_from_call(log: CallLog | None) -> list[AgentMessage]:
        if not log or not log.transcript_text:
            return []
        messages: list[AgentMessage] = []
        for line in str(log.transcript_text).splitlines()[-12:]:
            if line.startswith("caller:"):
                messages.append(AgentMessage(role="user", content=line.split(":", 1)[1].strip()))
            elif line.startswith("agent:"):
                messages.append(AgentMessage(role="assistant", content=line.split(":", 1)[1].strip()))
        return messages

    @staticmethod
    def handle_turn(
        db: Session,
        request: AgentRunRequest,
        *,
        synthesize_audio: bool = True,
        llm_model: str | None = None,
        llm_max_tokens: int | None = None,
        llm_temperature: float | None = None,
        llm_provider: str | None = None,
    ) -> AgentRunResult:
        total_start = time.perf_counter()
        resolve_start = time.perf_counter()
        agent = AgentManager.resolve_agent(db, org_id=request.context.org_id, agent_id=request.agent_id or request.context.agent_id)
        resolve_ms = int((time.perf_counter() - resolve_start) * 1000)
        log = None
        if request.context.call_control_id:
            log = db.execute(select(CallLog).where(CallLog.external_call_id == request.context.call_control_id)).scalar_one_or_none()
        prompt_start = time.perf_counter()
        history = request.history or AgentManager._history_from_call(log)
        messages = history + [AgentMessage(role="user", content=request.latest_user_utterance)]
        tools = AgentToolRegistry.definitions(
            allow_lookup=agent.allow_lookup_tool,
            allow_booking=agent.allow_booking_tool,
            allow_reschedule=agent.allow_reschedule_tool,
            allow_cancel=agent.allow_cancel_tool,
        )
        system_prompt = AgentManager.build_system_prompt(db, agent=agent, context=request.context)
        prompt_ms = int((time.perf_counter() - prompt_start) * 1000)
        completion_kwargs: dict[str, Any] = {
            "model": llm_model or agent.default_model,
            "tools": tools,
        }
        if llm_max_tokens is not None:
            completion_kwargs["max_tokens"] = llm_max_tokens
        if llm_temperature is not None:
            completion_kwargs["temperature"] = llm_temperature
        if llm_provider is not None:
            completion_kwargs["provider"] = llm_provider
        openai_start = time.perf_counter()
        completion = OpenAIProviderService.complete(
            db,
            system_prompt=system_prompt,
            messages=messages,
            **completion_kwargs,
        )
        openai_ms = int((time.perf_counter() - openai_start) * 1000)
        tool_results = [AgentToolCall(name=c.name, arguments=c.arguments, result=AgentToolRegistry.safe_not_available(c.name)) for c in completion.tool_calls]
        assistant_text = completion.assistant_text or "I'm sorry, I need to pass this to the clinic team."
        audio_b64 = None
        if synthesize_audio and agent.use_azure_tts:
            try:
                audio = AzureSpeechProviderService.synthesize_text(db, text=assistant_text)
                audio_b64 = base64.b64encode(audio).decode("ascii")
            except Exception:
                audio_b64 = None
        manager_total_ms = int((time.perf_counter() - total_start) * 1000)
        return AgentRunResult(
            agent_id=agent.id,
            agent_slug=agent.slug,
            assistant_text=assistant_text,
            tool_calls=tool_results,
            usage=completion.usage,
            audio_b64=audio_b64,
            transcript_metadata={
                "model": llm_model or agent.default_model,
                "llm_provider": llm_provider or "openai",
                "voice": agent.default_voice,
                "tool_calls": [t.__dict__ for t in tool_results],
                "timings": {
                    "manager_resolve_agent_ms": resolve_ms,
                    "manager_prompt_build_ms": prompt_ms,
                    "manager_openai_call_ms": openai_ms,
                    "manager_total_ms": manager_total_ms,
                    **completion.timings,
                },
            },
        )

    @staticmethod
    def append_turn_to_call_log(
        db: Session,
        *,
        call_control_id: str,
        caller_text: str,
        result: AgentRunResult,
    ) -> CallLog | None:
        log = db.execute(select(CallLog).where(CallLog.external_call_id == call_control_id)).scalar_one_or_none()
        if log is None:
            return None
        log.transcript_text = "\n".join([x for x in [log.transcript_text, f"caller: {caller_text}", f"agent: {result.assistant_text}"] if x])
        log.llm_response = result.assistant_text
        payload: dict[str, Any] = {}
        if log.raw_payload:
            try:
                payload = json.loads(log.raw_payload)
            except Exception:
                payload = {"previous_raw_payload": log.raw_payload}
        payload["agent"] = {
            "agent_id": result.agent_id,
            "agent_slug": result.agent_slug,
            "usage": result.usage,
            "metadata": result.transcript_metadata,
        }
        log.raw_payload = json.dumps(payload, ensure_ascii=False)
        log.last_status_at = datetime.utcnow()
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
