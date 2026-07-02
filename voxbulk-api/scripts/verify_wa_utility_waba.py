#!/usr/bin/env python3
"""Verify Telnyx integration WABA matches the expected Voxbulk Ltd WABA for UTILITY migration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants.wa_utility_migration import EXPECTED_WABA_ID, META_BUSINESS_PORTFOLIO_ID
from app.core.database import get_sessionmaker
from app.services.telnyx_voice_service import _telnyx_config, resolve_telnyx_whatsapp_waba_id


def main() -> int:
    with get_sessionmaker()() as db:
        try:
            config = _telnyx_config(db)
        except Exception as exc:
            print(f"ERROR: Telnyx not configured: {exc}", file=sys.stderr)
            return 1

        configured = str(config.get("whatsapp_waba_id") or config.get("waba_id") or "").strip()
        resolved = resolve_telnyx_whatsapp_waba_id(db, config)

    print(f"Expected WABA ID:     {EXPECTED_WABA_ID}")
    print(f"Portfolio (reference): {META_BUSINESS_PORTFOLIO_ID}")
    print(f"Admin configured:     {configured or '(empty)'}")
    print(f"Resolved for push:    {resolved or '(empty)'}")

    effective = configured or resolved
    if not effective:
        print(
            "\nERROR: No WABA ID found. Set Admin → Integrations → Telnyx → WhatsApp WABA ID "
            f"to {EXPECTED_WABA_ID} and Save.",
            file=sys.stderr,
        )
        return 1

    if effective != EXPECTED_WABA_ID:
        print(
            f"\nERROR: WABA mismatch. Active={effective!r} expected={EXPECTED_WABA_ID!r}. "
            "Update Admin → Integrations → Telnyx before running migration push.",
            file=sys.stderr,
        )
        return 1

    print("\nOK — WABA matches. Safe to run migrate_wa_templates_utility.py --push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
