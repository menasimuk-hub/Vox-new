"""Runtime deploy identity — git revision, repo path, and loaded code markers."""

from __future__ import annotations

import importlib
import json
import logging
import os
import socket
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Canonical deploy marker — must appear as this literal in instrumented source files.
# TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250
WEBHOOK_BUILD_MARKER = "TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250"

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parent
BUILD_INFO_FILE = API_ROOT / "build_info.json"

# Each site: file path (under voxbulk-api) and substrings that must exist on disk.
MARKER_SITES: dict[str, dict[str, Any]] = {
    "canonical": {
        "path": "app/core/runtime_build_info.py",
        "needles": [WEBHOOK_BUILD_MARKER, "WEBHOOK_BUILD_MARKER"],
    },
    "boot": {
        "path": "main.py",
        "needles": [WEBHOOK_BUILD_MARKER, "log_startup_build_info"],
    },
    "router": {
        "path": "app/routers/telnyx.py",
        "needles": [WEBHOOK_BUILD_MARKER, "log_webhook_entry", "router_dispatch"],
    },
    "service": {
        "path": "app/services/telnyx_inbound_messaging_service.py",
        "needles": [WEBHOOK_BUILD_MARKER, "log_webhook_entry", "service_handle_webhook"],
    },
}

SESSION_DISK_FILES: dict[str, list[str]] = {
    "app/services/survey_session_service.py": [
        "ensure_awaiting_start_session",
        "DECISION_AWAITING_START",
    ],
    "app/services/survey_whatsapp_conversation_service.py": [
        "find_active_recipient_for_inbound",
        "awaiting_start_session_committed",
        "welcome_sent_but_no_active_session",
    ],
    "app/services/survey_builder_test_service.py": [
        "Could not start WA survey test session: session was not created",
    ],
}

_boot_marker_executed = False
_webhook_marker_count = 0


def boot_marker_executed() -> bool:
    return _boot_marker_executed


def webhook_marker_count() -> int:
    return _webhook_marker_count


def _read_file(rel_path: str) -> str:
    path = API_ROOT / rel_path
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _file_has_needles(rel_path: str, needles: list[str]) -> bool:
    text = _read_file(rel_path)
    if not text:
        return False
    return all(needle in text for needle in needles)


def _site_disk_ok(site: str) -> bool:
    spec = MARKER_SITES[site]
    return _file_has_needles(str(spec["path"]), list(spec["needles"]))


def _module_source_has_needles(module_name: str, needles: list[str]) -> bool:
    try:
        mod = importlib.import_module(module_name)
        src_path = Path(getattr(mod, "__file__", "") or "")
        if not src_path.is_file():
            return False
        text = src_path.read_text(encoding="utf-8", errors="ignore")
        return all(needle in text for needle in needles)
    except Exception:
        return False


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


def get_deploy_verification() -> dict[str, Any]:
    build = get_runtime_build_info()

    boot_disk = _site_disk_ok("boot")
    router_disk = _site_disk_ok("router")
    service_disk = _site_disk_ok("service")
    canonical_disk = _site_disk_ok("canonical")

    boot_loaded = (
        WEBHOOK_BUILD_MARKER == "TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250"
        and _module_source_has_needles("main", MARKER_SITES["boot"]["needles"])
    )
    router_loaded = _module_source_has_needles(
        "app.routers.telnyx", MARKER_SITES["router"]["needles"]
    )
    service_loaded = _module_source_has_needles(
        "app.services.telnyx_inbound_messaging_service", MARKER_SITES["service"]["needles"]
    )

    session_disk: dict[str, bool] = {
        rel: _file_has_needles(rel, needles) for rel, needles in SESSION_DISK_FILES.items()
    }
    session_disk_ok = all(session_disk.values()) if session_disk else True

    try:
        from app.services.survey_session_service import SurveySessionService

        session_memory_ok = hasattr(SurveySessionService, "ensure_awaiting_start_session")
    except Exception:
        session_memory_ok = False

    markers_ok = boot_disk and router_disk and service_disk and canonical_disk
    loaded_ok = boot_loaded and router_loaded and service_loaded
    deploy_ok = markers_ok and loaded_ok and session_disk_ok and session_memory_ok

    return {
        **build,
        "git_sha": build.get("git_sha"),
        "git_branch": build.get("git_branch"),
        "boot_marker_present_on_disk": boot_disk,
        "router_marker_present_on_disk": router_disk,
        "service_marker_present_on_disk": service_disk,
        "canonical_marker_present_on_disk": canonical_disk,
        "boot_marker_loaded": boot_loaded,
        "router_marker_loaded": router_loaded,
        "service_marker_loaded": service_loaded,
        "boot_marker_executed_in_process": boot_marker_executed(),
        "webhook_marker_logged_count": webhook_marker_count(),
        "session_code_present_on_disk": session_disk_ok,
        "session_code_loaded": session_memory_ok,
        "deploy_ok": deploy_ok,
        "marker_site_paths": {k: v["path"] for k, v in MARKER_SITES.items()},
        "session_disk_detail": session_disk,
        "handler_chain": (
            "main:app → app.routers.telnyx.telnyx_messages_webhook "
            "→ TelnyxInboundMessagingService.handle_webhook"
        ),
    }


def log_startup_build_info(app_logger: logging.Logger | None = None) -> dict[str, Any]:
    global _boot_marker_executed
    log = app_logger or logger
    data = get_deploy_verification()
    _boot_marker_executed = True
    log.info(
        "%s app_boot git_sha=%s git_branch=%s built_at=%s hostname=%s pid=%s "
        "api_root=%s repo_root=%s deploy_ok=%s boot_disk=%s router_disk=%s service_disk=%s "
        "boot_loaded=%s router_loaded=%s service_loaded=%s log=%s",
        WEBHOOK_BUILD_MARKER,
        data.get("git_sha"),
        data.get("git_branch"),
        data.get("built_at"),
        data.get("hostname"),
        data.get("pid"),
        data.get("api_root"),
        data.get("repo_root"),
        data.get("deploy_ok"),
        data.get("boot_marker_present_on_disk"),
        data.get("router_marker_present_on_disk"),
        data.get("service_marker_present_on_disk"),
        data.get("boot_marker_loaded"),
        data.get("router_marker_loaded"),
        data.get("service_marker_loaded"),
        data.get("git_log_one_line"),
    )
    if not data.get("deploy_ok"):
        log.warning(
            "%s deploy_verification_failed verification=%s",
            WEBHOOK_BUILD_MARKER,
            {
                k: data.get(k)
                for k in (
                    "boot_marker_present_on_disk",
                    "router_marker_present_on_disk",
                    "service_marker_present_on_disk",
                    "boot_marker_loaded",
                    "router_marker_loaded",
                    "service_marker_loaded",
                    "session_code_present_on_disk",
                    "session_code_loaded",
                )
            },
        )
    return data


def log_webhook_entry(
    *,
    event_type: str = "",
    from_phone: str = "",
    org_id: str | None = None,
    handler: str = "TelnyxInboundMessagingService.handle_webhook",
) -> dict[str, Any]:
    global _webhook_marker_count
    _webhook_marker_count += 1
    data = get_runtime_build_info()
    logger.info(
        "%s webhook_entry handler=%s git_sha=%s branch=%s hostname=%s pid=%s "
        "event_type=%s from_phone=%r org_id=%s api_root=%s count=%s",
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
        _webhook_marker_count,
    )
    return data
