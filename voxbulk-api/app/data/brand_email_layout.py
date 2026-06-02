"""Shared branded HTML email wrapper — use for all VOXBULK transactional emails."""

from __future__ import annotations

from app.services.brand_assets import BRAND_COLORS, email_logo_url

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


def wrap_brand_email(*, title: str, inner_html: str, footer: str = "Sent by VOXBULK · careers@voxbulk.com") -> str:
    logo = email_logo_html()
    c = BRAND_COLORS
    return f"""<!DOCTYPE html>
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


def cta_button(*, href: str, label: str) -> str:
    c = BRAND_COLORS
    return (
        f'<p style="margin:24px 0;">'
        f'<a href="{href}" style="display:inline-block;background:{c["primary"]};color:#ffffff;'
        f'padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:600;">{label}</a>'
        f"</p>"
    )


def _calendar_icon_url(name: str) -> str:
    """PNG icons for confirmation emails — same pattern as EMAIL_LOGO_URL (our API, not SVG/CDN)."""
    from app.services.brand_assets import asset_data_uri, public_brand_url

    data = asset_data_uri(name)
    if data:
        return data
    return public_brand_url("https://api.voxbulk.com", name)


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
        f'<div style="{wrap}">'
        f"{title}"
        f'<table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0;">'
        f"<tr>"
        f'<td style="{cell}">'
        f'<a href="{google_url}" style="{link}">'
        f'<img src="{google_icon}" alt="Google Calendar" width="32" height="32" style="{icon}" />'
        f"Google Calendar</a></td>"
        f'<td style="{cell}">'
        f'<a href="{outlook_url}" style="{link}">'
        f'<img src="{outlook_icon}" alt="Outlook" width="32" height="32" style="{icon}" />'
        f"Outlook</a></td>"
        f'<td style="{cell}">'
        f'<a href="{ics_url}" style="{link}">'
        f'<img src="{apple_icon}" alt="Apple Calendar" width="32" height="32" style="{icon}" />'
        f"Apple / .ics</a></td>"
        f"</tr></table></div>"
    )
