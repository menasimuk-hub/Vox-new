#!/usr/bin/env python3
"""One-time cleanup: merge duplicate parent/clone WA survey template rows into one active row."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_template_clone_push_service import relink_template_references
from app.services.survey_whatsapp_template_service import template_row_is_sendable_on_meta
from app.services.telnyx_whatsapp_template_sync_service import _detach_template_references


def _family_key(row: TelnyxWhatsappTemplate) -> int:
    parent_id = int(row.parent_template_id or 0)
    if parent_id:
        return parent_id
    return int(row.id)


def _pick_winner(group: list[TelnyxWhatsappTemplate]) -> TelnyxWhatsappTemplate:
    sendable = [r for r in group if template_row_is_sendable_on_meta(r) and r.active_for_survey]
    if sendable:
        return max(sendable, key=lambda r: int(r.id))
    active = [r for r in group if r.active_for_survey]
    if active:
        return max(active, key=lambda r: int(r.id))
    return max(group, key=lambda r: int(r.id))


def main() -> int:
    deleted = 0
    relinked = 0
    with get_sessionmaker()() as db:
        rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
        families: dict[int, list[TelnyxWhatsappTemplate]] = defaultdict(list)
        id_to_row = {int(r.id): r for r in rows}
        seen_families: set[int] = set()
        for row in rows:
            if not str(row.name or "").startswith("voxbulk_survey_"):
                continue
            key = _family_key(row)
            if key not in seen_families:
                seen_families.add(key)
                root = id_to_row.get(key, row)
                for candidate in rows:
                    cid = int(candidate.id)
                    pid = int(candidate.parent_template_id or 0)
                    if cid == key or pid == key:
                        families[key].append(candidate)
        for _family_id, group in families.items():
            if len(group) <= 1:
                winner = group[0]
                if winner.parent_template_id:
                    winner.parent_template_id = None
                    db.add(winner)
                continue
            winner = _pick_winner(group)
            winner.parent_template_id = None
            winner.active_for_survey = True
            db.add(winner)
            for loser in group:
                lid = int(loser.id)
                if lid == int(winner.id):
                    continue
                counts = relink_template_references(db, lid, int(winner.id))
                relinked += sum(counts.values())
                loser.active_for_survey = False
                db.add(loser)
                _detach_template_references(db, lid)
                db.delete(loser)
                deleted += 1
        db.commit()
    print(f"cleanup_wa_template_clone_rows: deleted={deleted} relink_refs={relinked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
