"""Shared styled QR PNG renderer (square/dots, rounded/circle finders, frame round)."""

from __future__ import annotations

import io
import re
from typing import Any, Literal

import qrcode
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_M

ModuleStyle = Literal["square", "dots"]
CornerStyle = Literal["square", "rounded"]
FrameRound = Literal["none", "top", "all"]
FinderShape = Literal["square", "rounded", "circle"]

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


def _finder_shape(module_style: ModuleStyle, corner_style: CornerStyle) -> FinderShape:
    """Dots modules → circular finders; otherwise square or rounded."""
    if module_style == "dots":
        return "circle"
    if corner_style == "rounded":
        return "rounded"
    return "square"


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
        pad = max(1, int(module_px * 0.22))
        draw.ellipse((x0 + pad, y0 + pad, x1 - pad, y1 - pad), fill=fill)
    else:
        draw.rectangle((x0, y0, x1, y1), fill=fill)


def _punch_shape(
    img: Image.Image,
    box: tuple[int, int, int, int],
    *,
    shape: FinderShape,
    radius: int = 0,
) -> Image.Image:
    """Clear alpha inside box so the finder middle ring is truly hollow."""
    if img.mode != "RGBA":
        return img
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    if shape == "circle":
        md.ellipse(box, fill=255)
    elif shape == "rounded":
        md.rounded_rectangle(box, radius=max(1, radius), fill=255)
    else:
        md.rectangle(box, fill=255)
    r, g, b, a = img.split()
    a = Image.composite(Image.new("L", img.size, 0), a, mask)
    return Image.merge("RGBA", (r, g, b, a))


