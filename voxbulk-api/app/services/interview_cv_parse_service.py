"""Parse CV files (PDF, DOCX, ZIP) for interview intake."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

CV_EXTENSIONS = {".pdf", ".docx", ".doc"}
ZIP_EXTENSIONS = {".zip"}

MIN_GOOD_TEXT_CHARS = 80
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_ZIP_FILES = 200
MAX_PAGES = 40

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,4}\)?[\s\-.]?)?\d{3,4}[\s\-.]?\d{3,4}(?:[\s\-.]?\d{2,4})?"
)


@dataclass
class ParsedCv:
    filename: str
    text: str = ""
    quality: str = "missing"
    name: str = ""
    phone: str = ""
    email: str = ""
    skills: list[str] = field(default_factory=list)
    job_titles: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    experience_lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    corrupt: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "quality": self.quality,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "skills": self.skills,
            "job_titles": self.job_titles,
            "education": self.education,
            "experience_lines": self.experience_lines[:12],
            "errors": self.errors,
            "text_chars": len(self.text or ""),
        }


def name_from_filename(filename: str) -> str:
    """Best-effort candidate name from CV filename (e.g. john_smith_cv.pdf)."""
    base = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[0]
    base = re.sub(r"(?i)\b(curriculum vitae|curriculum|resume|cv|profile)\b", " ", base)
    base = re.sub(r"[_\-]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    if not base:
        return ""
    words = base.split()
    if len(words) > 6:
        return " ".join(words[:4])
    if base.isupper():
        return base.title()
    return base


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _finalize_parsed_contacts(parsed: ParsedCv) -> None:
    if parsed.name:
        return
    from_filename = name_from_filename(parsed.filename)
    if from_filename:
        parsed.name = from_filename
        parsed.errors = [e for e in parsed.errors if e != "Name not found in CV"]
    elif "Name not found in CV — edit manually" not in parsed.errors:
        parsed.errors.append("Name not found in CV — edit manually")


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _clean_phone(raw: str) -> str:
    digits = re.sub(r"[^\d+]", "", str(raw or "").strip())
    if len(re.sub(r"\D", "", digits)) < 10:
        return ""
    return digits if digits.startswith("+") else digits


def _extract_contacts(text: str) -> tuple[str, str, str]:
    email = ""
    phone = ""
    em = EMAIL_RE.search(text or "")
    if em:
        email = em.group(0).strip().lower()
    for match in PHONE_RE.finditer(text or ""):
        candidate = _clean_phone(match.group(0))
        if len(re.sub(r"\D", "", candidate)) >= 10:
            phone = candidate
            break
    name = _guess_name(text)
    return name, phone, email


def _guess_name(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for line in lines[:8]:
        if EMAIL_RE.search(line) or PHONE_RE.search(line):
            continue
        if len(line) < 3 or len(line) > 80:
            continue
        if sum(ch.isdigit() for ch in line) > 3:
            continue
        words = line.split()
        if 1 <= len(words) <= 5 and all(w[0].isalpha() for w in words if w):
            return line
    return ""


def _extract_skills(text: str) -> list[str]:
    block = ""
    lower = text.lower()
    for header in ("skills", "technical skills", "core competencies"):
        idx = lower.find(header)
        if idx >= 0:
            block = text[idx : idx + 800]
            break
    if not block:
        return []
    parts = re.split(r"[,;|\n•·]", block)
    out: list[str] = []
    for part in parts:
        skill = re.sub(r"^(skills|technical skills)\s*:?\s*", "", part.strip(), flags=re.I)
        if 2 <= len(skill) <= 48 and not skill.lower().startswith("skill"):
            out.append(skill)
        if len(out) >= 12:
            break
    return out


def _extract_job_titles(text: str) -> list[str]:
    titles: list[str] = []
    for line in (text or "").splitlines():
        ln = line.strip()
        if not ln or len(ln) > 90:
            continue
        if re.search(r"\b(engineer|developer|manager|analyst|consultant|director|lead|designer|specialist)\b", ln, re.I):
            if not EMAIL_RE.search(ln) and not PHONE_RE.search(ln):
                titles.append(ln[:90])
        if len(titles) >= 8:
            break
    return titles


def _extract_education(text: str) -> list[str]:
    edu: list[str] = []
    for line in (text or "").splitlines():
        ln = line.strip()
        if re.search(r"\b(bsc|msc|mba|ba|ma|phd|degree|university|college|school)\b", ln, re.I):
            edu.append(ln[:120])
        if len(edu) >= 6:
            break
    return edu


def _extract_experience(text: str) -> list[str]:
    lines: list[str] = []
    capture = False
    for line in (text or "").splitlines():
        ln = line.strip()
        if re.match(r"^(experience|work history|employment)\b", ln, re.I):
            capture = True
            continue
        if capture and re.match(r"^(education|skills|projects)\b", ln, re.I):
            break
        if capture and ln:
            lines.append(ln[:140])
        if len(lines) >= 12:
            break
    return lines


def _quality_from_text(text: str, *, corrupt: bool = False) -> str:
    if corrupt:
        return "corrupt"
    chars = len(re.sub(r"\s+", "", text or ""))
    if chars < MIN_GOOD_TEXT_CHARS:
        return "low_quality"
    return "good"


def parse_pdf_bytes(content: bytes, filename: str) -> ParsedCv:
    parsed = ParsedCv(filename=filename)
    try:
        import fitz
    except ImportError as e:
        parsed.errors.append("PDF parser not installed on server")
        parsed.quality = "corrupt"
        parsed.corrupt = True
        return parsed
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        if doc.needs_pass:
            parsed.errors.append("Password-protected PDF — save an unlocked copy")
            parsed.quality = "corrupt"
            parsed.corrupt = True
            doc.close()
            return parsed
        chunks: list[str] = []
        for i, page in enumerate(doc):
            if i >= MAX_PAGES:
                break
            chunks.append(page.get_text() or "")
        doc.close()
        parsed.text = "\n".join(chunks).strip()
    except Exception:
        parsed.errors.append("Could not read PDF")
        parsed.quality = "corrupt"
        parsed.corrupt = True
        return parsed

    parsed.quality = _quality_from_text(parsed.text)
    parsed.name, parsed.phone, parsed.email = _extract_contacts(parsed.text)
    parsed.skills = _extract_skills(parsed.text)
    parsed.job_titles = _extract_job_titles(parsed.text)
    parsed.education = _extract_education(parsed.text)
    parsed.experience_lines = _extract_experience(parsed.text)
    if parsed.quality == "low_quality":
        parsed.errors.append("Low-quality CV (scanned or very little text)")
    if not parsed.phone:
        parsed.errors.append("Phone not found in CV — add manually")
    _finalize_parsed_contacts(parsed)
    return parsed


def parse_docx_bytes(content: bytes, filename: str) -> ParsedCv:
    parsed = ParsedCv(filename=filename)
    try:
        from docx import Document
    except ImportError:
        parsed.errors.append("DOCX parser not installed on server")
        parsed.quality = "corrupt"
        parsed.corrupt = True
        return parsed
    try:
        doc = Document(io.BytesIO(content))
        parsed.text = "\n".join(p.text for p in doc.paragraphs if p.text).strip()
    except Exception:
        parsed.errors.append("Could not read DOCX")
        parsed.quality = "corrupt"
        parsed.corrupt = True
        return parsed

    parsed.quality = _quality_from_text(parsed.text)
    parsed.name, parsed.phone, parsed.email = _extract_contacts(parsed.text)
    parsed.skills = _extract_skills(parsed.text)
    parsed.job_titles = _extract_job_titles(parsed.text)
    parsed.education = _extract_education(parsed.text)
    parsed.experience_lines = _extract_experience(parsed.text)
    if parsed.quality == "low_quality":
        parsed.errors.append("Low-quality CV (very little text)")
    if not parsed.phone:
        parsed.errors.append("Phone not found in CV — add manually")
    _finalize_parsed_contacts(parsed)
    return parsed


def parse_cv_bytes(content: bytes, filename: str) -> ParsedCv:
    name = str(filename or "upload").lower()
    if len(content) > MAX_FILE_BYTES:
        p = ParsedCv(filename=filename, quality="corrupt", corrupt=True)
        p.errors.append("File too large (max 15 MB)")
        return p
    if name.endswith(".pdf"):
        return parse_pdf_bytes(content, filename)
    if name.endswith(".docx"):
        return parse_docx_bytes(content, filename)
    if name.endswith(".doc"):
        p = ParsedCv(filename=filename, quality="corrupt", corrupt=True)
        p.errors.append("Old .doc format — save as PDF or DOCX")
        return p
    p = ParsedCv(filename=filename, quality="corrupt", corrupt=True)
    p.errors.append("Unsupported file type — use PDF or DOCX")
    return p


def iter_cv_files_from_zip(content: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")][:MAX_ZIP_FILES]
        for entry in names:
            lower = entry.lower()
            if lower.startswith("__macosx/") or "/." in entry:
                continue
            if not any(lower.endswith(ext) for ext in CV_EXTENSIONS):
                continue
            try:
                data = zf.read(entry)
            except Exception:
                continue
            base = entry.rsplit("/", 1)[-1]
            out.append((base, data))
    return out


def parse_uploaded_cv_files(files: list[tuple[str, bytes]]) -> list[ParsedCv]:
    parsed: list[ParsedCv] = []
    for filename, content in files:
        lower = filename.lower()
        if any(lower.endswith(ext) for ext in ZIP_EXTENSIONS):
            try:
                for inner_name, inner_bytes in iter_cv_files_from_zip(content):
                    parsed.append(parse_cv_bytes(inner_bytes, inner_name))
            except zipfile.BadZipFile:
                bad = ParsedCv(filename=filename, quality="corrupt", corrupt=True)
                bad.errors.append("Invalid ZIP file")
                parsed.append(bad)
            continue
        parsed.append(parse_cv_bytes(content, filename))
    return parsed
