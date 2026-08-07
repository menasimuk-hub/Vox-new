"""Generate Smart Card QR PNGs with optional true transparent background."""

from __future__ import annotations

import io
import re
from typing import Any

import qrcode
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_M


def _hex_rgb(raw: str | None, default: str) -> tuple[int, int, int]:
    cleaned = re.sub(r"[^0-9a-fA-F]", "", str(raw or ""))
    if len(cleaned) == 3:
        cleaned = "".join(c * 2 for c in cleaned)
    if len(cleaned) != 6:
        cleaned = re.sub(r"[^0-9a-fA-F]", "", default)[:6].ljust(6, "0")
    return int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16)


def render_smart_card_qr_png(
    data: str,
    *,
    fg_hex: str | None = "000000",
    bg_hex: str | None = "ffffff",
    transparent: bool = False,
    size: int = 512,
    border: int = 2,
) -> bytes:
    """Return PNG bytes. When transparent=True, background alpha is 0 (no solid fill)."""
    payload = str(data or "").strip() or "https://voxbulk.com"
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=max(0, int(border)),
    )
    qr.add_data(payload)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    modules = len(matrix)
    target = max(64, min(2048, int(size or 512)))
    module_px = max(1, target // modules)
    pixel = modules * module_px

    fg = _hex_rgb(fg_hex, "000000")
    if transparent:
        img = Image.new("RGBA", (pixel, pixel), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        fill = fg + (255,)
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    x0, y0 = x * module_px, y * module_px
                    draw.rectangle((x0, y0, x0 + module_px - 1, y0 + module_px - 1), fill=fill)
    else:
        bg = _hex_rgb(bg_hex, "ffffff")
        img = Image.new("RGB", (pixel, pixel), bg)
        draw = ImageDraw.Draw(img)
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    x0, y0 = x * module_px, y * module_px
                    draw.rectangle((x0, y0, x0 + module_px - 1, y0 + module_px - 1), fill=fg)

    if img.size[0] != target:
        img = img.resize((target, target), Image.Resampling.NEAREST)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_rep_qr_png(rep: Any, *, size: int = 512) -> bytes:
    from app.services.smart_card.company_service import SmartCardCompanyService

    url = SmartCardCompanyService.public_web_url(str(getattr(rep, "qr_token", "") or ""))
    return render_smart_card_qr_png(
        url,
        fg_hex=getattr(rep, "qr_fg_color", None) or "000000",
        bg_hex=getattr(rep, "qr_bg_color", None) or "ffffff",
        transparent=bool(getattr(rep, "qr_transparent", False)),
        size=size,
    )
