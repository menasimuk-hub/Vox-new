from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.telnyx_api_key import require_telnyx_api_key

MATRIX_PATH = Path(__file__).resolve().parents[2] / "data" / "interview_voice_matrix.yaml"
ELEVENLABS_MODEL = "eleven_flash_v2_5"
ELEVENLABS_KEY_REF = "elevenlabs-paid"
TELNYX_SCORE_THRESHOLD = 3
UUID_VOICE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)

REGION_ACCENT_KEYWORDS: dict[str, list[str]] = {
    "GB": ["british", "uk", "english", "england", "gb"],
    "SC": ["scottish", "scotland", "british", "uk"],
    "IE": ["irish", "ireland", "ie"],
    "US": ["american", "us", "united states", "usa"],
    "CA": ["canadian", "canada", "north american"],
    "AU": ["australian", "australia", "au"],
}


def load_voice_matrix(path: Path | None = None) -> list[dict[str, Any]]:
    matrix_file = path or MATRIX_PATH
    if not matrix_file.is_file():
        return []
    raw = yaml.safe_load(matrix_file.read_text(encoding="utf-8")) or {}
    agents = raw.get("agents") if isinstance(raw, dict) else None
    if not isinstance(agents, list):
        return []
    return [a for a in agents if isinstance(a, dict) and str(a.get("slug") or "").startswith("interview-")]


def matrix_entry_for_slug(slug: str, path: Path | None = None) -> dict[str, Any] | None:
    clean = str(slug or "").strip()
    for row in load_voice_matrix(path):
        if str(row.get("slug") or "") == clean:
            return row
    return None


def voice_settings_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Build Telnyx assistant voice_settings from a matrix row (primary provider only)."""
    provider = str(entry.get("provider") or "telnyx").strip().lower()
    voice = str(entry.get("voice") or "").strip()
    if not voice:
        raise ValueError(f"No voice configured for {entry.get('slug')}")
    settings: dict[str, Any] = {"voice": voice}
    if provider == "elevenlabs":
        ref = str(entry.get("api_key_ref") or ELEVENLABS_KEY_REF).strip()
        if ref:
            settings["api_key_ref"] = ref
    return settings


def voice_settings_from_fallback(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Build voice_settings from matrix fallback block, if present."""
    fb = entry.get("fallback")
    if not isinstance(fb, dict):
        return None
    voice = str(fb.get("voice") or "").strip()
    if not voice:
        return None
    merged = {
        "slug": entry.get("slug"),
        "provider": fb.get("provider") or "telnyx",
        "voice": voice,
        "api_key_ref": fb.get("api_key_ref"),
    }
    return voice_settings_from_entry(merged)


def _gender_score(blob: str, gender: str) -> int:
    g = str(gender or "").lower()
    b = blob.lower()
    if g == "male":
        if any(x in b for x in ("female", " woman", "fem", "girl")):
            return -8
        if any(x in b for x in ("male", " man", "masc", "boy")):
            return 2
    elif g == "female":
        if any(x in b for x in ("male", " man", "masc", "boy")):
            return -8
        if any(x in b for x in ("female", " woman", "fem", "girl")):
            return 2
    return 0


def _gender_match(blob: str, gender: str) -> bool:
    return _gender_score(blob, gender) >= 0


def _score_voice(blob: str, keywords: list[str], gender: str) -> int:
    score = _gender_score(blob, gender)
    lower = blob.lower()
    for kw in keywords:
        if kw.lower() in lower:
            score += 2
    return score


def _telnyx_voice_string(voice_row: dict[str, Any]) -> str:
    voice_id = str(voice_row.get("voice_id") or voice_row.get("name") or "").strip()
    model = str(voice_row.get("model_id") or voice_row.get("model") or "").strip()
    if voice_id.lower().startswith("telnyx."):
        return voice_id
    if UUID_VOICE_RE.match(voice_id):
        return ""
    if model and voice_id:
        return f"Telnyx.{model}.{voice_id}"
    if voice_id:
        return f"Telnyx.NaturalHD.{voice_id}"
    return ""


