"""Seed WA Survey types and abc_choice templates from a simple Markdown file."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService, _normalize_slug
from app.services.survey_industry_seed_service import INDUSTRY_CATALOG, _service_slug
from app.services.survey_industry_scope import apply_industry_to_template
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_whatsapp_template_service import (
    META_BODY_HARD_MAX_CHARS,
    META_BUTTON_LABEL_MAX_CHARS,
    STANDARD_OPT_OUT_FOOTER,
    SYNC_DRAFT,
    SYNC_LOCAL_CHANGES,
    VARIANT_STANDARD,
    _body_preview,
    _dumps,
    _is_local_row,
    _normalize_draft_components,
    _telnyx_name_for,
)
from app.services.wa_template_meta_sync import default_wa_template_language, normalize_wa_template_language
from app.services.wa_template_privacy import PRIVACY_MODE_OFF

_LOCAL_ID_PREFIX = "local-"
_OPTION_LINE_RE = re.compile(r"[A-Z]\)\s*")
_INDUSTRY_HEADER_RE = re.compile(
    r"^(?:industry|industry_name)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_INDUSTRY_SLUG_HEADER_RE = re.compile(
    r"^(?:industry_slug|industry-slug)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)


@dataclass
class MdSurveyQuestion:
    name: str
    body: str
    options: list[str]
    wizard_description: str = ""
    step_role: str = "abc_choice"


@dataclass
class MdSurveyIndustrySection:
    industry_name: str
    industry_slug: str | None = None
    questions: list[MdSurveyQuestion] = field(default_factory=list)


@dataclass
class ParsedMultiMdSurveyPack:
    sections: list[MdSurveyIndustrySection] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


def _strip_markdown_title(raw: str) -> str:
    text = str(raw or "").strip()
    match = re.match(r"^\*\*(.+)\*\*$", text)
    if match:
        return match.group(1).strip()
    return text


def _industry_catalog_lookup() -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for item in INDUSTRY_CATALOG:
        name = str(item.get("name") or "").strip()
        slug = str(item.get("slug") or "").strip()
        if name and slug:
            lookup[name.lower()] = (slug, name)
    return lookup


def _parse_question_lines(lines: list[str], *, block_idx: int) -> MdSurveyQuestion | None:
    if not lines:
        return None
    options_idx = None
    for idx in range(len(lines) - 1, 0, -1):
        if _looks_like_options_line(lines[idx]):
            options_idx = idx
            break
    if options_idx is None:
        return None

    name = _strip_markdown_title(lines[0].strip())
    if options_idx <= 1:
        return None
    body = _sanitize_body("\n".join(lines[1:options_idx]))
    options = [_sanitize_button_label(opt) for opt in _parse_options_line(lines[options_idx])]
    return MdSurveyQuestion(
        name=name,
        body=body,
        options=options,
        wizard_description=body,
    )


def parse_multi_industry_md_survey_pack(text: str, *, source_name: str = "") -> ParsedMultiMdSurveyPack:
    """Parse a master MD file with industry section headers and abc_choice blocks."""
    pack = ParsedMultiMdSurveyPack()
    lookup = _industry_catalog_lookup()
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            raw = raw[end + 4 :].lstrip("\n")

    current: MdSurveyIndustrySection | None = None
    blocks = re.split(r"\n\s*\n", raw.strip())
    for block_idx, block in enumerate(blocks, start=1):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        if len(lines) == 1:
            title = _strip_markdown_title(lines[0])
            industry = lookup.get(title.lower())
            if industry is not None:
                slug, name = industry
                if current is not None and current.questions:
                    pack.sections.append(current)
                current = MdSurveyIndustrySection(industry_name=name, industry_slug=slug)
                continue
        else:
            title = _strip_markdown_title(lines[0])
            industry = lookup.get(title.lower())
            if industry is not None:
                slug, name = industry
                if current is not None and current.questions:
                    pack.sections.append(current)
                current = MdSurveyIndustrySection(industry_name=name, industry_slug=slug)
                lines = lines[1:]
                if not lines:
                    continue

        question = _parse_question_lines(lines, block_idx=block_idx)
        if question is None:
            label = lines[0][:40]
            pack.parse_errors.append(
                f"Block {block_idx} ({label}): could not parse question/options"
            )
            continue
        if current is None:
            pack.parse_errors.append(
                f"Block {block_idx} ({question.name[:40]}): question found before any industry header"
            )
            continue
        question_errors = _validate_question(question)
        if question_errors:
            pack.parse_errors.extend(question_errors)
        current.questions.append(question)

    if current is not None and current.questions:
        pack.sections.append(current)

    if not pack.sections and not pack.parse_errors:
        label = source_name or "file"
        pack.parse_errors.append(f"No industry sections found in {label}")
    return pack


@dataclass
class ParsedMdSurveyPack:
    industry_name: str | None = None
    industry_slug: str | None = None
    questions: list[MdSurveyQuestion] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


class SurveyWaMdSeedError(ValueError):
    pass


def _slug_from_label(raw: str) -> str:
    return _normalize_slug(raw) or _service_slug(raw)


def _title_from_filename(path: Path) -> tuple[str, str]:
    stem = path.stem.replace("-", " ").replace("_", " ").strip()
    slug = _service_slug(stem)
    name = " ".join(word.capitalize() for word in stem.split()) or slug.replace("_", " ").title()
    return slug, name


def _parse_options_line(line: str) -> list[str]:
    text = str(line or "").strip()
    if not text:
        return []
    if _OPTION_LINE_RE.search(text):
        parts = _OPTION_LINE_RE.split(text)
        options = [part.strip(" \t-—·") for part in parts if part.strip()]
        if options:
            return options
    if "/" in text:
        return [part.strip() for part in text.split("/") if part.strip()]
    return []


def _looks_like_options_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    matches = re.findall(r"[A-Z]\)", text)
    return len(matches) >= 2


def _sanitize_button_label(raw: str) -> str:
    label = _EMOJI_RE.sub("", str(raw or "")).strip()
    label = re.sub(r"\s+", " ", label)
    if not label:
        label = "Option"
    if len(label) > META_BUTTON_LABEL_MAX_CHARS:
        label = label[:META_BUTTON_LABEL_MAX_CHARS].rstrip()
    return label


def _sanitize_body(raw: str) -> str:
    body = re.sub(r"\s+", " ", str(raw or "").strip())
    if len(body) > META_BODY_HARD_MAX_CHARS:
        body = body[: META_BODY_HARD_MAX_CHARS - 1].rstrip() + "…"
    return body


def _validate_question(question: MdSurveyQuestion) -> list[str]:
    errors: list[str] = []
    if not question.name.strip():
        errors.append("missing survey type name")
    if not question.body.strip():
        errors.append(f"{question.name}: missing question body")
    if len(question.options) < 2:
        errors.append(f"{question.name}: need at least 2 answer options")
    if len(question.options) > 3:
        errors.append(f"{question.name}: Meta allows at most 3 quick_reply buttons")
    for opt in question.options:
        if not _sanitize_button_label(opt):
            errors.append(f"{question.name}: invalid button label {opt!r}")
    if len(STANDARD_OPT_OUT_FOOTER) > 60:
        errors.append("internal footer length misconfigured")
    return errors


def parse_md_survey_pack(text: str, *, source_name: str = "") -> ParsedMdSurveyPack:
    """Parse MD blocks: title, question body, then A) B) C) options line."""
    pack = ParsedMdSurveyPack()
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            frontmatter = raw[3:end].strip()
            raw = raw[end + 4 :].lstrip("\n")
            for line in frontmatter.splitlines():
                slug_match = _INDUSTRY_SLUG_HEADER_RE.match(line.strip())
                if slug_match:
                    pack.industry_slug = _slug_from_label(slug_match.group(1))
                    continue
                name_match = _INDUSTRY_HEADER_RE.match(line.strip())
                if name_match:
                    pack.industry_name = name_match.group(1).strip()

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if stripped.lower().startswith("# industry"):
                pack.industry_name = stripped.split(":", 1)[-1].strip(" #")
            slug_match = _INDUSTRY_SLUG_HEADER_RE.match(stripped.lstrip("#").strip())
            if slug_match:
                pack.industry_slug = _slug_from_label(slug_match.group(1))
            continue
        header_match = _INDUSTRY_HEADER_RE.match(stripped)
        if header_match and not pack.industry_name:
            pack.industry_name = header_match.group(1).strip()
            continue

    blocks = re.split(r"\n\s*\n", raw.strip())
    for block_idx, block in enumerate(blocks, start=1):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if all(_INDUSTRY_HEADER_RE.match(ln) or _INDUSTRY_SLUG_HEADER_RE.match(ln) for ln in lines):
            continue
        if lines[0].lower().startswith("industry:"):
            pack.industry_name = lines[0].split(":", 1)[-1].strip()
            continue

        options_idx = None
        for idx in range(len(lines) - 1, 0, -1):
            if _looks_like_options_line(lines[idx]):
                options_idx = idx
                break
        if options_idx is None:
            pack.parse_errors.append(
                f"Block {block_idx} ({lines[0][:40]}): could not find A) B) C) options line"
            )
            continue

        name = lines[0].strip()
        if options_idx <= 1:
            pack.parse_errors.append(f"Block {block_idx} ({name[:40]}): missing question body line")
            continue
        body = _sanitize_body("\n".join(lines[1:options_idx]))
        options = [_sanitize_button_label(opt) for opt in _parse_options_line(lines[options_idx])]
        question = MdSurveyQuestion(
            name=name,
            body=body,
            options=options,
            wizard_description=body,
        )
        question_errors = _validate_question(question)
        if question_errors:
            pack.parse_errors.extend(question_errors)
        pack.questions.append(question)

    if not pack.questions and not pack.parse_errors:
        label = source_name or "file"
        pack.parse_errors.append(f"No survey questions found in {label}")
    return pack


def _build_abc_choice_components(*, body: str, options: list[str]) -> list[dict[str, Any]]:
    labels = [_sanitize_button_label(opt) for opt in options[:3] if _sanitize_button_label(opt)]
    if len(labels) < 2:
        raise SurveyWaMdSeedError("At least two button labels are required")
    return [
        {"type": "BODY", "text": body},
        {"type": "FOOTER", "text": STANDARD_OPT_OUT_FOOTER},
        {
            "type": "BUTTONS",
            "buttons": [{"type": "QUICK_REPLY", "text": label} for label in labels],
        },
    ]


def _resolve_industry(
    db: Session,
    *,
    industry_slug: str | None,
    industry_name: str | None,
    create_industry: bool,
) -> Industry:
    slug = _slug_from_label(industry_slug or industry_name or "")
    if not slug:
        raise SurveyWaMdSeedError("Industry slug or name is required")

    row = IndustryService.get_by_slug(db, slug)
    if row is None and industry_name:
        row = db.execute(
            select(Industry).where(func.lower(Industry.name) == industry_name.strip().lower())
        ).scalar_one_or_none()
    if row is None:
        if not create_industry:
            raise SurveyWaMdSeedError(
                f"Industry not found for slug={slug!r}. Pass --create-industry or seed industries first."
            )
        row = IndustryService.create_industry(
            db,
            {
                "slug": slug,
                "name": (industry_name or slug.replace("_", " ").title()).strip(),
                "description": f"WA Survey templates seeded from Markdown for {(industry_name or slug).strip()}.",
                "sort_order": 120,
                "is_active": True,
            },
        )
    return row


def _ensure_survey_type(
    db: Session,
    *,
    industry: Industry,
    question: MdSurveyQuestion,
    create_missing: bool,
) -> tuple[SurveyType, bool]:
    slug = _service_slug(question.name)
    row = db.execute(
        select(SurveyType).where(
            SurveyType.industry_id == industry.id,
            SurveyType.slug == slug,
        )
    ).scalar_one_or_none()
    if row is not None:
        changed = False
        if row.name != question.name:
            row.name = question.name
            changed = True
        desc = question.wizard_description or question.body
        if row.description != desc:
            row.description = desc
            changed = True
        if changed:
            row.updated_at = datetime.utcnow()
            db.add(row)
        return row, False
    if not create_missing:
        return None, False
    now = datetime.utcnow()
    row = SurveyType(
        id=str(uuid.uuid4()),
        industry_id=industry.id,
        slug=slug,
        name=question.name,
        description=question.wizard_description or question.body,
        is_active=True,
        default_length="standard",
        min_length=4,
        max_length=6,
        supports_anonymous=False,
        sort_order=100,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row, True


def _find_question_template(db: Session, *, survey_type_id: str) -> TelnyxWhatsappTemplate | None:
    rows = (
        db.execute(
            select(TelnyxWhatsappTemplate).where(
                TelnyxWhatsappTemplate.survey_type_id == survey_type_id,
                TelnyxWhatsappTemplate.step_role == "abc_choice",
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    return sorted(rows, key=lambda r: r.updated_at or r.created_at, reverse=True)[0]


def _upsert_question_template(
    db: Session,
    *,
    survey_type: SurveyType,
    question: MdSurveyQuestion,
    overwrite: bool,
    language: str,
) -> tuple[TelnyxWhatsappTemplate, str]:
    components = _build_abc_choice_components(body=question.body, options=question.options)
    lang_code, lang_error = normalize_wa_template_language(language, db=db)
    if lang_error:
        raise SurveyWaMdSeedError(lang_error)
    lang_code = lang_code or default_wa_template_language(db)

    existing = _find_question_template(db, survey_type_id=survey_type.id)
    now = datetime.utcnow()
    display_name = f"{survey_type.name} — Question"[:128]

    if existing is not None and not overwrite:
        return existing, "skipped"

    if existing is not None:
        normalized = _normalize_draft_components(components)
        existing.display_name = display_name
        existing.customer_description = question.wizard_description
        existing.language = lang_code
        existing.category = "UTILITY"
        existing.variant_type = VARIANT_STANDARD
        existing.privacy_mode = PRIVACY_MODE_OFF
        existing.step_role = "abc_choice"
        existing.outcome_key = None
        existing.draft_components_json = _dumps(normalized)
        existing.body_preview = _body_preview(normalized)
        existing.example_values_json = _dumps([])
        existing.active_for_survey = True
        existing.updated_at = now
        if _is_local_row(existing):
            existing.status = "LOCAL_DRAFT"
            existing.local_sync_status = SYNC_DRAFT
        else:
            existing.local_sync_status = SYNC_LOCAL_CHANGES
        row = existing
        action = "updated"
    else:
        local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
        normalized = _normalize_draft_components(components)
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=local_id,
            template_id=local_id,
            name=_telnyx_name_for(survey_type.slug, f"abc_{uuid.uuid4().hex[:6]}"),
            display_name=display_name,
            customer_description=question.wizard_description,
            language=lang_code,
            category="UTILITY",
            status="LOCAL_DRAFT",
            variant_type=VARIANT_STANDARD,
            privacy_mode=PRIVACY_MODE_OFF,
            step_role="abc_choice",
            outcome_key=None,
            survey_type_id=survey_type.id,
            body_preview=_body_preview(normalized),
            draft_components_json=_dumps(normalized),
            components_json=_dumps(normalized),
            example_values_json=_dumps([]),
            local_sync_status=SYNC_DRAFT,
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(row)
        db.flush()
        apply_industry_to_template(row, survey_type)
        action = "created"

    SurveyTypeTemplateService.upsert_mapping(
        db,
        survey_type_id=survey_type.id,
        template_id=row.id,
        usable_as_standard=True,
        privacy_mode=PRIVACY_MODE_OFF,
    )
    db.flush()
    return row, action


class SurveyWaMdSeedService:
    @staticmethod
    def seed_from_markdown_file(
        db: Session,
        *,
        md_path: str | Path,
        industry_slug: str | None = None,
        industry_name: str | None = None,
        create_industry: bool = False,
        create_missing_types: bool = True,
        overwrite_templates: bool = False,
        dry_run: bool = False,
        language: str = "en_GB",
    ) -> dict[str, Any]:
        path = Path(md_path)
        if not path.is_file():
            raise SurveyWaMdSeedError(f"Markdown file not found: {path}")

        content = path.read_text(encoding="utf-8")
        parsed = parse_md_survey_pack(content, source_name=path.name)
        if parsed.parse_errors:
            raise SurveyWaMdSeedError("; ".join(parsed.parse_errors))

        file_slug, file_name = _title_from_filename(path)
        resolved_slug = industry_slug or parsed.industry_slug or file_slug
        resolved_name = industry_name or parsed.industry_name or file_name

        preview_rows: list[dict[str, Any]] = []
        for question in parsed.questions:
            preview_rows.append(
                {
                    "survey_type": question.name,
                    "body": question.body,
                    "wizard_description": question.wizard_description,
                    "buttons": question.options,
                    "category": "UTILITY",
                    "privacy_mode": "off",
                    "step_role": "abc_choice",
                    "language": language,
                }
            )

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "md_file": str(path),
                "industry_slug": resolved_slug,
                "industry_name": resolved_name,
                "question_count": len(parsed.questions),
                "preview": preview_rows,
            }

        industry = _resolve_industry(
            db,
            industry_slug=resolved_slug,
            industry_name=resolved_name,
            create_industry=create_industry,
        )

        types_created = 0
        types_existing = 0
        templates_created = 0
        templates_updated = 0
        templates_skipped = 0
        rows_out: list[dict[str, Any]] = []

        for question in parsed.questions:
            survey_type, type_created = _ensure_survey_type(
                db,
                industry=industry,
                question=question,
                create_missing=create_missing_types,
            )
            if survey_type is None:
                raise SurveyWaMdSeedError(
                    f"Survey type {question.name!r} not found under {industry.name}. "
                    "Use --create-types or run seed_wa_survey_industries.py first."
                )
            if type_created:
                types_created += 1
            else:
                types_existing += 1

            template, action = _upsert_question_template(
                db,
                survey_type=survey_type,
                question=question,
                overwrite=overwrite_templates,
                language=language,
            )
            if action == "created":
                templates_created += 1
            elif action == "updated":
                templates_updated += 1
            else:
                templates_skipped += 1

            rows_out.append(
                {
                    "survey_type_id": survey_type.id,
                    "survey_type_slug": survey_type.slug,
                    "survey_type_name": survey_type.name,
                    "template_id": template.id,
                    "template_name": template.name,
                    "body": question.body,
                    "buttons": question.options,
                    "wizard_description": question.wizard_description,
                    "action": action,
                }
            )

        db.commit()
        return {
            "ok": True,
            "dry_run": False,
            "md_file": str(path),
            "industry_id": industry.id,
            "industry_slug": industry.slug,
            "industry_name": industry.name,
            "question_count": len(parsed.questions),
            "survey_types_created": types_created,
            "survey_types_existing": types_existing,
            "templates_created": templates_created,
            "templates_updated": templates_updated,
            "templates_skipped": templates_skipped,
            "rows": rows_out,
        }

    @staticmethod
    def _seed_questions_for_industry(
        db: Session,
        *,
        industry: Industry,
        questions: list[MdSurveyQuestion],
        create_missing_types: bool,
        overwrite_templates: bool,
        language: str,
    ) -> dict[str, Any]:
        types_created = 0
        types_existing = 0
        templates_created = 0
        templates_updated = 0
        templates_skipped = 0
        rows_out: list[dict[str, Any]] = []

        for question in questions:
            survey_type, type_created = _ensure_survey_type(
                db,
                industry=industry,
                question=question,
                create_missing=create_missing_types,
            )
            if survey_type is None:
                raise SurveyWaMdSeedError(
                    f"Survey type {question.name!r} not found under {industry.name}. "
                    "Run seed_wa_survey_industries.py first."
                )
            if type_created:
                types_created += 1
            else:
                types_existing += 1

            template, action = _upsert_question_template(
                db,
                survey_type=survey_type,
                question=question,
                overwrite=overwrite_templates,
                language=language,
            )
            if action == "created":
                templates_created += 1
            elif action == "updated":
                templates_updated += 1
            else:
                templates_skipped += 1

            rows_out.append(
                {
                    "survey_type_id": survey_type.id,
                    "survey_type_slug": survey_type.slug,
                    "survey_type_name": survey_type.name,
                    "template_id": template.id,
                    "template_name": template.name,
                    "body": question.body,
                    "buttons": question.options,
                    "wizard_description": question.wizard_description,
                    "action": action,
                }
            )

        return {
            "industry_id": industry.id,
            "industry_slug": industry.slug,
            "industry_name": industry.name,
            "question_count": len(questions),
            "survey_types_created": types_created,
            "survey_types_existing": types_existing,
            "templates_created": templates_created,
            "templates_updated": templates_updated,
            "templates_skipped": templates_skipped,
            "rows": rows_out,
        }

    @staticmethod
    def seed_all_industries_from_markdown_file(
        db: Session,
        *,
        md_path: str | Path,
        create_missing_types: bool = True,
        overwrite_templates: bool = True,
        dry_run: bool = False,
        language: str = "en_GB",
    ) -> dict[str, Any]:
        path = Path(md_path)
        if not path.is_file():
            raise SurveyWaMdSeedError(f"Markdown file not found: {path}")

        content = path.read_text(encoding="utf-8")
        parsed = parse_multi_industry_md_survey_pack(content, source_name=path.name)
        if parsed.parse_errors:
            raise SurveyWaMdSeedError("; ".join(parsed.parse_errors))

        if dry_run:
            preview: list[dict[str, Any]] = []
            for section in parsed.sections:
                for question in section.questions:
                    preview.append(
                        {
                            "industry": section.industry_name,
                            "industry_slug": section.industry_slug,
                            "survey_type": question.name,
                            "body": question.body,
                            "buttons": question.options,
                        }
                    )
            return {
                "ok": True,
                "dry_run": True,
                "md_file": str(path),
                "industry_count": len(parsed.sections),
                "question_count": sum(len(s.questions) for s in parsed.sections),
                "preview": preview[:40],
                "preview_truncated": len(preview) > 40,
            }

        industry_results: list[dict[str, Any]] = []
        total_questions = 0
        totals = {
            "survey_types_created": 0,
            "survey_types_existing": 0,
            "templates_created": 0,
            "templates_updated": 0,
            "templates_skipped": 0,
        }

        for section in parsed.sections:
            industry = _resolve_industry(
                db,
                industry_slug=section.industry_slug,
                industry_name=section.industry_name,
                create_industry=False,
            )
            summary = SurveyWaMdSeedService._seed_questions_for_industry(
                db,
                industry=industry,
                questions=section.questions,
                create_missing_types=create_missing_types,
                overwrite_templates=overwrite_templates,
                language=language,
            )
            industry_results.append(summary)
            total_questions += int(summary.get("question_count") or 0)
            for key in totals:
                totals[key] += int(summary.get(key) or 0)

        db.commit()
        return {
            "ok": True,
            "dry_run": False,
            "md_file": str(path),
            "industry_count": len(industry_results),
            "question_count": total_questions,
            **totals,
            "industries": industry_results,
        }
