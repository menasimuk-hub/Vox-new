"""Shared styled QR PNG renderer (square/dots, rounded finders, arrow, frame round)."""

from __future__ import annotations

import io
import re
from typing import Any, Literal

import qrcode
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_M

ModuleStyle = Literal["square", "dots"]
CornerStyle = Literal["square", "rounded"]
FrameRound = Literal["none", "top", "all"]

MODULE_STYLES = frozenset({"square", "dots"})
CORNER_STYLES = frozenset({"square", "rounded"})
FRAME_ROUNDS = frozenset({"none", "top", "all"})


def normalize_module_style(raw: str | None) -> ModuleStyle:
    v = str(raw or "square").strip().lower()
    return "dots" if v == "dots" else "square"


def normalize_corner_style(raw: str | None) -> CornerStyle:
    v = str(raw or "square").strip().lower()
    return "rounded" if v == "rounded" else "square"


def normalize_frame_round(raw: str | None) -> FrameRound:
    v = str(raw or "none").strip().lower()
    if v in ("top", "all"):
        return v  # type: ignore[return-value]
    return "none"


def _hex_rgb(raw: str | None, default: str) -> tuple[int, int, int]:
    cleaned = re.sub(r"[^0-9a-fA-F]", "", str(raw or ""))
    if len(cleaned) == 3:
        cleaned = "".join(c * 2 for c in cleaned)
    if len(cleaned) != 6:
        cleaned = re.sub(r"[^0-9a-fA-F]", "", default)[:6].ljust(6, "0")
    return int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16)


