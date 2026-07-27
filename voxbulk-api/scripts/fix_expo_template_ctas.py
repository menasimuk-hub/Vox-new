#!/usr/bin/env python3
"""Fix Expo Apify template CTAs on VPS DB: trial_url + unsubscribe_url + Gmail-safe white button."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.core.database import get_sessionmaker

TPL_ID = "6a693edd-f711-4137-ba82-f12661b20840"

# Gmail-safe CTA: inline white text (class styles often ignored → blue links)
WHITE_TRIAL_CTA = (
    '<a href="{{trial_url}}" target="_blank" '
    'style="display:inline-block;background:#16a34a;color:#ffffff !important;'
    'padding:10px 28px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;'
    'mso-padding-alt:0;">'
    '<span style="color:#ffffff !important;text-decoration:none;font-weight:600;">'
    "Start Free Trial →"
    "</span></a>"
)

UNSUB = (
    '<a href="{{unsubscribe_url}}" '
    'style="color:#6b6560 !important;text-decoration:underline;">Unsubscribe</a>'
)


def fix_html(html: str) -> str:
    out = html
    # Hardcoded trial / register URLs → merge tag
    out = re.sub(
        r'href=(["\'])https?://(?:www\.)?voxbulk\.com/expo/trial\1',
        'href="{{trial_url}}"',
        out,
        flags=re.I,
    )
    out = re.sub(
        r'href=(["\'])https?://(?:www\.)?voxbulk\.com/signin(?:\?[^"\']*)?\1',
        'href="{{trial_url}}"',
        out,
        flags=re.I,
    )
    # Replace green button anchor(s) that use class=btn-green
    out = re.sub(
        r'<a\b[^>]*class=["\'][^"\']*btn-green[^"\']*["\'][^>]*>.*?</a>',
        WHITE_TRIAL_CTA,
        out,
        flags=re.I | re.S,
    )
    # Any remaining trial_url with only class styling (no inline color) already handled;
    # ensure href is trial_url on Start Free Trial text
    out = re.sub(
        r'<a\b([^>]*?)href=["\'][^"\']*["\']([^>]*)>\s*Start Free Trial[^<]*</a>',
        WHITE_TRIAL_CTA,
        out,
        flags=re.I | re.S,
    )
    # Unsubscribe # or empty → merge tag
    out = re.sub(
        r'<a\b[^>]*href=["\']#["\'][^>]*>\s*Unsubscribe\s*</a>',
        UNSUB,
        out,
        flags=re.I | re.S,
    )
    out = re.sub(
        r'<a\b[^>]*>\s*Unsubscribe\s*</a>',
        UNSUB,
        out,
        flags=re.I | re.S,
    )
    return out


def main() -> None:
    db = get_sessionmaker()()
    row = db.execute(
        text("SELECT id, name, html_template FROM ai_team_email_templates WHERE id = :id"),
        {"id": TPL_ID},
    ).mappings().first()
    if not row:
        # fallback by name
        row = db.execute(
            text(
                "SELECT id, name, html_template FROM ai_team_email_templates "
                "WHERE name = 'free 3 days expo code' LIMIT 1"
            )
        ).mappings().first()
    if not row:
        print("ERROR: template not found")
        sys.exit(1)

    before = row["html_template"] or ""
    after = fix_html(before)
    changed = before != after
    print("template:", row["id"], row["name"])
    print("changed:", changed)
    print("has trial_url:", "{{trial_url}}" in after)
    print("has unsubscribe_url:", "{{unsubscribe_url}}" in after)
    print("hardcoded expo/trial left:", "voxbulk.com/expo/trial" in after.lower())
    print("href=# left:", 'href="#"' in after or "href='#'" in after)

    if changed:
        db.execute(
            text(
                "UPDATE ai_team_email_templates SET html_template = :html, updated_at = UTC_TIMESTAMP() "
                "WHERE id = :id"
            ),
            {"html": after, "id": row["id"]},
        )
        camp = db.execute(
            text(
                "UPDATE ai_team_campaigns SET html_template = :html, updated_at = UTC_TIMESTAMP() "
                "WHERE template_id = :id"
            ),
            {"html": after, "id": row["id"]},
        )
        db.commit()
        print("DB updated template + campaigns with template_id, rowcount=", camp.rowcount)
    else:
        print("No HTML changes needed")

    # also dump CTAs after
    for m in re.finditer(r"<a\b[^>]*>.*?</a>", after, flags=re.I | re.S):
        chunk = m.group(0)
        low = chunk.lower()
        if any(k in low for k in ("trial", "unsub", "start")):
            print("CTA:", " ".join(chunk.split())[:500])
    Path("/tmp/voxbulk-tpl-fixed.html").write_text(after, encoding="utf-8")
    print("saved /tmp/voxbulk-tpl-fixed.html")
    db.close()


if __name__ == "__main__":
    main()
