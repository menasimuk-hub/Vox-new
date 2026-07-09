#!/usr/bin/env python3
"""Live test: DeepInfra + DeepSeek for marketing utility rewrite (run on VPS)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_wa_utility_rewrite_service import (
    DEFAULT_UTILITY_LLM_MODEL,
    resolve_utility_llm_config,
    rewrite_body_for_utility,
)


def _probe_provider(db, *, provider: str, model: str | None) -> dict:
    system = 'Return JSON only: {"ok":true,"provider":"' + provider + '"}'
    try:
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system,
            messages=[AgentMessage(role="user", content="ping")],
            max_tokens=60,
            temperature=0,
            provider=provider,
            model=model,
        )
        text = str(result.assistant_text or "").strip()
        return {"provider": provider, "model": model or "(default)", "ok": True, "sample": text[:200]}
    except Exception as exc:
        return {"provider": provider, "model": model or "(default)", "ok": False, "error": str(exc)[:400]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Test utility LLM providers on VPS")
    parser.add_argument("--english-only", action="store_true", help="Force English body that needs rewrite")
    args = parser.parse_args()

    db = get_sessionmaker()()
    try:
        try:
            cfg = resolve_utility_llm_config(db)
            print("Resolved LLM:", {k: v for k, v in cfg.items() if k != "api_key_set"})
            print("API key set:", cfg.get("api_key_set"))
        except Exception as exc:
            print("resolve_utility_llm_config ERROR:", exc)
            cfg = {}

        for provider, model in (
            ("deepinfra", DEFAULT_UTILITY_LLM_MODEL),
            ("deepseek", None),
        ):
            out = _probe_provider(db, provider=provider, model=model)
            print(f"\n--- probe {provider} ---")
            for k, v in out.items():
                print(f"  {k}: {v}")

        original = (
            "How satisfied were you with our hotel atmosphere?"
            if args.english_only
            else "🌆 ¿Cómo calificarías el ambiente y la atmósfera de nuestro hotel?"
        )
        template = "cfs_hotel_atmosphere_en_v1" if args.english_only else "cfs_hotel_atmosphere_es_v1"
        lang = "en_gb" if args.english_only else "es_gb"

        print("\n--- rewrite_body_for_utility (deepinfra) ---")
        try:
            rewritten = rewrite_body_for_utility(
                db,
                original_body=original,
                button_labels=["Poor", "Fair", "Good"] if args.english_only else ["Malo", "Regular", "Bueno"],
                template_name=template,
                industry_slug="hotel",
                topic_name="atmosphere",
                language=lang,
                use_llm=True,
                llm_provider="deepinfra",
                llm_model=DEFAULT_UTILITY_LLM_MODEL,
            )
            changed = rewritten.strip() != original.strip()
            print("  changed:", changed)
            print("  before:", original)
            print("  after:", rewritten)
        except Exception as exc:
            print("  ERROR:", exc)

        if args.english_only:
            print("\n--- rewrite_body_for_utility (deepseek fallback) ---")
            try:
                rewritten = rewrite_body_for_utility(
                    db,
                    original_body=original,
                    button_labels=["Poor", "Fair", "Good"],
                    template_name=template,
                    industry_slug="hotel",
                    topic_name="atmosphere",
                    language=lang,
                    use_llm=True,
                    llm_provider="deepseek",
                    llm_model=None,
                )
                changed = rewritten.strip() != original.strip()
                print("  changed:", changed)
                print("  before:", original)
                print("  after:", rewritten)
            except Exception as exc:
                print("  ERROR:", exc)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
