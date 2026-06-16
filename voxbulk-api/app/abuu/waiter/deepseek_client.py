"""DeepSeek client with timeout and fallback flag."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService
from app.abuu.waiter.trace import trace

logger = logging.getLogger(__name__)
_sem: threading.BoundedSemaphore | None = None
_sem_lock = threading.Lock()


def _semaphore() -> threading.BoundedSemaphore:
    global _sem
    if _sem is None:
        with _sem_lock:
            if _sem is None:
                cap = max(1, int(get_settings().abuu_agent_max_concurrent_llm or 30))
                _sem = threading.BoundedSemaphore(value=cap)
    return _sem


@dataclass
class DeepSeekResult:
    text: str
    fallback_used: bool = False
    error: str | None = None


class WaiterDeepSeekClient:
    @staticmethod
    def complete(
        main_db: Session,
        *,
        system_prompt: str,
        user_content: str,
        max_tokens: int = 200,
        temperature: float = 0.2,
    ) -> DeepSeekResult:
        settings = get_settings()
        timeout = float(settings.abuu_waiter_deepseek_timeout_seconds)
        if not _semaphore().acquire(blocking=True, timeout=timeout):
            trace("FAIL", reason="deepseek_concurrency_timeout")
            return DeepSeekResult(text="", fallback_used=True, error="concurrency_timeout")
        try:
            result = OpenAIProviderService.complete(
                main_db,
                system_prompt=system_prompt,
                messages=[AgentMessage(role="user", content=user_content)],
                max_tokens=max_tokens,
                temperature=temperature,
                provider="deepseek",
            )
            text = str(result.assistant_text or "").strip()
            return DeepSeekResult(text=text, fallback_used=False)
        except Exception as exc:
            logger.warning("waiter_deepseek_failed", exc_info=True)
            trace("FAIL", reason="deepseek_error", error=str(exc)[:200])
            return DeepSeekResult(text="", fallback_used=True, error=str(exc))
        finally:
            _semaphore().release()
