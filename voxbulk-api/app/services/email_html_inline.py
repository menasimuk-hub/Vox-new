"""Inline CSS into HTML for email-client delivery (Gmail, Outlook, etc.).

Email clients often strip or ignore ``<style>`` blocks. Moving rules onto
``style=""`` attributes keeps colours, padding, and fonts more reliable.

This does **not** magically make flex/grid responsive — table-based email HTML
is still best — but it helps every Apify / AI Team template consistently.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Protect merge tags that contain characters some HTML parsers may alter.
_MERGE_TAG_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_-]+)\s*\}\}")


def inline_email_css(html: str | None) -> str:
    """Copy ``<style>`` / linked rules onto element ``style`` attributes.

    Keeps ``<style>`` blocks that contain ``@media`` (helpful in Apple Mail).
    On failure, returns the original HTML unchanged.
    """
    raw = str(html or "")
    if not raw.strip():
        return raw
    # Skip pure text / tiny fragments without CSS opportunity
    lower = raw.lower()
    if "<style" not in lower and "stylesheet" not in lower and "class=" not in lower:
        # Still may have classes with no style block — nothing to inline
        if "<" not in raw:
            return raw

    placeholders: dict[str, str] = {}

    def _stash(match: re.Match[str]) -> str:
        key = match.group(1)
        token = f"__VB_MERGE_{len(placeholders)}__"
        placeholders[token] = "{{" + key + "}}"
        return token

    protected = _MERGE_TAG_RE.sub(_stash, raw)

    try:
        from css_inline import CSSInliner

        inliner = CSSInliner(
            inline_style_tags=True,
            keep_style_tags=True,  # retain @media for clients that honour it
            keep_link_tags=False,
            base_url=None,
            load_remote_stylesheets=False,
            extra_css=None,
        )
        out = inliner.inline(protected)
    except Exception as exc:
        logger.warning("email_css_inline_failed err=%s", exc)
        return raw

    for token, tag in placeholders.items():
        out = out.replace(token, tag)
    return out
