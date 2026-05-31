"""Shared HTML email layout — dashboard beige + navy theme."""

from __future__ import annotations

from app.services.brand_assets import BRAND_COLORS, logo_data_uri


def wrap_interview_email(*, title: str, inner_html: str) -> str:
    logo_uri = logo_data_uri(variant="logo-black") or ""
    logo_img = (
        f'<img src="{logo_uri}" alt="VOXBULK" style="height:32px;width:auto;display:block;" />'
        if logo_uri
        else '<span style="font-size:18px;font-weight:700;color:#1a2d5c;">VOXBULK</span>'
    )
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
              {logo_img}
            </td>
          </tr>
          <tr>
            <td style="padding:28px;">
              {inner_html}
            </td>
          </tr>
          <tr>
            <td style="padding:16px 28px 24px;border-top:1px solid {c['border']};font-size:12px;color:{c['ink_muted']};">
              Sent by VOXBULK · careers@voxbulk.com
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
