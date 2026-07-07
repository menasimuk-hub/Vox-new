#!/usr/bin/env python3
"""Rewrite generic E/G/P options in wa_survey_abc_catalog.py."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seed_data.wa_survey_button_diversify import diversify_question_options

CATALOG_PATH = ROOT / "seed_data" / "wa_survey_abc_catalog.py"
EGP_LINE = '"options": ["Excellent", "Good", "Poor"]'


def main() -> int:
    lines = CATALOG_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = 0
    out: list[str] = []
    for line in lines:
        if EGP_LINE in line:
            m = re.search(r'"name": "([^"]+)"', line)
            if m:
                name = m.group(1)
                new_opts = diversify_question_options(name, ["Excellent", "Good", "Poor"])
                if new_opts != ["Excellent", "Good", "Poor"]:
                    line = line.replace(EGP_LINE, '"options": ' + repr(new_opts))
                    changed += 1
                    print(name, "->", new_opts)
        out.append(line)
    CATALOG_PATH.write_text("".join(out), encoding="utf-8")
    print(f"updated={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