def _draw_finder(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    x0: int,
    y0: int,
    module_px: int,
    fill: tuple,
    bg_fill: tuple | None,
    shape: FinderShape,
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Draw one 7×7 finder: outer ring + hollow middle + solid centre.

    When bg_fill is None (transparent QR), the middle ring is punched clear —
    never filled with white — so white-on-transparent finders stay scannable.
    """
    px0 = x0 * module_px
    py0 = y0 * module_px
    outer = (px0, py0, px0 + 7 * module_px - 1, py0 + 7 * module_px - 1)
    mid = (
        px0 + module_px,
        py0 + module_px,
        px0 + 6 * module_px - 1,
        py0 + 6 * module_px - 1,
    )
    core = (
        px0 + 2 * module_px,
        py0 + 2 * module_px,
        px0 + 5 * module_px - 1,
        py0 + 5 * module_px - 1,
    )
    rad_o = max(2, module_px * 2)
    rad_m = max(1, module_px)
    rad_c = max(1, module_px)

    if shape == "circle":
        if bg_fill is not None:
            draw.ellipse(outer, fill=fill)
            draw.ellipse(mid, fill=bg_fill)
            draw.ellipse(core, fill=fill)
        else:
            draw.ellipse(outer, fill=fill)
            img = _punch_shape(img, mid, shape="circle")
            draw = ImageDraw.Draw(img)
            draw.ellipse(core, fill=fill)
        return img, draw

    if shape == "rounded":
        if bg_fill is not None:
            draw.rounded_rectangle(outer, radius=rad_o, fill=fill)
            draw.rounded_rectangle(mid, radius=rad_m, fill=bg_fill)
            draw.rounded_rectangle(core, radius=rad_c, fill=fill)
        else:
            draw.rounded_rectangle(outer, radius=rad_o, fill=fill)
            img = _punch_shape(img, mid, shape="rounded", radius=rad_m)
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle(core, radius=rad_c, fill=fill)
        return img, draw

    # square
    if bg_fill is not None:
        draw.rectangle(outer, fill=fill)
        draw.rectangle(mid, fill=bg_fill)
        draw.rectangle(core, fill=fill)
    else:
        draw.rectangle(outer, fill=fill)
        img = _punch_shape(img, mid, shape="square")
        draw = ImageDraw.Draw(img)
        draw.rectangle(core, fill=fill)
    return img, draw


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
    r = max(0, min(radius, (x1 - x0) // 2, (y1 - y0) // 2))
    if fill is not None:
        draw.rectangle((x0, y0 + r, x1, y1), fill=fill)
        draw.rectangle((x0 + r, y0, x1 - r, y0 + r), fill=fill)
        draw.pieslice((x0, y0, x0 + 2 * r, y0 + 2 * r), 180, 270, fill=fill)
        draw.pieslice((x1 - 2 * r, y0, x1, y0 + 2 * r), 270, 360, fill=fill)
    if outline is not None and width > 0:
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
    show_arrow: bool = False,  # kept for API compat; ignored (arrow removed)
    frame_round: str | None = "none",
) -> bytes:
    """Return PNG bytes for a styled QR."""
    del show_arrow  # arrow option removed
    payload = str(data or "").strip() or "https://voxbulk.com"
    mod = normalize_module_style(module_style)
    cor = normalize_corner_style(corner_style)
    frame = normalize_frame_round(frame_round)
    shape = _finder_shape(mod, cor)

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
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
    module_px = max(4, target // max(n, 1))
    pixel = n * module_px

    fg = _hex_rgb(fg_hex, "000000")
    bg = _hex_rgb(bg_hex, "ffffff")

    if transparent:
        img = Image.new("RGBA", (pixel, pixel), (0, 0, 0, 0))
        fill: tuple = fg + (255,)
        bg_fill: tuple | None = None
    else:
        img = Image.new("RGB", (pixel, pixel), bg)
        fill = fg
        bg_fill = bg

    draw = ImageDraw.Draw(img)

    finder_set: set[tuple[int, int]] = set()
    finder_origins = [
        (b, b),
        (b + core_n - 7, b),
        (b, b + core_n - 7),
    ]
    for fx, fy in finder_origins:
        for yy in range(fy, fy + 7):
            for xx in range(fx, fx + 7):
                finder_set.add((xx, yy))

    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if not dark or (x, y) in finder_set:
                continue
            _draw_module(draw, x=x, y=y, module_px=module_px, fill=fill, style=mod)

    for fx, fy in finder_origins:
        img, draw = _draw_finder(
            img,
            draw,
            x0=fx,
            y0=fy,
            module_px=module_px,
            fill=fill,
            bg_fill=bg_fill,
            shape=shape,
        )

    if pixel != target:
        img = img.resize((target, target), Image.Resampling.LANCZOS)

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
    return render_styled_qr_png(
        data,
        fg_hex=fg_hex,
        bg_hex=bg_hex,
        transparent=transparent,
        size=size,
        border=border,
        module_style=module_style,
        corner_style=corner_style,
        show_arrow=False,
        frame_round=frame_round,
    )


def style_kwargs_from_row(row: Any) -> dict[str, Any]:
    return {
        "fg_hex": getattr(row, "qr_fg_color", None) or "000000",
        "bg_hex": getattr(row, "qr_bg_color", None) or "ffffff",
        "transparent": bool(getattr(row, "qr_transparent", False)),
        "module_style": getattr(row, "qr_module_style", None) or "square",
        "corner_style": getattr(row, "qr_corner_style", None) or "square",
        "show_arrow": False,
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
    del a  # arrow removed
    out = dict(base)
    out["show_arrow"] = False
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
    del show_arrow
    api = (api_origin or "").rstrip("/") or "https://api.voxbulk.com"
    fg_c = re.sub(r"[^0-9a-fA-F]", "", fg or "000000")[:6] or "000000"
    bg_c = re.sub(r"[^0-9a-fA-F]", "", bg or "ffffff")[:6] or "ffffff"
    m = normalize_module_style(module_style)
    c = normalize_corner_style(corner_style)
    fr = normalize_frame_round(frame_round)
    tr = "1" if transparent else "0"
    p = path if path.startswith("/") else f"/{path}"
    return f"{api}{p}?fg={fg_c}&bg={bg_c}&t={tr}&m={m}&c={c}&a=0&f={fr}&s={int(size)}"
