"""Shared branded HTML email wrapper — use for all VOXBULK transactional emails."""

from __future__ import annotations

import re

from app.services.brand_assets import BRAND_COLORS, BRAND_TAGLINE, email_logo_url

# Production logo URL (HTTPS, works in email clients — not data: URIs)
EMAIL_LOGO_URL = "https://api.voxbulk.com/public/brand/logo-black"


def email_logo_html(*, href: str = "https://voxbulk.com", width: int = 140) -> str:
    url = email_logo_url()
    return (
        f'<a href="{href}" style="text-decoration:none;display:inline-block;">'
        f'<img src="{url}" alt="VOXBULK" width="{width}" '
        f'style="display:block;border:0;outline:none;max-width:{width}px;height:auto;" />'
        f"</a>"
    )


EMAIL_PREFERENCES_MANAGE_URL = "https://dashboard.voxbulk.com/settings/profile#email-notifications"

# Standalone prefs paragraph we inject / strip (muted body style, not branded bottom strip).
_PREFS_BLOCK_RE = re.compile(
    r"(?is)<p\b[^>]*>\s*<a\b[^>]*>\s*(?:Manage Email Preferences|Change Preferences|Email preferences)\s*</a>\s*</p>\s*"
)
_CONTACT_LINE_RE = re.compile(
    r"(?is)<p\b[^>]*>[\s\S]*?"
    r"(?:Questions about this decision|Questions about|Contact us at|contact us at|"
    r"If you have questions|Questions\?|Need help\?|Need more help\?)"
    r"[\s\S]*?</p>"
)


def email_preferences_footer_html(*, manage_url: str | None = None) -> str:
    """Muted body-style prefs link (same theme as contact/help lines)."""
    href = (manage_url or EMAIL_PREFERENCES_MANAGE_URL).strip() or EMAIL_PREFERENCES_MANAGE_URL
    c = BRAND_COLORS
    return (
        f'<p style="margin:8px 0 0;font-size:13px;line-height:1.5;color:{c["ink_muted"]};">'
        f'<a href="{href}" style="color:{c["ink_muted"]};text-decoration:underline;">Manage Email Preferences</a>'
        f"</p>"
    )


def _strip_prefs_blocks(text: str) -> str:
    return _PREFS_BLOCK_RE.sub("", text)


def _insert_prefs_in_main_content(text: str, snippet: str) -> str:
    """Place prefs under contact/help copy inside the main body cell — not the bottom strip."""
    content_td = re.search(
        r'<td[^>]*style="[^"]*padding:\s*28px[^"]*"[^>]*>',
        text,
        flags=re.I,
    )
    if content_td:
        start = content_td.end()
        footer_mark = text.find("border-top:1px solid", start)
        search_end = footer_mark if footer_mark > 0 else len(text)
        close = text.rfind("</td>", start, search_end)
        if close > start:
            chunk = text[start:close]
            contacts = list(_CONTACT_LINE_RE.finditer(chunk))
            if contacts:
                insert_at = start + contacts[-1].end()
                return text[:insert_at] + snippet + text[insert_at:]
            return text[:close] + snippet + text[close:]

    contacts = list(_CONTACT_LINE_RE.finditer(text))
    if contacts:
        insert_at = contacts[-1].end()
        return text[:insert_at] + snippet + text[insert_at:]

    close_body = re.search(r"</body\s*>", text, flags=re.I)
    if close_body:
        return text[: close_body.start()] + snippet + text[close_body.start() :]
    return text + snippet


def inject_email_preferences_footer(body: str, *, manage_url: str | None = None) -> str:
    """Ensure Manage Email Preferences sits under body contact lines (idempotent)."""
    text = str(body or "")
    if not text.strip():
        return text
    # Relocate/restyle: remove prior injects (including wrong bottom-footer placement).
    text = _strip_prefs_blocks(text)
    # Upgrade any remaining legacy label that wasn't a standalone <p><a>…</a></p> block.
    text, _n = re.subn(
        r"(?i)>\s*Email preferences\s*<",
        ">Manage Email Preferences<",
        text,
        count=1,
    )
    if "manage email preferences" in text.lower() or "change preferences" in text.lower():
        return text
    snippet = email_preferences_footer_html(manage_url=manage_url)
    return _insert_prefs_in_main_content(text, snippet)


