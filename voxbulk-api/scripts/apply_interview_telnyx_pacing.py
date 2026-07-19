#!/usr/bin/env python3
"""Apply normal voice speed + snappy turn-taking to all interview Telnyx assistants."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.telnyx_assistant_service import apply_interview_assistant_pacing


def main() -> int:
    Session = get_sessionmaker()
    paced = 0
    with Session() as db:
        rows = db.execute(
            select(AgentDefinition).where(AgentDefinition.supports_interview.is_(True))
        ).scalars().all()
        for agent in rows:
            aid = str(getattr(agent, "telnyx_assistant_id", "") or "").strip()
            if not aid:
                print(f"skip {agent.name}: no telnyx_assistant_id")
                continue
            try:
                # Use provider defaults (ElevenLabs ~1.12, NaturalHD ~1.2) — do not force 1.0.
                result = apply_interview_assistant_pacing(db, aid)
                voice = "voice_err" if result.get("voice_error") else "voice_ok"
                intr = "int_err" if result.get("interruption_error") else "int_ok"
                print(f"{agent.name}\t{aid}\t{voice}\t{intr}")
                paced += 1
            except Exception as exc:  # noqa: BLE001
                print(f"{agent.name}\tFAIL\t{exc}")
    print(f"paced={paced}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
