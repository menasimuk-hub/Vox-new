"""Batched Meta template pushes with pauses to avoid rate limits / spam detection."""

from __future__ import annotations

import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import get_settings


def template_push_batch_size(limit: int | None = None) -> int:
    settings = get_settings()
    raw = int(limit if limit is not None else settings.wa_template_push_batch_size)
    return max(1, min(raw, 10))


def template_push_batch_pause() -> float:
    settings = get_settings()
    return max(0.5, float(settings.wa_template_push_batch_pause_seconds))


def run_batched_push(
    items: list[Any],
    *,
    offset: int = 0,
    limit: int | None = None,
    push_one: Callable[[Any], dict[str, Any]],
    item_label: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    batch = template_push_batch_size(limit)
    pause = template_push_batch_pause()
    start = max(0, int(offset or 0))
    total = len(items)
    chunk = items[start : start + batch]

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    pushed = 0
    skipped = 0
    linked = 0

    for idx, item in enumerate(chunk):
        if idx > 0:
            time.sleep(pause)
        label = item_label(item) if item_label else str(item)
        try:
            result = push_one(item)
            if result.get("linked") or result.get("skipped_push"):
                linked += 1
            elif result.get("skipped"):
                skipped += 1
            else:
                pushed += 1
            results.append({"ok": True, "label": label, **result})
        except Exception as exc:  # noqa: BLE001
            errors.append({"label": label, "error": str(exc)[:500]})

    next_offset = start + len(chunk)
    return {
        "ok": len(errors) == 0,
        "pushed": pushed,
        "linked": linked,
        "skipped": skipped,
        "error_count": len(errors),
        "errors": errors,
        "results": results,
        "offset": start,
        "limit": batch,
        "next_offset": next_offset,
        "has_more": next_offset < total,
        "total": total,
        "message": (
            f"Pushed batch {start + 1}–{next_offset} of {total}"
            + (" (more remaining)" if next_offset < total else " (complete)")
        ),
    }
