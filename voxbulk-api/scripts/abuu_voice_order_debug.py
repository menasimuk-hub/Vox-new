#!/usr/bin/env python3
"""Inspect and replay Abuu voice order debug pipeline stages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.abuu.services.voice_order_debug_service import VoiceOrderDebugService
from app.abuu.services.voice_order_replay_service import VoiceOrderReplayService
from app.core.abuu_database import get_abuu_sessionmaker
from app.core.database import get_sessionmaker


def _print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_show(order_request_id: str) -> int:
    with get_abuu_sessionmaker()() as abuu_db:
        bundle = VoiceOrderDebugService.get_bundle(abuu_db, order_request_id)
        if bundle is None:
            print(f"Not found: {order_request_id}", file=sys.stderr)
            return 1
        _print_json(bundle)
    return 0


def cmd_replay(
    *,
    order_request_id: str | None,
    audio_path: str | None,
    phone: str | None,
    from_step: int,
) -> int:
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        try:
            result = VoiceOrderReplayService.replay(
                abuu_db,
                main_db,
                order_request_id=order_request_id,
                audio_path=audio_path,
                phone=phone,
                from_step=from_step,
                dry_run=True,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        _print_json(result)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Abuu voice order debug tools")
    sub = parser.add_subparsers(dest="command", required=True)

    show_parser = sub.add_parser("show", help="Print all six pipeline stages for a request")
    show_parser.add_argument("order_request_id")

    replay_parser = sub.add_parser("replay", help="Re-run stages 2-5 without creating an order")
    replay_parser.add_argument("order_request_id", nargs="?", default=None)
    replay_parser.add_argument("--audio", dest="audio_path", default=None)
    replay_parser.add_argument("--phone", default=None)
    replay_parser.add_argument("--from-step", type=int, default=2, choices=[2, 3, 4, 5])

    args = parser.parse_args()
    if args.command == "show":
        return cmd_show(args.order_request_id)
    if args.command == "replay":
        if not args.order_request_id and not args.audio_path:
            replay_parser.error("Provide order_request_id or --audio")
        if args.audio_path and not args.phone:
            replay_parser.error("--phone is required with --audio")
        return cmd_replay(
            order_request_id=args.order_request_id,
            audio_path=args.audio_path,
            phone=args.phone,
            from_step=args.from_step,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
