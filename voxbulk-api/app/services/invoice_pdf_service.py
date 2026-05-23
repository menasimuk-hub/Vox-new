from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>.*?</style>", re.I | re.S)
_SCRIPT_BLOCK_RE = re.compile(r"<script[^>]*>.*?</script>", re.I | re.S)

# fpdf2 default Helvetica is Latin-1 only; normalize common Unicode punctuation first.
_UNICODE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("\u2014", "-"),  # em dash
    ("\u2013", "-"),  # en dash
    ("\u2018", "'"),
    ("\u2019", "'"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u2026", "..."),
    ("\u00a0", " "),
)


def _ascii_safe_for_pdf(text: str) -> str:
    out = str(text or "")
    for src, dst in _UNICODE_REPLACEMENTS:
        out = out.replace(src, dst)
    try:
        out.encode("latin-1")
    except UnicodeEncodeError:
        out = out.encode("latin-1", errors="replace").decode("latin-1")
    return out


def _prepare_html_for_fpdf(html: str) -> str:
    clean = _ascii_safe_for_pdf(str(html or "").strip())
    clean = _STYLE_BLOCK_RE.sub("", clean)
    clean = _SCRIPT_BLOCK_RE.sub("", clean)
    clean = re.sub(r"<meta[^>]*>", "", clean, flags=re.I)
    clean = re.sub(r"<title[^>]*>.*?</title>", "", clean, flags=re.I | re.S)
    clean = re.sub(r"<!DOCTYPE[^>]*>", "", clean, flags=re.I)
    clean = re.sub(r"<html[^>]*>", "", clean, flags=re.I)
    clean = re.sub(r"</html>", "", clean, flags=re.I)
    clean = re.sub(r"<head[^>]*>.*?</head>", "", clean, flags=re.I | re.S)
    clean = re.sub(r"<body[^>]*>", "", clean, flags=re.I)
    clean = re.sub(r"</body>", "", clean, flags=re.I)
    return clean.strip()


def render_html_to_pdf_bytes(html: str) -> bytes:
    clean = str(html or "").strip()
    if not clean:
        raise ValueError("HTML content is empty")
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise RuntimeError("fpdf2 is not installed") from e

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    try:
        pdf.write_html(_prepare_html_for_fpdf(clean))
    except Exception as exc:
        logger.warning("invoice_pdf_html_fallback", extra={"error": str(exc)})
        plain = _ascii_safe_for_pdf(re.sub(r"<[^>]+>", "\n", clean))
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 5, plain or "Invoice")
    out = pdf.output()
    return bytes(out)
