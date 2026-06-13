from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentMessage:
    role: str
    content: str


@dataclass(frozen=True)
class AgentRuntimeContext:
    org_id: str
    user_id: str | None = None
    call_log_id: int | None = None
    call_control_id: str | None = None
    appointment_id: str | None = None
    patient_id: str | None = None
    workflow_type: str = "rebooking"
    agent_id: str | None = None


@dataclass(frozen=True)
class AgentToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    id: str = ""


@dataclass(frozen=True)
class AgentRunRequest:
    context: AgentRuntimeContext
    latest_user_utterance: str
    history: list[AgentMessage] = field(default_factory=list)
    agent_id: str | None = None


@dataclass(frozen=True)
class AgentRunResult:
    agent_id: str
    agent_slug: str
    assistant_text: str
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    audio_b64: str | None = None
    transcript_metadata: dict[str, Any] = field(default_factory=dict)
