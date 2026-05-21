import json
import re
from pathlib import Path

html = Path(r"c:\Users\zaghlol\Downloads\VoxLegal.html").read_text(encoding="utf-8")
pages = ["terms", "privacy", "cookies", "gdpr", "legal"]
out: dict[str, str] = {}

for i, p in enumerate(pages):
    start_pat = rf'<div class="page(?: active)?" id="page-{p}">'
    start = re.search(start_pat, html)
    if not start:
        out[p] = ""
        continue
    start_idx = start.end()
    next_page = pages[i + 1] if i + 1 < len(pages) else None
    if next_page:
        end_pat = rf'<div class="page" id="page-{next_page}">'
        end = re.search(end_pat, html[start_idx:])
        end_idx = start_idx + end.start() if end else len(html)
    else:
        end_idx = html.find("<script>", start_idx)
        if end_idx == -1:
            end_idx = len(html)
    chunk = html[start_idx:end_idx].strip()
    # Drop accidental wrapper close tags / HTML comments from extraction.
    chunk = re.sub(r"</div>\s*$", "", chunk).strip()
    chunk = re.sub(r"<!--.*?-->\s*$", "", chunk, flags=re.S).strip()
    chunk = re.sub(r'\sonclick="togCookie\(this\)"', "", chunk)
    out[p] = chunk

dest = Path(__file__).resolve().parents[1] / "app" / "data" / "legal_default_bodies.json"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print({k: len(v) for k, v in out.items()})
