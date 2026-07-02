#!/usr/bin/env python3
"""Fix templates stuck with Meta 2388024: link if possible, else rename and push fresh."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_utility_rewrite_service import (
    _find_template_row,
    apply_utility_rewrite_to_row,
)
from app.services.survey_whatsapp_template_service import (
    SYNC_IN_SYNC,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _apply_remote_telnyx_item,
    _has_remote_telnyx_id,
    _resolve_push_language,
    _try_link_existing_remote_template,
)
from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService
from app.services.wa_template_meta_sync import suggest_alternate_template_name

_LOCAL_PREFIX = "local-"


def _topic_slug(name: str) -> str:
    m = re.match(r"^voxbulk_survey_(.+)_(?:abc|utu)_[a-f0-9]{6}$", str(name or "").strip().lower())
    return m.group(1) if m else ""


def _find_remote_exact(name: str, items: list[dict]) -> dict | None:
    target = name.strip().lower()
    for item in items:
        if str(item.get("name") or "").strip().lower() == target:
            return item
    return None


def _find_remote_by_slug(name: str, items: list[dict]) -> dict | None:
    slug = _topic_slug(name)
    if not slug:
        return None
    matches = [i for i in items if slug in str(i.get("name") or "").lower()]
    if not matches:
        return None
    exact = [i for i in matches if str(i.get("name") or "").strip().lower() == name.strip().lower()]
    if exact:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    return None


def _try_link_row(db, row, *, lang: str, waba_items: list, all_items: list) -> bool:
    rid = str(row.telnyx_record_id or "").strip()
    if rid and not rid.startswith(_LOCAL_PREFIX):
        try:
            item = TelnyxWhatsappTemplateSyncService.fetch_template_by_record_id(db, rid)
            _apply_remote_telnyx_item(row, item, overwrite_draft=False)
            db.add(row)
            db.commit()
            db.refresh(row)
            return True
        except Exception:
            pass

    for items in (waba_items, all_items):
        if _try_link_existing_remote_template(db, row, language=lang, remote_items=items):
            return True
        remote = _find_remote_exact(str(row.name or ""), items)
        if remote is None:
            remote = _find_remote_by_slug(str(row.name or ""), items)
        if remote is not None:
            _apply_remote_telnyx_item(row, remote, overwrite_draft=False)
            db.add(row)
            db.commit()
            db.refresh(row)
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Link or rename+push stuck UTILITY survey templates")
    parser.add_argument("--template-name", action="append", required=True)
    args = parser.parse_args()

    ok = 0
    fail = 0
    names = [n.strip() for n in args.template_name if str(n or "").strip()]

    with get_sessionmaker()() as db:
        waba_items = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(db, filter_waba_id=True)
        all_items = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(db, filter_waba_id=False)
        print(f"Telnyx templates fetched: waba={len(waba_items)} all={len(all_items)}")

        for name in names:
            row = _find_template_row(db, name)
            if row is None:
                print(f"MISS {name}")
                fail += 1
                continue

            lang, lang_error = _resolve_push_language(db, row)
            if lang_error:
                print(f"FAIL {name}: {lang_error}")
                fail += 1
                continue

            if _try_link_row(db, row, lang=lang, waba_items=waba_items, all_items=all_items):
                row.last_push_error = None
                row.local_sync_status = SYNC_IN_SYNC
                db.add(row)
                db.commit()
                SurveyWhatsappTemplateService.refresh_telnyx_status(db, row)
                print(f"OK  {name}: linked as {row.name} status={row.status}")
                ok += 1
                continue

            new_name = suggest_alternate_template_name(str(row.name or ""))
            print(f"RENAME {name} -> {new_name}")
            row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
            apply_utility_rewrite_to_row(db, row, use_llm=False)
            try:
                result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                msg = str(result.get("sync_message") or result.get("message") or "pushed")
                print(f"OK  {new_name}: {msg}")
                ok += 1
            except SurveyWhatsappTemplateError as exc:
                print(f"FAIL {new_name}: {exc}")
                fail += 1

    print(f"Done: {ok} ok, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
