"""Line-buffered progress output for WA UTILITY migration scripts."""

from __future__ import annotations

import os
import sys


def migration_progress(message: str) -> None:
    print(message, flush=True)
    path = str(os.getenv("WA_MIGRATION_PROGRESS_LOG") or "").strip()
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")


def migration_banner(title: str) -> None:
    migration_progress(f"\n=== {title} ===")