def fetch_telnyx_voices(db: Session) -> list[dict[str, Any]]:
    api_key, _ = require_telnyx_api_key(db)
    url = "https://api.telnyx.com/v2/text-to-speech/voices?provider=telnyx"
    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
        response = client.get(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    if response.status_code >= 400:
        return []
    try:
        body = response.json()
    except Exception:
        return []
    voices = body.get("voices") if isinstance(body, dict) else None
    return [v for v in voices if isinstance(v, dict)] if isinstance(voices, list) else []


def fetch_elevenlabs_voices(db: Session) -> list[dict[str, Any]]:
    from app.services.providers.elevenlabs_service import ElevenLabsProviderService

    try:
        config = ElevenLabsProviderService._config(db)
    except Exception:
        return []
    base_url = str(config.get("base_url") or "https://api.elevenlabs.io").rstrip("/")
    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
        response = client.get(
            f"{base_url}/v1/voices",
            headers={"xi-api-key": str(config.get("api_key") or "")},
        )
    if response.status_code >= 400:
        return []
    try:
        body = response.json()
    except Exception:
        return []
    voices = body.get("voices") if isinstance(body, dict) else None
    return [v for v in voices if isinstance(v, dict)] if isinstance(voices, list) else []


def pick_telnyx_voice(
    voices: list[dict[str, Any]],
    *,
    region: str,
    gender: str,
    extra_keywords: list[str] | None = None,
) -> tuple[str, int]:
    keywords = list(REGION_ACCENT_KEYWORDS.get(region.upper(), []))
    if extra_keywords:
        keywords.extend(extra_keywords)
    best_voice = ""
    best_score = 0
    for row in voices:
        blob = " ".join(
            str(row.get(k) or "")
            for k in ("name", "voice_id", "language", "gender", "provider", "model_id", "model")
        )
        voice_str = _telnyx_voice_string(row)
        if not voice_str or UUID_VOICE_RE.search(voice_str.split(".")[-1]):
            continue
        score = _score_voice(blob, keywords, gender)
        if score > best_score:
            best_score = score
            best_voice = voice_str
    return best_voice, best_score


def pick_elevenlabs_voice(
    voices: list[dict[str, Any]],
    *,
    region: str,
    gender: str,
    extra_keywords: list[str] | None = None,
) -> tuple[str, int]:
    keywords = list(REGION_ACCENT_KEYWORDS.get(region.upper(), []))
    if extra_keywords:
        keywords.extend(extra_keywords)
    best_id = ""
    best_score = 0
    for row in voices:
        voice_id = str(row.get("voice_id") or "").strip()
        if not voice_id:
            continue
        labels = row.get("labels") if isinstance(row.get("labels"), dict) else {}
        blob = " ".join(
            [
                str(row.get("name") or ""),
                voice_id,
                str(row.get("description") or ""),
                " ".join(f"{k} {v}" for k, v in labels.items()),
            ]
        )
        score = _score_voice(blob, keywords, gender)
        if score > best_score:
            best_score = score
            best_id = voice_id
    if not best_id:
        return "", 0
    return f"ElevenLabs.{ELEVENLABS_MODEL}.{best_id}", best_score


def discover_entry_for_spec(
    db: Session,
    *,
    slug: str,
    region: str,
    gender: str,
    accent_keywords: list[str] | None = None,
    telnyx_voices: list[dict[str, Any]] | None = None,
    elevenlabs_voices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tx = telnyx_voices if telnyx_voices is not None else fetch_telnyx_voices(db)
    el = elevenlabs_voices if elevenlabs_voices is not None else fetch_elevenlabs_voices(db)
    kw = accent_keywords or REGION_ACCENT_KEYWORDS.get(region.upper(), [])

    telnyx_voice, tx_score = pick_telnyx_voice(tx, region=region, gender=gender, extra_keywords=kw)
    el_voice, el_score = pick_elevenlabs_voice(el, region=region, gender=gender, extra_keywords=kw)

    entry: dict[str, Any] = {
        "slug": slug,
        "region": region,
        "gender": gender,
        "accent_keywords": kw,
    }

    if telnyx_voice and tx_score >= TELNYX_SCORE_THRESHOLD:
        entry["provider"] = "telnyx"
        entry["voice"] = telnyx_voice
        if el_voice and el_score > 0:
            entry["fallback"] = {
                "provider": "elevenlabs",
                "voice": el_voice,
                "api_key_ref": ELEVENLABS_KEY_REF,
            }
    elif el_voice:
        entry["provider"] = "elevenlabs"
        entry["voice"] = el_voice
        entry["api_key_ref"] = ELEVENLABS_KEY_REF
        if telnyx_voice:
            entry["fallback"] = {"provider": "telnyx", "voice": telnyx_voice}
    elif telnyx_voice:
        entry["provider"] = "telnyx"
        entry["voice"] = telnyx_voice
    else:
        entry["provider"] = "telnyx"
        entry["voice"] = "Telnyx.NaturalHD.astra" if gender == "female" else "Telnyx.NaturalHD.albion"

    entry["_discover"] = {"telnyx_score": tx_score, "elevenlabs_score": el_score}
    return entry


def apply_voice_to_assistant(
    db: Session,
    *,
    assistant_id: str,
    voice_settings: dict[str, Any],
    dry_run: bool = False,
) -> None:
    import httpx

    from app.services.telnyx_assistant_service import (
        _telnyx_response_detail,
        _update_telnyx_assistant,
        normalize_telnyx_assistant_id,
    )

    clean_id = normalize_telnyx_assistant_id(assistant_id)
    body = {"voice_settings": dict(voice_settings), "promote_to_main": True}
    if dry_run:
        return
    try:
        _update_telnyx_assistant(db, clean_id, body)
    except httpx.HTTPStatusError as exc:
        detail = _telnyx_response_detail(exc.response)
        raise RuntimeError(f"{exc} — {detail}") from exc
