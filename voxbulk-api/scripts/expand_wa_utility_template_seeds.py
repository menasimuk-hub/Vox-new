#!/usr/bin/env python3
"""Expand WA Survey + Feedback seed catalogs to 25 utility-safe topics per industry."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seed_data.wa_survey_abc_catalog import WA_SURVEY_ABC_CATALOG
from seed_data.wa_utility_template_expansion import (
    EXTRA_FEEDBACK_TOPICS,
    EXTRA_SURVEY_TOPICS,
    FEEDBACK_BODY_PATCHES,
    FEEDBACK_TOPIC_REPLACEMENTS,
    SURVEY_BODY_PATCHES,
    SURVEY_TOPIC_REPLACEMENTS,
)


def _patch_survey_body(body: str) -> str:
    text = str(body or "")
    for needle, replacement in SURVEY_BODY_PATCHES:
        if needle.lower() in text.lower():
            emoji = ""
            m = re.match(r"^(\S+)\s", text)
            if m and not m.group(1)[0].isalnum():
                emoji = m.group(1) + " "
            return emoji + replacement
    lower = text.lower()
    if "following your" in lower or "recent visit" in lower or "recent order" in lower or "recent stay" in lower:
        return text
    if text and not text[0].isalnum():
        parts = text.split(" ", 1)
        emoji = parts[0] + " "
        rest = parts[1] if len(parts) > 1 else text
    else:
        emoji = "😊 "
        rest = text
    rest = rest.strip()
    if rest.endswith("?"):
        inner = rest[:-1].strip()
        return f"{emoji}Following your recent visit, {inner.lower()}?"
    return f"{emoji}Following your recent visit, how would you rate {rest.lower()}?"


def expand_survey_catalog() -> list[dict]:
    expanded: list[dict] = []
    for industry in WA_SURVEY_ABC_CATALOG:
        questions: list[dict] = []
        seen_names: set[str] = set()
        for q in industry.get("questions") or []:
            name = str(q.get("name") or "")
            body = str(q.get("body") or "")
            options = list(q.get("options") or [])
            if name in SURVEY_TOPIC_REPLACEMENTS:
                name, body = SURVEY_TOPIC_REPLACEMENTS[name]
            else:
                body = _patch_survey_body(body)
            if name in seen_names:
                continue
            seen_names.add(name)
            questions.append({"name": name, "body": body, "options": options})

        for extra in EXTRA_SURVEY_TOPICS:
            name = str(extra["name"])
            if name in seen_names:
                continue
            seen_names.add(name)
            questions.append(
                {
                    "name": name,
                    "body": str(extra["body"]),
                    "options": list(extra["options"]),
                }
            )
        expanded.append(
            {
                "slug": industry["slug"],
                "name": industry["name"],
                "questions": questions[:25],
            }
        )
    return expanded


def _patch_feedback_body(body: str) -> str:
    text = body.strip()
    if text.lower().startswith("body:"):
        text = text.split(":", 1)[1].strip()
    for needle, replacement in FEEDBACK_BODY_PATCHES:
        if needle.lower() in text.lower():
            emoji = ""
            m = re.match(r"^(\S+)\s", text)
            if m:
                emoji = m.group(1) + " "
            return f"Body: {emoji}{replacement}"
    lower = text.lower()
    if "following your" in lower or "thank you for" in lower:
        return f"Body: {text}"
    if text and not text[0].isalnum():
        parts = text.split(" ", 1)
        emoji = parts[0] + " "
        rest = parts[1] if len(parts) > 1 else text
    else:
        emoji = "😊 "
        rest = text
    rest = rest.strip()
    if rest.endswith("?"):
        inner = rest[:-1].strip()
        return f"Body: {emoji}Following your recent visit, {inner.lower()}?"
    return f"Body: {emoji}Following your recent visit, how would you rate {rest.lower()}?"


def expand_feedback_md(content: str) -> str:
    content = re.sub(
        r"\*\*140 templates across 7 industries\*\*",
        "**175 templates across 7 industries**",
        content,
    )

    def _replace_block(match: re.Match) -> str:
        header = match.group(1)
        if header in FEEDBACK_TOPIC_REPLACEMENTS:
            new_title, new_body, buttons = FEEDBACK_TOPIC_REPLACEMENTS[header]
            return f"**{new_title}**\nBody: {new_body}\nButtons: {' | '.join(buttons)}\n"
        body_line = match.group(2)
        patched = _patch_feedback_body(body_line)
        buttons_line = match.group(3)
        return f"**{header}**\n{patched}\n{buttons_line}\n"

    pattern = re.compile(
        r"\*\*(?P<header>\d{2} – [^*]+)\*\*\n"
        r"(Body: .+)\n"
        r"(Buttons: .+)\n",
        re.MULTILINE,
    )
    content = pattern.sub(_replace_block, content)

    extra_block = "\n".join(
        f"**{title}**\nBody: {b}\nButtons: {' | '.join(btns)}\n"
        for title, b, btns in EXTRA_FEEDBACK_TOPICS
    )

    sections = re.split(r"(?=^## )", content, flags=re.MULTILINE)
    rebuilt: list[str] = []
    for idx, section in enumerate(sections):
        if idx == 0:
            rebuilt.append(section.rstrip())
            continue
        body = section.rstrip()
        if not body.endswith("---"):
            body = body + "\n\n" + extra_block + "\n---"
        else:
            body = body[:-3].rstrip() + "\n\n" + extra_block + "\n---"
        rebuilt.append(body)
    return "\n".join(rebuilt) + "\n"


def _render_catalog_py(catalog: list[dict]) -> str:
    lines = [
        '"""Master abc_choice question catalog for WA Survey industry templates."""',
        "",
        "from __future__ import annotations",
        "",
        "# Each entry: industry slug (from INDUSTRY_CATALOG), industry display name, list of questions",
        '# Each question: {"name": str, "body": str, "options": [str, str, str]}',
        "",
        "WA_SURVEY_ABC_CATALOG: list[dict] = [",
    ]
    for industry in catalog:
        lines.append("    {")
        lines.append(f'        "slug": "{industry["slug"]}",')
        lines.append(f'        "name": "{industry["name"]}",')
        lines.append('        "questions": [')
        for q in industry["questions"]:
            name = q["name"].replace('"', '\\"')
            body = q["body"].replace('"', '\\"')
            opts = ", ".join(f'"{o.replace(chr(34), "")}"' for o in q["options"])
            lines.append(
                f'            {{"name": "{name}", "body": "{body}", "options": [{opts}]}},'
            )
        lines.append("        ],")
        lines.append("    },")
    lines.append("]")
    lines.append("")
    return "\n".join(lines)


def _sync_industry_catalog_services(catalog: list[dict]) -> None:
    path = ROOT / "app" / "services" / "survey_industry_seed_service.py"
    text = path.read_text(encoding="utf-8")
    for industry in catalog:
        slug = industry["slug"]
        services = [q["name"] for q in industry["questions"]]
        pattern = rf'("slug": "{re.escape(slug)}",\s*\n\s*"name": "[^"]+",\s*\n\s*"sort_order": \d+,\s*\n\s*"services": \[)(.*?)(\],)'
        replacement_services = "\n".join(f'            "{s}",' for s in services)
        new_block = rf"\1\n{replacement_services}\n        \3"
        text, count = re.subn(pattern, new_block, text, count=1, flags=re.DOTALL)
        if count != 1:
            raise RuntimeError(f"Failed to patch INDUSTRY_CATALOG services for {slug}")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    catalog = expand_survey_catalog()
    catalog_path = ROOT / "seed_data" / "wa_survey_abc_catalog.py"
    catalog_path.write_text(_render_catalog_py(catalog), encoding="utf-8")
    print(f"Updated {catalog_path}")

    _sync_industry_catalog_services(catalog)
    print("Updated app/services/survey_industry_seed_service.py")

    from scripts.build_wa_survey_master_md import render_markdown

    md_path = ROOT / "seed-data" / "wa-survey" / "all-industries-abc-templates.md"
    md_path.write_text(render_markdown(catalog), encoding="utf-8")
    print(f"Updated {md_path}")

    fb_path = ROOT / "seed-data" / "customer-feedback" / "english-templates.md"
    fb_path.write_text(expand_feedback_md(fb_path.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Updated {fb_path}")

    for industry in catalog:
        print(f"  {industry['slug']}: {len(industry['questions'])} questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
