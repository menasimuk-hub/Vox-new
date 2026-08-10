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

# Rule: every branded HTML email gets Manage Email Preferences in the last footer
# card (under "Sent via/by VOXBULK …"), same muted 12px theme — never mid-body.
_PREFS_BLOCK_RE = re.compile(
    r"(?is)<p\b[^>]*>\s*<a\b[^>]*>\s*(?:Manage Email Preferences|Change Preferences|Email preferences)\s*</a>\s*</p>\s*"
)
_PREFS_ANCHOR_RE = re.compile(
    r"(?is)<a\b[^>]*>\s*(?:Manage Email Preferences|Change Preferences|Email preferences)\s*</a>"
)
_SENT_FOOTER_RE = re.compile(
    r"(?is)(Sent\s+(?:via|by)\s+VOXBULK[^\n<]*)",
)
_QUESTIONS_LINE_RE = re.compile(
    r"(?is)(<p\b[^>]*>[\s\S]*?"
    r"(?:Questions\?\s*Contact|Questions about[\s\S]*?Contact us)"
    r"[\s\S]*?</p>)",
)


def email_preferences_footer_html(*, manage_url: str | None = None) -> str:
    """Muted 12px link matching the Sent via / Sent by footer strip (all products)."""
    href = (manage_url or EMAIL_PREFERENCES_MANAGE_URL).strip() or EMAIL_PREFERENCES_MANAGE_URL
    c = BRAND_COLORS
    return (
        f'<p style="margin:8px 0 0;font-size:12px;line-height:1.5;color:{c["ink_muted"]};">'
        f'<a href="{href}" style="color:{c["ink_muted"]};text-decoration:underline;">Manage Email Preferences</a>'
        f"</p>"
    )


def _strip_prefs_blocks(text: str) -> str:
    return _PREFS_BLOCK_RE.sub("", text)


def _prefs_in_last_footer_card(text: str) -> bool:
    footer_mark = text.rfind("border-top:1px solid")
    if footer_mark < 0:
        return False
    td_close = text.find("</td>", footer_mark)
    if td_close < 0:
        return False
    cell = text[footer_mark:td_close].lower()
    return "manage email preferences" in cell or "change preferences" in cell


def _insert_prefs_in_last_cards(text: str, snippet: str) -> str:
    """
    Place prefs in the last email cards for every product template:
    1) Preferred — under "Sent via/by VOXBULK …" in the bottom footer strip
    2) Fallback — under a trailing "Questions? Contact …" line
    3) Else — before </body>
    """
    footer_mark = text.rfind("border-top:1px solid")
    if footer_mark >= 0:
        td_close = text.find("</td>", footer_mark)
        if td_close > footer_mark:
            cell = text[footer_mark:td_close]
            sent = _SENT_FOOTER_RE.search(cell)
            if sent:
                abs_at = footer_mark + sent.end()
                return text[:abs_at] + snippet + text[abs_at:]
            return text[:td_close] + snippet + text[td_close:]

    questions = list(_QUESTIONS_LINE_RE.finditer(text))
    if questions:
        insert_at = questions[-1].end()
        return text[:insert_at] + snippet + text[insert_at:]

    close_body = re.search(r"</body\s*>", text, flags=re.I)
    if close_body:
        return text[: close_body.start()] + snippet + text[close_body.start() :]
    return text + snippet


def inject_email_preferences_footer(body: str, *, manage_url: str | None = None) -> str:
    """Idempotent: prefs link always lives in the last footer card (all emails)."""
    text = str(body or "")
    if not text.strip():
        return text
    text = _strip_prefs_blocks(text)
    if _prefs_in_last_footer_card(text):
        return text
    # Remove leftover mid-body / wrong-place anchors then re-insert in the footer card.
    text = _PREFS_ANCHOR_RE.sub("", text)
    snippet = email_preferences_footer_html(manage_url=manage_url)
    return _insert_prefs_in_last_cards(text, snippet)


def wrap_brand_email(
    *,
    title: str,
    inner_html: str,
    footer: str = "Sent by VOXBULK · careers@voxbulk.com",
    badge: str | None = None,
) -> str:
    """Build a branded email. Always includes Manage Email Preferences under the Sent footer."""
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
