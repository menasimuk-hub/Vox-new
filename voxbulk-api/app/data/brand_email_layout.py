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
