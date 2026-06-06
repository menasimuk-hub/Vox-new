"""Runtime deploy identity — git revision, repo path, and loaded code markers."""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Impossible-to-miss marker in Telnyx webhook logs after deploy.
WEBHOOK_BUILD_MARKER = "TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250"

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parent
BUILD_INFO_FILE = API_ROOT / "build_info.json"

DISK_MARKER_FILES: dict[str, list[str]] = {
    "app/services/survey_session_service.py": [
        "ensure_awaiting_start_session",
        "DECISION_AWAITING_START",
    ],
    "app/services/survey_whatsapp_conversation_service.py": [
        "find_active_recipient_for_inbound",
        "awaiting_start_session_committed",
        "welcome_sent_but_no_active_session",
    ],
    "app/services/telnyx_inbound_messaging_service.py": [
        "survey_session_bug",
        WEBHOOK_BUILD_MARKER,
    ],
    "app/services/survey_builder_test_service.py": [
        "Could not start WA survey test session: session was not created",
    ],
}


def _git_field(*args: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", *args],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
        return out.strip()
    except Exception:
        return ""


@lru_cache(maxsize=1)
def get_runtime_build_info() -> dict[str, Any]:
    """Load once per process — git SHA, branch, hostname, repo paths."""
    info: dict[str, Any] = {
        "webhook_build_marker": WEBHOOK_BUILD_MARKER,
        "api_root": str(API_ROOT),
        "repo_root": str(REPO_ROOT),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "cwd": os.getcwd(),
    }
    if BUILD_INFO_FILE.is_file():
        try:
            file_data = json.loads(BUILD_INFO_FILE.read_text(encoding="utf-8"))
            if isinstance(file_data, dict):
                info["build_info_file"] = file_data
                info["git_sha"] = str(file_data.get("git_sha") or file_data.get("sha") or "")
                info["git_branch"] = str(file_data.get("git_branch") or file_data.get("branch") or "")
                info["built_at"] = str(file_data.get("built_at") or "")
        except Exception:
            info["build_info_file_error"] = True
    if not info.get("git_sha"):
        info["git_sha"] = _git_field("rev-parse", "--short", "HEAD") or "unknown"
    if not info.get("git_branch"):
        info["git_branch"] = _git_field("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    info["git_sha_full"] = _git_field("rev-parse", "HEAD") or info.get("git_sha")
    info["git_log_one_line"] = _git_field("log", "-1", "--oneline") or ""
    return info


def _disk_markers() -> dict[str, bool]:
    out: dict[str, bool] = {}
    for rel_path, needles in DISK_MARKER_FILES.items():
        path = API_ROOT / rel_path
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            out[rel_path] = False
            continue
        out[rel_path] = all(needle in text for needle in needles)
    return out


def _memory_markers() -> dict[str, bool]:
    markers: dict[str, bool] = {}
    try:
        from app.services.survey_session_service import SurveySessionService

        markers["ensure_awaiting_start_session"] = hasattr(
            SurveySessionService, "ensure_awaiting_start_session"
        )
    except Exception:
        markers["ensure_awaiting_start_session"] = False
    try:
        from app.services.survey_whatsapp_conversation_service import (
            find_active_recipient_for_inbound,
            log_welcome_sent_without_active_session,
        )

        markers["find_active_recipient_for_inbound"] = callable(find_active_recipient_for_inbound)
        markers["log_welcome_sent_without_active_session"] = callable(
            log_welcome_sent_without_active_session
        )
    except Exception:
        markers["find_active_recipient_for_inbound"] = False
        markers["log_welcome_sent_without_active_session"] = False
    try:
        from app.services import telnyx_inbound_messaging_service as tim

        src = Path(getattr(tim, "__file__", "") or "")
        body = src.read_text(encoding="utf-8", errors="ignore") if src.is_file() else ""
        markers["survey_session_bug"] = "survey_session_bug" in body
        markers[WEBHOOK_BUILD_MARKER] = WEBHOOK_BUILD_MARKER in body
    except Exception:
        markers["survey_session_bug"] = False
        markers[WEBHOOK_BUILD_MARKER] = False
    return markers


def get_deploy_verification() -> dict[str, Any]:
    build = get_runtime_build_info()
    disk = _disk_markers()
    memory = _memory_markers()
    all_disk = all(disk.values()) if disk else False
    all_memory = all(memory.values()) if memory else False
    return {
        **build,
        "disk_markers": disk,
        "memory_markers": memory,
        "disk_markers_ok": all_disk,
        "memory_markers_ok": all_memory,
        "deploy_ok": all_disk and all_memory,
        "handler_chain": (
            "main:app → app.routers.telnyx.telnyx_messages_webhook "
            "→ TelnyxInboundMessagingService.handle_webhook"
        ),
    }


def log_startup_build_info(app_logger: logging.Logger | None = None) -> dict[str, Any]:
    log = app_logger or logger
    data = get_deploy_verification()
    log.info(
        "%s app_boot git_sha=%s git_branch=%s built_at=%s hostname=%s pid=%s "
        "api_root=%s repo_root=%s deploy_ok=%s disk_ok=%s memory_ok=%s log=%s",
        WEBHOOK_BUILD_MARKER,
        data.get("git_sha"),
        data.get("git_branch"),
        data.get("built_at"),
        data.get("hostname"),
        data.get("pid"),
        data.get("api_root"),
        data.get("repo_root"),
        data.get("deploy_ok"),
        data.get("disk_markers_ok"),
        data.get("memory_markers_ok"),
        data.get("git_log_one_line"),
    )
    if not data.get("deploy_ok"):
        log.warning(
            "%s deploy_verification_failed disk=%s memory=%s",
            WEBHOOK_BUILD_MARKER,
            data.get("disk_markers"),
            data.get("memory_markers"),
        )
    return data


def log_webhook_entry(
    *,
    event_type: str = "",
    from_phone: str = "",
    org_id: str | None = None,
    handler: str = "TelnyxInboundMessagingService.handle_webhook",
) -> dict[str, Any]:
    data = get_runtime_build_info()
    logger.info(
        "%s webhook_entry handler=%s git_sha=%s branch=%s hostname=%s pid=%s "
        "event_type=%s from_phone=%r org_id=%s api_root=%s",
        WEBHOOK_BUILD_MARKER,
        handler,
        data.get("git_sha"),
        data.get("git_branch"),
        data.get("hostname"),
        data.get("pid"),
        event_type,
        from_phone,
        org_id,
        data.get("api_root"),
    )
    return data
