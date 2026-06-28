"""Decode uploaded CSV/text bytes that may not be UTF-8.

Excel on non-English Windows often saves CSV files in a legacy single-byte
code page (Windows-1256 for Arabic, Windows-1252 for Western European) or as
UTF-16, which a naive ``bytes.decode("utf-8", errors="replace")`` turns into
"????" / replacement characters. This helper trusts byte-order marks, then
strict UTF-8, then statistical detection, so non-Latin names survive intake.
"""

from __future__ import annotations


def decode_uploaded_text(content: bytes) -> str:
    if not content:
        return ""

    # Byte-order marks are unambiguous — trust them before anything else.
    if content[:3] == b"\xef\xbb\xbf":
        return content[3:].decode("utf-8", errors="replace")
    if content[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
        return content.decode("utf-32", errors="replace")
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return content.decode("utf-16", errors="replace")

    # Strict UTF-8 only succeeds for genuine UTF-8 — no silent corruption.
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # Statistical detection handles legacy code pages (cp1256, cp1252, ...).
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(content).best()
        if best is not None:
            return str(best)
    except Exception:
        pass

    # Deterministic fallback. cp1256 (Arabic) is tried before latin-1, which
    # never raises and would otherwise mask recoverable Arabic text.
    for enc in ("cp1256", "cp1252", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")
