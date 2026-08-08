"""Unit tests for org logo format validation + tone normalize."""

from __future__ import annotations

import pytest

from app.services.org_logo_storage_service import normalize_logo_tone, validate_logo_upload

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)
JPEG_MIN = bytes(
    [
        0xFF,
        0xD8,
        0xFF,
        0xD9,
    ]
)
GIF_MIN = b"GIF89a" + b"\x00" * 10
SVG_MIN = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
WEBP_MIN = b"RIFF" + (12).to_bytes(4, "little") + b"WEBP" + b"\x00" * 4


def test_validate_png_ok():
    assert validate_logo_upload(filename="brand.png", content=PNG_1X1) == ".png"


def test_validate_jpeg_ok():
    assert validate_logo_upload(filename="brand.jpg", content=JPEG_MIN) in {".jpg", ".jpeg"}


def test_validate_webp_stored_ok():
    assert validate_logo_upload(filename="brand.webp", content=WEBP_MIN) == ".webp"


def test_reject_svg():
    with pytest.raises(ValueError, match="Only PNG and JPG"):
        validate_logo_upload(filename="brand.svg", content=SVG_MIN)


def test_reject_gif():
    with pytest.raises(ValueError, match="Only PNG and JPG"):
        validate_logo_upload(filename="brand.gif", content=GIF_MIN)


def test_normalize_tone():
    assert normalize_logo_tone("light") == "light"
    assert normalize_logo_tone("DARK") == "dark"
    assert normalize_logo_tone("nope") is None
