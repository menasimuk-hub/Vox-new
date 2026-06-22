#!/usr/bin/env python3
"""Export WA template names to Excel with industry + survey type mapping.

Usage (from voxbulk-api, project venv):
  .venv/bin/python scripts/export_wa_templates_industry_map.py
  .venv/bin/python scripts/export_wa_templates_industry_map.py \\
    --names-file seed-data/wa-templates/export-template-names.txt \\
    --output exports/wa_template_industry_map.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_NAMES = ROOT / "seed-data" / "wa-templates" / "export-template-names.txt"
DEFAULT_OUTPUT = ROOT / "exports" / "wa_template_industry_map.xlsx"

COLUMNS = [
    "template_name",
    "product_line",
    "industry_slug",
    "industry_name",
    "survey_type_slug",
    "survey_type_name",
    "template_key",
    "name_variant",
    "db_found",
    "telnyx_status",
    "display_name",
    "body_preview",
    "source",
]


def load_names(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            names.append(text)
    return names


def write_xlsx(rows: list[dict], output: Path) -> None:
    import openpyxl
    from openpyxl.styles import Font

    output.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "WA templates"
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row.get(col, "") for col in COLUMNS])
    for col in ws.columns:
        width = min(48, max(len(str(cell.value or "")) for cell in col) + 2)
        ws.column_dimensions[col[0].column_letter].width = width
    wb.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export WA template industry / survey type map to Excel")
    parser.add_argument("--names-file", type=Path, default=DEFAULT_NAMES, help="One template name per line")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output .xlsx path")
    args = parser.parse_args()

    if not args.names_file.is_file():
        raise SystemExit(f"Names file not found: {args.names_file}")

    names = load_names(args.names_file)
    if not names:
        raise SystemExit(f"No template names in {args.names_file}")

    from app.core.database import get_sessionmaker
    from app.services.wa_template_industry_export_service import resolve_template_export_rows

    with get_sessionmaker()() as db:
        rows = resolve_template_export_rows(db, names)

    write_xlsx(rows, args.output)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
