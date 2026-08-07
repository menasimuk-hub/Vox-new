"""Smart Card QR PNG — transparent background support."""

from __future__ import annotations

import io

from PIL import Image

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
    # Corner should be background (quiet zone)
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
