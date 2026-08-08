"""Generate Smart Card QR PNGs (delegates to shared styled renderer)."""

from __future__ import annotations

from typing import Any

from app.services.qr_style_render import render_styled_qr_png, style_kwargs_from_row


def render_smart_card_qr_png(
    data: str,
    *,
    fg_hex: str | None = "000000",
    bg_hex: str | None = "ffffff",
    transparent: bool = False,
    size: int = 512,
    border: int = 2,
    module_style: str | None = "square",
    corner_style: str | None = "square",
    show_arrow: bool = False,
    frame_round: str | None = "none",
) -> bytes:
    return render_styled_qr_png(
        data,
        fg_hex=fg_hex,
        bg_hex=bg_hex,
        transparent=transparent,
        size=size,
        border=border,
        module_style=module_style,
        corner_style=corner_style,
        show_arrow=show_arrow,
        frame_round=frame_round,
    )


def render_rep_qr_png(rep: Any, *, size: int = 512, **overrides: Any) -> bytes:
    from app.services.smart_card.company_service import SmartCardCompanyService

    url = SmartCardCompanyService.public_web_url(str(getattr(rep, "qr_token", "") or ""))
    kwargs = style_kwargs_from_row(rep)
    kwargs.update({k: v for k, v in overrides.items() if v is not None})
    return render_smart_card_qr_png(url, size=size, **kwargs)
