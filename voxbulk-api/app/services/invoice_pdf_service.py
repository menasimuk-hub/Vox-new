from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>.*?</style>", re.I | re.S)
_SCRIPT_BLOCK_RE = re.compile(r"<script[^>]*>.*?</script>", re.I | re.S)


def _prepare_html_for_fpdf(html: str) -> str:
    clean = str(html or "").strip()
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
        plain = re.sub(r"<[^>]+>", "\n", clean)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 5, plain or "Invoice")
    out = pdf.output()
    return bytes(out)
