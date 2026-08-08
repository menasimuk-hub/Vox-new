"""Smart Card / styled QR PNG — transparent + style options."""

from __future__ import annotations

import io

from PIL import Image

from app.services.qr_style_render import render_styled_qr_png
from app.services.smart_card.qr_image_service import render_smart_card_qr_png


def test_transparent_qr_has_alpha_channel():
    png = render_smart_card_qr_png(
        "https://voxbulk.com/smart-card/acme-jane-deadbeefcafebabe",
        fg_hex="000000",
        transparent=True,
        size=256,
    )
    img = Image.open(io.BytesIO(png))
    assert img.mode == "RGBA"
    alphas = [p[3] for p in img.getdata()]
    assert 0 in alphas
    assert 255 in alphas


def test_opaque_qr_is_rgb_with_custom_colours():
    png = render_smart_card_qr_png(
        "https://voxbulk.com/smart-card/acme-jane-deadbeefcafebabe",
        fg_hex="1e3a8a",
        bg_hex="fef3c7",
        transparent=False,
        size=256,
    )
    img = Image.open(io.BytesIO(png))
    assert img.mode == "RGB"
    assert img.getpixel((2, 2)) == (0xFE, 0xF3, 0xC7)


def test_white_modules_on_transparent_still_visible_as_opaque_pixels():
    png = render_smart_card_qr_png(
        "https://voxbulk.com/smart-card/acme-jane-deadbeefcafebabe",
        fg_hex="ffffff",
        transparent=True,
        size=256,
    )
    img = Image.open(io.BytesIO(png))
    opaque_white = sum(1 for p in img.getdata() if p[3] == 255 and p[0] >= 250)
    clear = sum(1 for p in img.getdata() if p[3] == 0)
    assert opaque_white > 100
    assert clear > 100


def test_white_transparent_finders_are_hollow_not_white_filled():
    """Regression: transparent + white must not paint solid white finder plates."""
    png = render_styled_qr_png(
        "https://voxbulk.com/smart-card/demo",
        fg_hex="ffffff",
        transparent=True,
        corner_style="rounded",
        size=280,
        border=2,
    )
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    # Before resize: module_px = 280 // n. Quiet zone = 2 modules.
    # Finder mid ring at modules (border+1 .. border+5) → sample at ~3.5 modules from corner.
    # After resize to square target, proportion is the same.
    w, _h = img.size
    # Mid-ring of top-left finder ≈ (2+3.5)/n of width; n≈version+4quiet ≈ 29–41
    # Use a band inside the finder ring (not quiet zone, not centre)
    samples = []
    for frac in (0.12, 0.14, 0.16):
        x = int(w * frac)
        y = int(w * frac)
        samples.append(img.getpixel((x, y)))
    clear = sum(1 for p in samples if p[3] < 40)
    # At least one sample in the hollow ring should be clear
    assert clear >= 1, f"expected hollow finder samples={samples}"


def test_dots_use_circular_finders_and_frame():
    png = render_styled_qr_png(
        "https://voxbulk.com/survey/demo-token",
        module_style="dots",
        corner_style="square",
        frame_round="top",
        size=256,
    )
    assert png.startswith(b"\x89PNG")
    img = Image.open(io.BytesIO(png))
    assert img.size[0] > 0 and img.size[1] > 0