def _arrow_band(n: int) -> tuple[int, int, int, int] | None:
    """Module band cleared for the arrow shaft (x0,y0,x1,y1 inclusive)."""
    if n < 21:
        return None
    cy = n // 2
    half_h = max(1, n // 18)
    y0 = max(8, cy - half_h)
    y1 = min(n - 9, cy + half_h)
    x0 = max(8, n // 5)
    x1 = n - 2
    if y1 < y0 or x1 < x0:
        return None
    return x0, y0, x1, y1


def _draw_module(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    module_px: int,
    fill: tuple,
    style: ModuleStyle,
) -> None:
    x0, y0 = x * module_px, y * module_px
    x1, y1 = x0 + module_px - 1, y0 + module_px - 1
    if style == "dots":
        pad = max(0, module_px // 8)
        draw.ellipse((x0 + pad, y0 + pad, x1 - pad, y1 - pad), fill=fill)
    else:
        draw.rectangle((x0, y0, x1, y1), fill=fill)


def _draw_rounded_finder(
    draw: ImageDraw.ImageDraw,
    *,
    x0: int,
    y0: int,
    module_px: int,
    fill: tuple,
    bg: tuple | None,
) -> None:
    """Draw one 7×7 finder as concentric rounded squares."""
    outer = (
        x0 * module_px,
        y0 * module_px,
        (x0 + 7) * module_px - 1,
        (y0 + 7) * module_px - 1,
    )
    rad_outer = max(2, module_px * 2)
    draw.rounded_rectangle(outer, radius=rad_outer, fill=fill)
    if bg is not None:
        mid = (
            (x0 + 1) * module_px,
            (y0 + 1) * module_px,
            (x0 + 6) * module_px - 1,
            (y0 + 6) * module_px - 1,
        )
        rad_mid = max(1, module_px)
        draw.rounded_rectangle(mid, radius=rad_mid, fill=bg)
    core = (
        (x0 + 2) * module_px,
        (y0 + 2) * module_px,
        (x0 + 5) * module_px - 1,
        (y0 + 5) * module_px - 1,
    )
    rad_core = max(1, module_px)
    draw.rounded_rectangle(core, radius=rad_core, fill=fill)


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    *,
    band: tuple[int, int, int, int],
    module_px: int,
    fill: tuple,
    overhang_px: int,
) -> None:
    x0, y0, x1, y1 = band
    left = x0 * module_px
    right = (x1 + 1) * module_px
    top = y0 * module_px
    bottom = (y1 + 1) * module_px
    mid_y = (top + bottom) // 2
    thickness = max(2, (bottom - top) * 2 // 3)
    shaft_top = mid_y - thickness // 2
    shaft_bot = mid_y + thickness // 2
    head_w = max(module_px * 3, overhang_px)
    shaft_end = right - head_w // 2
    tip_x = right + overhang_px
    draw.rectangle((left, shaft_top, shaft_end, shaft_bot), fill=fill)
    draw.polygon(
        [
            (shaft_end - module_px, top - thickness // 4),
            (tip_x, mid_y),
            (shaft_end - module_px, bottom + thickness // 4),
        ],
        fill=fill,
    )


def _apply_frame_mask(img: Image.Image, frame: FrameRound, bg_rgba: tuple[int, int, int, int]) -> Image.Image:
    if frame == "none":
        return img
    w, h = img.size
    radius = max(8, min(w, h) // 10)
    mask = Image.new("L", (w, h), 0)
    mdraw = ImageDraw.Draw(mask)
    if frame == "all":
        mdraw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    else:
        # top corners rounded: draw full rect then punch square bottoms... 
        # simpler: rounded_rectangle then re-fill bottom corners as opaque square
        mdraw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
        mdraw.rectangle((0, h - radius - 1, radius + 1, h - 1), fill=255)
        mdraw.rectangle((w - radius - 1, h - radius - 1, w - 1, h - 1), fill=255)

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    out = Image.new("RGBA", (w, h), bg_rgba)
    out.paste(img, (0, 0))
    # Apply mask to alpha
    r, g, b, a = out.split()
    a = Image.composite(a, Image.new("L", (w, h), 0), mask)
    return Image.merge("RGBA", (r, g, b, a))


def render_styled_qr_png(
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
    """Return PNG bytes for a styled QR."""
    payload = str(data or "").strip() or "https://voxbulk.com"
    mod = normalize_module_style(module_style)
    cor = normalize_corner_style(corner_style)
    frame = normalize_frame_round(frame_round)
    arrow = bool(show_arrow)

    ec = ERROR_CORRECT_H if arrow else ERROR_CORRECT_M
    qr = qrcode.QRCode(
        version=None,
        error_correction=ec,
        box_size=10,
        border=max(0, int(border)),
    )
    qr.add_data(payload)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    # qrcode matrix includes quiet-zone border; work on full matrix
    n = len(matrix)
    # Finder positions are relative to the QR module grid including border offset.
    # Quiet zone is `border` modules on each side; finders sit at border offset.
    b = max(0, int(border))
    core_n = n - 2 * b

    target = max(64, min(2048, int(size or 512)))
    overhang_modules = 4 if arrow else 0
    total_modules_w = n + overhang_modules
    module_px = max(1, target // total_modules_w)
    pixel_w = total_modules_w * module_px
    pixel_h = n * module_px
    overhang_px = overhang_modules * module_px

    fg = _hex_rgb(fg_hex, "000000")
    bg = _hex_rgb(bg_hex, "ffffff")

    if transparent:
        img = Image.new("RGBA", (pixel_w, pixel_h), (0, 0, 0, 0))
        fill: tuple = fg + (255,)
        bg_fill: tuple | None = None
        knockout: tuple = (0, 0, 0, 0)
    else:
        img = Image.new("RGB", (pixel_w, pixel_h), bg)
        fill = fg
        bg_fill = bg
        knockout = bg

    draw = ImageDraw.Draw(img)

    band = None
    if arrow and core_n >= 21:
        ax0, ay0, ax1, ay1 = _arrow_band(core_n)  # type: ignore[misc]
        # Shift into full matrix coords (quiet zone offset)
        band = (ax0 + b, ay0 + b, ax1 + b, ay1 + b)

    # Clear arrow band first
    if band is not None:
        x0, y0, x1, y1 = band
        draw.rectangle(
            (x0 * module_px, y0 * module_px, (x1 + 1) * module_px - 1, (y1 + 1) * module_px - 1),
            fill=knockout,
        )

    # Draw modules, skipping finders when rounded (drawn separately) and arrow band
    finder_set = set()
    if cor == "rounded":
        for fx0, fy0, fx1, fy1 in [
            (b, b, b + 6, b + 6),
            (b + core_n - 7, b, b + core_n - 1, b + 6),
            (b, b + core_n - 7, b + 6, b + core_n - 1),
        ]:
            for yy in range(fy0, fy1 + 1):
                for xx in range(fx0, fx1 + 1):
                    finder_set.add((xx, yy))

    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if not dark:
                continue
            if (x, y) in finder_set:
                continue
            if band is not None:
                bx0, by0, bx1, by1 = band
                if bx0 <= x <= bx1 and by0 <= y <= by1:
                    continue
            _draw_module(draw, x=x, y=y, module_px=module_px, fill=fill, style=mod)

    if cor == "rounded":
        for fx, fy in [(b, b), (b + core_n - 7, b), (b, b + core_n - 7)]:
            _draw_rounded_finder(draw, x0=fx, y0=fy, module_px=module_px, fill=fill, bg=bg_fill if bg_fill is not None else (255, 255, 255, 255))

    if band is not None:
        _draw_arrow(draw, band=band, module_px=module_px, fill=fill, overhang_px=overhang_px)

    # Scale to target height while keeping aspect (arrow may make it wider)
    if pixel_h != target:
        new_w = max(1, int(round(pixel_w * (target / pixel_h))))
        img = img.resize((new_w, target), Image.Resampling.NEAREST)

    if frame != "none":
        bg_rgba = (0, 0, 0, 0) if transparent else (*bg, 255)
        img = _apply_frame_mask(img, frame, bg_rgba)
        if not transparent and img.mode == "RGBA":
            # Flatten onto bg for opaque downloads
            flat = Image.new("RGB", img.size, bg)
            flat.paste(img, mask=img.split()[3])
            img = flat

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


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
    """Back-compat alias used by Smart Card tests/callers."""
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


def style_kwargs_from_row(row: Any) -> dict[str, Any]:
    return {
        "fg_hex": getattr(row, "qr_fg_color", None) or "000000",
        "bg_hex": getattr(row, "qr_bg_color", None) or "ffffff",
        "transparent": bool(getattr(row, "qr_transparent", False)),
        "module_style": getattr(row, "qr_module_style", None) or "square",
        "corner_style": getattr(row, "qr_corner_style", None) or "square",
        "show_arrow": bool(getattr(row, "qr_show_arrow", False)),
        "frame_round": getattr(row, "qr_frame_round", None) or "none",
    }


def merge_style_query_overrides(
    base: dict[str, Any],
    *,
    fg: str | None = None,
    bg: str | None = None,
    t: str | None = None,
    m: str | None = None,
    c: str | None = None,
    a: str | None = None,
    f: str | None = None,
) -> dict[str, Any]:
    out = dict(base)
    if fg is not None and str(fg).strip():
        out["fg_hex"] = str(fg).strip().lstrip("#")
    if bg is not None and str(bg).strip():
        out["bg_hex"] = str(bg).strip().lstrip("#")
    if t is not None and str(t).strip() != "":
        out["transparent"] = str(t).strip() in ("1", "true", "True", "yes")
    if m is not None and str(m).strip():
        out["module_style"] = normalize_module_style(m)
    if c is not None and str(c).strip():
        out["corner_style"] = normalize_corner_style(c)
    if a is not None and str(a).strip() != "":
        out["show_arrow"] = str(a).strip() in ("1", "true", "True", "yes")
    if f is not None and str(f).strip():
        out["frame_round"] = normalize_frame_round(f)
    return out


def build_qr_png_url(
    *,
    api_origin: str,
    path: str,
    fg: str = "000000",
    bg: str = "ffffff",
    transparent: bool = False,
    module_style: str = "square",
    corner_style: str = "square",
    show_arrow: bool = False,
    frame_round: str = "none",
    size: int = 512,
) -> str:
    api = (api_origin or "").rstrip("/") or "https://api.voxbulk.com"
    fg_c = re.sub(r"[^0-9a-fA-F]", "", fg or "000000")[:6] or "000000"
    bg_c = re.sub(r"[^0-9a-fA-F]", "", bg or "ffffff")[:6] or "ffffff"
    m = normalize_module_style(module_style)
    c = normalize_corner_style(corner_style)
    fr = normalize_frame_round(frame_round)
    tr = "1" if transparent else "0"
    ar = "1" if show_arrow else "0"
    p = path if path.startswith("/") else f"/{path}"
    return f"{api}{p}?fg={fg_c}&bg={bg_c}&t={tr}&m={m}&c={c}&a={ar}&f={fr}&s={int(size)}"