def wrap_brand_email(
    *,
    title: str,
    inner_html: str,
    footer: str = "Sent by VOXBULK · careers@voxbulk.com",
    badge: str | None = None,
) -> str:
    logo = email_logo_html()
    c = BRAND_COLORS
    tagline_html = (
        f'<p style="margin:8px 0 0;font-size:12px;color:{c["ink_muted"]};letter-spacing:0.02em;">'
        f"{BRAND_TAGLINE}</p>"
    )
    badge_html = ""
    if badge:
        badge_html = (
            f'<span style="float:right;font-size:11px;font-weight:600;letter-spacing:0.06em;'
            f'text-transform:uppercase;color:{c["ink_muted"]};padding-top:4px;">{badge}</span>'
        )
    # Prefs sit under body copy (e.g. contact/help lines), not in the bottom “Sent by” strip.
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:{c['background']};font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:{c['ink']};line-height:1.65;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{c['background']};padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:{c['surface']};border:1px solid {c['border']};border-radius:14px;overflow:hidden;">
          <tr>
            <td style="padding:24px 28px 12px;border-bottom:1px solid {c['border']};">
              {logo}
              {tagline_html}
              {badge_html}
            </td>
          </tr>
          <tr>
            <td style="padding:28px;">
              {inner_html}
            </td>
          </tr>
          <tr>
            <td style="padding:16px 28px 24px;border-top:1px solid {c['border']};font-size:12px;color:{c['ink_muted']};">
              {footer}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    return inject_email_preferences_footer(html)


def inject_brand_tagline(body: str) -> str | None:
    """Insert tagline under the VOXBULK logo when missing (preserves admin-edited copy)."""
    text = str(body or "")
    if not text or BRAND_TAGLINE in text:
        return None
    marker = 'alt="VOXBULK"'
    pos = text.find(marker)
    if pos < 0:
        return None
    close_a = text.find("</a>", pos)
    if close_a < 0:
        return None
    insert_at = close_a + len("</a>")
    c = BRAND_COLORS
    snippet = (
        f'<p style="margin:8px 0 0;font-size:12px;color:{c["ink_muted"]};letter-spacing:0.02em;">'
        f"{BRAND_TAGLINE}</p>"
    )
    return text[:insert_at] + snippet + text[insert_at:]


def cta_button(*, href: str, label: str) -> str:
    c = BRAND_COLORS
    return (
        f'<p style="margin:24px 0;">'
        f'<a href="{href}" style="display:inline-block;background:{c["primary"]};color:#ffffff;'
        f'padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:600;">{label}</a>'
        f"</p>"
    )


def _calendar_icon_url(name: str) -> str:
    """HTTPS PNG URLs for calendar buttons (avoid large data: URIs that break SMTP/HTML)."""
    from app.services.brand_assets import api_public_origin, public_brand_url

    return public_brand_url(api_public_origin(), f"{name}.png")


def calendar_links_html(*, google_url: str, outlook_url: str, ics_url: str) -> str:
    """Inline add-to-calendar links for interview confirmation/reminder emails."""
    c = BRAND_COLORS
    wrap = (
        f"margin:20px 0;padding:18px 16px;background:#f5f1ea;border-radius:12px;border:1px solid #e5e0d8;"
    )
    title = f'<p style="margin:0 0 14px;font-size:13px;font-weight:600;color:{c["ink"]};">Add to your calendar</p>'
    cell = "padding:0 6px 0 0;vertical-align:top;"
    link = (
        f"display:inline-block;min-width:96px;padding:12px 10px;border-radius:10px;"
        f"border:1px solid {c['border']};background:{c['surface']};color:{c['primary']};"
        f"text-decoration:none;font-size:12px;font-weight:600;line-height:1.25;text-align:center;"
    )
    icon = (
        "display:block;margin:0 auto 8px;width:32px;height:32px;border:0;outline:none;"
        "max-width:32px;max-height:32px;"
    )
    google_icon = _calendar_icon_url("calendar-google")
    outlook_icon = _calendar_icon_url("calendar-outlook")
    apple_icon = _calendar_icon_url("calendar-apple")
    return (
        f'<div style="{wrap}">{title}'
        f'<table role="presentation" cellspacing="0" cellpadding="0"><tr>'
        f'<td style="{cell}"><a href="{google_url}" style="{link}">'
        f'<img src="{google_icon}" width="32" height="32" alt="" style="{icon}" />Google</a></td>'
        f'<td style="{cell}"><a href="{outlook_url}" style="{link}">'
        f'<img src="{outlook_icon}" width="32" height="32" alt="" style="{icon}" />Outlook</a></td>'
        f'<td style="padding:0;vertical-align:top;"><a href="{ics_url}" style="{link}">'
        f'<img src="{apple_icon}" width="32" height="32" alt="" style="{icon}" />Apple / ICS</a></td>'
        f"</tr></table></div>"
    )
