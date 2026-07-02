#!/usr/bin/env python3
"""Shell wrapper for migrate_wa_templates_utility.py (VPS/Linux)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "bin" / "python"
SCRIPT = ROOT / "scripts" / "migrate_wa_templates_utility.py"


def main() -> int:
    py = PY if PY.exists() else Path(sys.executable)
    cmd = [str(py), str(SCRIPT), *sys.argv[1:]]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
