from __future__ import annotations

import pytest

from app.abuu.services.abuu_voice_service import is_low_quality_transcript


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hehehehehe",
        "hahaha",
        "ههههه",
        "aaaaaa",
        "lol",
    ],
)
def test_is_low_quality_transcript_rejects_noise(text: str):
    assert is_low_quality_transcript(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "بدي دجاج مشوي",
        "I want chicken shawarma",
        "واحد برجر لحم",
    ],
)
def test_is_low_quality_transcript_accepts_real_orders(text: str):
    assert is_low_quality_transcript(text) is False
