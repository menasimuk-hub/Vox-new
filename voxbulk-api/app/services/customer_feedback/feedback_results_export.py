"""Export Customer Feedback results as CSV or PDF."""

from __future__ import annotations

import csv
import io
from typing import Any


def build_feedback_results_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    writer.writerow(["Customer Feedback Results"])
    writer.writerow(["Sessions", summary.get("sessions", "")])
    writer.writerow(["Completed", summary.get("completed_sessions", "")])
    writer.writerow(["Responses", summary.get("responses", "")])
    writer.writerow(["Scans", summary.get("total_scans", "")])
    writer.writerow(["Satisfaction %", summary.get("satisfaction_pct", "")])
    writer.writerow([])
    writer.writerow(["Question", "Answer", "Count"])
    for block in payload.get("aggregates") or []:
        question = str(block.get("question") or "")
        for row in block.get("responses") or []:
            writer.writerow([question, row.get("answer"), row.get("count")])
    writer.writerow([])
    writer.writerow(["When", "Location", "Question", "Answer", "Phone"])
    for row in payload.get("rows") or []:
        writer.writerow(
            [
                row.get("created_at"),
                row.get("location_name"),
                row.get("question_key"),
                row.get("answer_text"),
                row.get("visitor_phone") or "",
            ]
        )
    return buf.getvalue()


def build_feedback_results_export_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    loc_name = str(payload.get("location_name") or "All locations")
    rows_html = []
    for block in payload.get("aggregates") or []:
        q = str(block.get("question") or "")
        rows_html.append(f"<h3>{_esc(q)}</h3><ul>")
        for item in block.get("breakdown") or block.get("responses") or []:
            label = item.get("label") or item.get("answer")
            pct = item.get("pct")
            count = item.get("count")
            if pct is not None:
                rows_html.append(f"<li>{_esc(label)}: {pct}% ({count})</li>")
            else:
                rows_html.append(f"<li>{_esc(label)}: {count}</li>")
        rows_html.append("</ul>")

    ai = payload.get("ai") if isinstance(payload.get("ai"), dict) else {}
    rec_html = "".join(
        f"<li><strong>{_esc(r.get('title'))}</strong> — {_esc(r.get('text'))}</li>"
        for r in (ai.get("recommendations") or [])[:5]
        if isinstance(r, dict)
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Feedback Results</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 32px; color: #111; }}
h1 {{ font-size: 22px; }}
.kpi {{ display: flex; gap: 24px; flex-wrap: wrap; margin: 16px 0; }}
.kpi div {{ background: #f4f4f5; padding: 12px 16px; border-radius: 8px; }}
</style></head><body>
<h1>Customer Feedback Results — {_esc(loc_name)}</h1>
<div class="kpi">
  <div><div>Completed</div><strong>{summary.get('completed_sessions', 0)}</strong></div>
  <div><div>Satisfaction</div><strong>{summary.get('satisfaction_pct', '—')}%</strong></div>
  <div><div>Unhappy</div><strong>{summary.get('unhappy_count', 0)}</strong></div>
  <div><div>Scans</div><strong>{summary.get('total_scans', 0)}</strong></div>
</div>
<h2>Questions</h2>
{''.join(rows_html)}
<h2>AI recommended actions</h2>
<ul>{rec_html or '<li>No recommendations yet.</li>'}</ul>
</body></html>"""


def build_feedback_results_pdf(payload: dict[str, Any]) -> bytes:
    from app.services.invoice_pdf_service import render_html_to_pdf_bytes

    html = build_feedback_results_export_html(payload)
    return render_html_to_pdf_bytes(html)


def _esc(value: Any) -> str:
    text = str(value or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
