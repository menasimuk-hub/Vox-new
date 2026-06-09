#!/usr/bin/env python3
"""Build master Markdown file from WA_SURVEY_ABC_CATALOG."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seed_data.wa_survey_abc_catalog import WA_SURVEY_ABC_CATALOG

DEFAULT_OUT = ROOT / "seed-data" / "wa-survey" / "all-industries-abc-templates.md"


def _format_options(options: list[str]) -> str:
    labels = ("A", "B", "C")
    return " ".join(f"{label}) {opt}" for label, opt in zip(labels, options))


def render_markdown(catalog: list[dict]) -> str:
    blocks: list[str] = []
    for industry in catalog:
        blocks.append(str(industry["name"]))
        blocks.append("")
        for question in industry.get("questions") or []:
            blocks.append(str(question["name"]))
            blocks.append(str(question["body"]))
            blocks.append(_format_options(list(question.get("options") or [])))
            blocks.append("")
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    content = render_markdown(WA_SURVEY_ABC_CATALOG)
    out_path.write_text(content, encoding="utf-8")

    total_questions = sum(len(ind.get("questions") or []) for ind in WA_SURVEY_ABC_CATALOG)
    print(f"Wrote {out_path}")
    print(f"Industries: {len(WA_SURVEY_ABC_CATALOG)}")
    print(f"Questions:  {total_questions}")
    for industry in WA_SURVEY_ABC_CATALOG:
        count = len(industry.get("questions") or [])
        print(f"  {industry['slug']}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
