"""Apply / serialize QR style fields shared by Smart Card, Expo, Feedback."""

from __future__ import annotations

from typing import Any

from app.services.qr_style_render import (
    normalize_corner_style,
    normalize_frame_round,
    normalize_module_style,
)


def apply_qr_style_payload(row: Any, payload: dict[str, Any], *, allow_transparent: bool = False) -> None:
    if "qr_fg_color" in payload:
        row.qr_fg_color = str(payload.get("qr_fg_color") or "000000").replace("#", "")[:6]
    if "qr_bg_color" in payload:
        row.qr_bg_color = str(payload.get("qr_bg_color") or "ffffff").replace("#", "")[:6]
    if allow_transparent and "qr_transparent" in payload:
        row.qr_transparent = bool(payload.get("qr_transparent"))
    if "qr_module_style" in payload:
        row.qr_module_style = normalize_module_style(payload.get("qr_module_style"))
    if "qr_corner_style" in payload:
        row.qr_corner_style = normalize_corner_style(payload.get("qr_corner_style"))
    if "qr_show_arrow" in payload:
        row.qr_show_arrow = False
    if "qr_frame_round" in payload:
        row.qr_frame_round = normalize_frame_round(payload.get("qr_frame_round"))


def init_qr_style_on_create(row: Any, payload: dict[str, Any], *, allow_transparent: bool = False) -> None:
    row.qr_fg_color = str(payload.get("qr_fg_color") or "000000").replace("#", "")[:6]
    row.qr_bg_color = str(payload.get("qr_bg_color") or "ffffff").replace("#", "")[:6]
    if allow_transparent:
        row.qr_transparent = bool(payload.get("qr_transparent"))
    row.qr_module_style = normalize_module_style(payload.get("qr_module_style"))
    row.qr_corner_style = normalize_corner_style(payload.get("qr_corner_style"))
    row.qr_show_arrow = False
    row.qr_frame_round = normalize_frame_round(payload.get("qr_frame_round"))


def qr_style_dict(row: Any, *, include_transparent: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "qr_fg_color": getattr(row, "qr_fg_color", None) or "000000",
        "qr_bg_color": getattr(row, "qr_bg_color", None) or "ffffff",
        "qr_module_style": normalize_module_style(getattr(row, "qr_module_style", None)),
        "qr_corner_style": normalize_corner_style(getattr(row, "qr_corner_style", None)),
        "qr_show_arrow": False,
        "qr_frame_round": normalize_frame_round(getattr(row, "qr_frame_round", None)),
    }
    if include_transparent:
        out["qr_transparent"] = bool(getattr(row, "qr_transparent", False))
    return out
