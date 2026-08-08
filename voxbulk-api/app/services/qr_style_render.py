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


def _right_arrow_clear(n: int, border: int) -> tuple[int, int, int, int] | None:
    """Short clear band on the right edge of the data area (full-matrix coords)."""
    core = n - 2 * border
    if core < 21:
        return None
    cy = border + core // 2
    # Thin vertical clear strip near the right finder-safe edge
    half_h = max(2, core // 14)
    y0 = max(border + 8, cy - half_h)
    y1 = min(border + core - 9, cy + half_h)
    # Short shaft zone — only rightmost ~3 modules of core (not across whole QR)
    x1 = border + core - 2
    x0 = max(border + 8, x1 - 3)
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
        # Clear circular gaps — ~55% diameter so dots read as circles, not squares
        pad = max(1, int(module_px * 0.22))
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


def _draw_line_arrow(
    draw: ImageDraw.ImageDraw,
    *,
    clear: tuple[int, int, int, int],
    module_px: int,
    fill: tuple,
    qr_right_px: int,
    overhang_px: int,
) -> None:
    """Thin shaft inside the QR + chevron head outside (line-art, right-pointing)."""
    x0, y0, x1, y1 = clear
    mid_y = ((y0 + y1 + 1) * module_px) // 2
    # Shaft: short horizontal line in the cleared zone, stop before the outer edge
    shaft_left = x0 * module_px + module_px // 2
    shaft_right = qr_right_px - max(2, module_px // 3)
    stroke = max(2, module_px // 3)
    draw.line((shaft_left, mid_y, shaft_right, mid_y), fill=fill, width=stroke)

    # Chevron head outside the QR box
    tip_x = qr_right_px + overhang_px - max(2, module_px // 4)
    head_back = qr_right_px + max(2, overhang_px // 5)
    head_h = max(module_px * 2, overhang_px // 2)
    draw.line((head_back, mid_y - head_h, tip_x, mid_y), fill=fill, width=stroke)
    draw.line((head_back, mid_y + head_h, tip_x, mid_y), fill=fill, width=stroke)
    # Join shaft to head
    draw.line((shaft_right, mid_y, head_back, mid_y), fill=fill, width=stroke)


def _draw_frame_rect(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    frame: FrameRound,
    radius: int,
    fill: Any = None,
    outline: Any = None,
    width: int = 1,
) -> None:
    """Rounded rect; for frame=top only NW/NE are rounded."""
    x0, y0, x1, y1 = box
    if frame == "all":
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
        return
    if frame == "none":
        draw.rectangle(box, fill=fill, outline=outline, width=width)
        return
    # top only: round top, square bottom
    r = max(0, min(radius, (x1 - x0) // 2, (y1 - y0) // 2))
    if fill is not None:
        draw.rectangle((x0, y0 + r, x1, y1), fill=fill)
        draw.rectangle((x0 + r, y0, x1 - r, y0 + r), fill=fill)
        draw.pieslice((x0, y0, x0 + 2 * r, y0 + 2 * r), 180, 270, fill=fill)
        draw.pieslice((x1 - 2 * r, y0, x1, y0 + 2 * r), 270, 360, fill=fill)
    if outline is not None and width > 0:
        # Stroke as a slightly inset path approximation
        for i in range(width):
            ox0, oy0, ox1, oy1 = x0 + i, y0 + i, x1 - i, y1 - i
            orad = max(0, r - i)
            draw.arc((ox0, oy0, ox0 + 2 * orad, oy0 + 2 * orad), 180, 270, fill=outline, width=1)
            draw.arc((ox1 - 2 * orad, oy0, ox1, oy0 + 2 * orad), 270, 360, fill=outline, width=1)
            draw.line((ox0 + orad, oy0, ox1 - orad, oy0), fill=outline, width=1)
            draw.line((ox0, oy0 + orad, ox0, oy1), fill=outline, width=1)
            draw.line((ox1, oy0 + orad, ox1, oy1), fill=outline, width=1)
            draw.line((ox0, oy1, ox1, oy1), fill=outline, width=1)


def _apply_visible_frame(
    img: Image.Image,
    frame: FrameRound,
    *,
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
    transparent: bool,
    pad: int,
    stroke: int,
) -> Image.Image:
    """Pad canvas and draw a visible rounded border so frame style is obvious."""
    if frame == "none":
        return img
    w, h = img.size
    radius = max(14, min(w, h) // 8)
    out_w, out_h = w + 2 * pad, h + 2 * pad
    if transparent:
        out = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
        content = img.convert("RGBA") if img.mode != "RGBA" else img
    else:
        out = Image.new("RGB", (out_w, out_h), bg)
        content = img.convert("RGB") if img.mode == "RGBA" else img

    mask = Image.new("L", (w, h), 0)
    _draw_frame_rect(
        ImageDraw.Draw(mask),
        (0, 0, w - 1, h - 1),
        frame=frame,
        radius=max(8, radius - 4),
        fill=255,
    )
    if transparent:
        layered = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        layered.paste(content, (0, 0))
        r, g, b, a = layered.split()
        a = Image.composite(a, Image.new("L", (w, h), 0), mask)
        clipped = Image.merge("RGBA", (r, g, b, a))
        out.paste(clipped, (pad, pad), clipped)
    else:
        plate = Image.new("RGB", (w, h), bg)
        plate.paste(content, (0, 0))
        out.paste(plate, (pad, pad), mask)

    draw = ImageDraw.Draw(out)
    inset = max(1, stroke // 2)
    box = (inset, inset, out_w - 1 - inset, out_h - 1 - inset)
    stroke_fill: Any = (*fg, 255) if transparent else fg
    _draw_frame_rect(
        draw,
        box,
        frame=frame,
        radius=radius,
        outline=stroke_fill,
        width=max(2, stroke),
    )
    return out


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
    n = len(matrix)
    b = max(0, int(border))
    core_n = n - 2 * b

    target = max(64, min(2048, int(size or 512)))
    # Head hangs outside the QR square on the right
    overhang_modules = 5 if arrow else 0
    total_modules_w = n + overhang_modules
    # Prefer crisp modules before any optional scale
    module_px = max(4, target // max(n, 1))
    pixel_w = total_modules_w * module_px
    pixel_h = n * module_px
    overhang_px = overhang_modules * module_px
    qr_right_px = n * module_px

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

    clear = _right_arrow_clear(n, b) if arrow else None
    # Expand clear vertically a bit for breathing room around the shaft
    if clear is not None:
        x0, y0, x1, y1 = clear
        pad_y = 1
        y0 = max(b + 7, y0 - pad_y)
        y1 = min(b + core_n - 8, y1 + pad_y)
        clear = (x0, y0, x1, y1)
        draw.rectangle(
            (x0 * module_px, y0 * module_px, (x1 + 1) * module_px - 1, (y1 + 1) * module_px - 1),
            fill=knockout,
        )

    finder_set: set[tuple[int, int]] = set()
    # Keep finders solid (square or rounded) even when modules are dots — better scan + clearer style
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
            if clear is not None:
                cx0, cy0, cx1, cy1 = clear
                if cx0 <= x <= cx1 and cy0 <= y <= cy1:
                    continue
            _draw_module(draw, x=x, y=y, module_px=module_px, fill=fill, style=mod)

    if cor == "rounded":
        for fx, fy in [(b, b), (b + core_n - 7, b), (b, b + core_n - 7)]:
            _draw_rounded_finder(
                draw,
                x0=fx,
                y0=fy,
                module_px=module_px,
                fill=fill,
                bg=bg_fill if bg_fill is not None else (255, 255, 255, 255),
            )
    else:
        # Solid square finders (not dotted)
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark and (x, y) in finder_set:
                    x0, y0 = x * module_px, y * module_px
                    draw.rectangle(
                        (x0, y0, x0 + module_px - 1, y0 + module_px - 1),
                        fill=fill,
                    )

    if clear is not None:
        _draw_line_arrow(
            draw,
            clear=clear,
            module_px=module_px,
            fill=fill,
            qr_right_px=qr_right_px,
            overhang_px=overhang_px,
        )

    # Scale height to target; keep arrow overhang aspect
    if pixel_h != target:
        new_w = max(1, int(round(pixel_w * (target / pixel_h))))
        # Bilinear keeps circles smoother than nearest-neighbour
        img = img.resize((new_w, target), Image.Resampling.LANCZOS)

    if frame != "none":
        pad = max(10, target // 28)
        stroke = max(3, target // 64)
        img = _apply_visible_frame(
            img,
            frame,
            fg=fg,
            bg=bg,
            transparent=transparent,
            pad=pad,
            stroke=stroke,
        )

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
