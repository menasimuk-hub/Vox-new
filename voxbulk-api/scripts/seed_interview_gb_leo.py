#!/usr/bin/env python3
"""Legacy wrapper — seeds all regional interview agents (includes Leo)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "seed_interview_regional_agents.py"
    raise SystemExit(subprocess.call([sys.executable, str(target)]))
