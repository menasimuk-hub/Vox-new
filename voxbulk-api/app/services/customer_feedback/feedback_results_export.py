"""Export Customer Feedback results as CSV or PDF."""

from __future__ import annotations

import csv
import io
from typing import Any

from app.services.survey_report_template import _esc, logo_data_uri


def _feedback_question_rows(aggregates: list[dict[str, Any]]) -> str:
    rows_html: list[str] = []
    for block in aggregates:
        question = _esc(block.get("question") or "Question")
        total = int(block.get("total") or 0)
        breakdown = list(block.get("breakdown") or [])
        if not breakdown:
            responses = list(block.get("responses") or [])
            if not responses:
                rows_html.append(
                    f"<tr><td><strong>{question}</strong></td><td colspan='4'>No answers recorded</td></tr>"
                )
                continue
            base = total or sum(int(r.get("count") or 0) for r in responses) or 1
            for idx, row in enumerate(responses[:5]):
                label = _esc(row.get("label") or row.get("answer") or "—")
                count = int(row.get("count") or 0)
                pct = round((count / base) * 100)
                q_cell = (
                    f"<strong>{question}</strong><br/><span style='color:#666;font-size:10px'>{total} responses</span>"
                    if idx == 0
                    else ""
                )
                color = "#1a7a52" if pct >= 50 else "#1854a8"
                bar = (
                    f"<div style='background:#e2e2e2;border-radius:4px;height:8px;width:120px'>"
                    f"<div style='background:{color};height:8px;width:{max(4, pct)}%;border-radius:4px'></div></div>"
                )
                rows_html.append(
                    f"<tr><td>{q_cell}</td><td>{label}</td><td style='text-align:right'>{count}</td>"
                    f"<td style='text-align:right'>{pct}%</td><td>{bar}</td></tr>"
                )
            continue

        for idx, item in enumerate(breakdown):
            label = _esc(item.get("label") or item.get("key") or "—")
            count = int(item.get("count") or 0)
            pct = int(item.get("pct") or 0)
            key = str(item.get("key") or "").lower()
            if key in {"excellent", "yes", "good"}:
                color = "#1a7a52"
            elif key in {"poor", "no"}:
                color = "#a32020"
            else:
                color = "#b45309"
            q_cell = (
                f"<strong>{question}</strong><br/><span style='color:#666;font-size:10px'>{total} responses</span>"
                if idx == 0
                else ""
            )
            bar = (
                f"<div style='background:#e2e2e2;border-radius:4px;height:8px;width:120px'>"
                f"<div style='background:{color};height:8px;width:{max(4, pct)}%;border-radius:4px'></div></div>"
            )
            rows_html.append(
                f"<tr><td>{q_cell}</td><td>{label}</td><td style='text-align:right'>{count}</td>"
                f"<td style='text-align:right'>{pct}%</td><td>{bar}</td></tr>"
            )
    return "".join(rows_html) if rows_html else (
        "<tr><td colspan='5' style='color:#666'>No aggregated answers yet.</td></tr>"
    )


def _respondent_rows(respondents: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for r in respondents[:100]:
        phone = _esc(r.get("phone") or "—")
        sentiment = _esc(r.get("sentiment_label") or "neutral")
        flagged = "Yes" if r.get("flagged") or r.get("is_unhappy") else "No"
        when = _esc(r.get("completed_at") or r.get("started_at") or "")
        loc = _esc(r.get("location_name") or "")
        quote = _esc(r.get("quote") or "")
        rows.append(
            f"<tr><td>{phone}</td><td>{sentiment}</td><td>{flagged}</td>"
            f"<td>{loc}</td><td>{when}</td><td>{quote}</td></tr>"
        )
    return "".join(rows) if rows else "<tr><td colspan='6'>No respondents yet.</td></tr>"


def build_feedback_results_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    loc_name = payload.get("location_name") or "All locations"
    writer.writerow(["Customer Feedback Results", loc_name])
    writer.writerow(["Sessions", summary.get("sessions", "")])
    writer.writerow(["Completed", summary.get("completed_sessions", "")])
    writer.writerow(["Responses", summary.get("responses", "")])
    writer.writerow(["Scans", summary.get("total_scans", "")])
    writer.writerow(["Satisfaction %", summary.get("satisfaction_pct", "")])
    writer.writerow(["Would recommend %", summary.get("recommend_pct", "")])
    writer.writerow(["Unhappy count", summary.get("unhappy_count", "")])
    writer.writerow([])
    writer.writerow(["Question", "Option", "Count", "Percent"])
    for block in payload.get("aggregates") or []:
        question = str(block.get("question") or "")
        breakdown = block.get("breakdown") or []
        if breakdown:
            for idx, item in enumerate(breakdown):
                writer.writerow(
                    [
                        question if idx == 0 else "",
                        item.get("label") or item.get("key"),
                        item.get("count"),
                        f"{item.get('pct')}%",
                    ]
                )
        else:
            for idx, row in enumerate(block.get("responses") or []):
                writer.writerow([question if idx == 0 else "", row.get("answer"), row.get("count"), ""])
    writer.writerow([])
    writer.writerow(["Respondents"])
    writer.writerow(["Phone", "Sentiment", "Flagged", "Location", "Completed at", "Quote"])
    for row in payload.get("respondents") or []:
        writer.writerow(
            [
                row.get("phone") or "",
                row.get("sentiment_label") or "",
                "Yes" if row.get("flagged") or row.get("is_unhappy") else "No",
                row.get("location_name") or "",
                row.get("completed_at") or row.get("started_at") or "",
                row.get("quote") or "",
            ]
        )
    writer.writerow([])
    writer.writerow(["When", "Location", "Question", "Answer (English)", "Original", "Translation status", "Phone"])
    for row in payload.get("rows") or []:
        writer.writerow(
            [
                row.get("created_at"),
                row.get("location_name"),
                row.get("question") or row.get("question_key"),
                row.get("answer_text_en") or row.get("translated_text") or row.get("answer_text"),
                row.get("original_text") or "",
                row.get("translation_status") or "",
                row.get("visitor_phone") or "",
            ]
        )
    return buf.getvalue()


def build_feedback_results_export_html(payload: dict[str, Any], *, logo_uri: str | None = None) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    loc_name = _esc(payload.get("location_name") or "All locations")
    aggregates = payload.get("aggregates") or []
    ai = payload.get("ai") if isinstance(payload.get("ai"), dict) else {}
    recommendations = ai.get("recommendations") or []
    themes = ai.get("themes") or []
    respondents = payload.get("respondents") or []

    logo_uri = logo_uri if logo_uri is not None else logo_data_uri()
    logo_html = (
        f'<img src="{logo_uri}" alt="VOXBULK" style="height:28px;width:auto;max-width:180px"/>'
        if logo_uri
        else ""
    )

    completed = int(summary.get("completed_sessions") or 0)
    scans = int(summary.get("total_scans") or 0) or completed or 1
    response_rate = summary.get("completion_rate_pct")
    if response_rate is None and scans:
        response_rate = round((completed / scans) * 100)
    response_rate = int(response_rate or 0)
    satisfaction = summary.get("satisfaction_pct")
    satisfaction_label = f"{int(satisfaction)}%" if satisfaction is not None else "—"
    recommend = summary.get("recommend_pct")
    recommend_label = f"{int(recommend)}%" if recommend is not None else "—"
    unhappy = int(summary.get("unhappy_count") or 0)

    sentiment = summary.get("sentiment_counts") or {}
    sent_total = sum(int(v or 0) for v in sentiment.values()) if isinstance(sentiment, dict) else 0
    sent_rows = []
    for label, key, color in (
        ("Happy", "happy", "#1a7a52"),
        ("Neutral", "neutral", "#1854a8"),
        ("Unhappy", "unhappy", "#a32020"),
    ):
        count = int(sentiment.get(key) or 0) if isinstance(sentiment, dict) else 0
        pct = round((count / sent_total) * 100) if sent_total else 0
        sent_rows.append(
            f"<tr><td>{label}</td><td style='text-align:right'>{count}</td>"
            f"<td style='text-align:right'>{pct}%</td>"
            f"<td><div style='background:#e2e2e2;height:8px;border-radius:4px'>"
            f"<div style='width:{max(4, pct)}%;background:{color};height:8px;border-radius:4px'></div></div></td></tr>"
        )

    theme_rows = []
    for theme in themes[:6]:
        if not isinstance(theme, dict):
            continue
        label = _esc(theme.get("label") or "Theme")
        value = int(theme.get("value") or 0)
        sentiment_label = _esc(theme.get("sentiment") or "mixed")
        color = "#1a7a52" if sentiment_label == "positive" else "#a32020" if sentiment_label == "negative" else "#b45309"
        theme_rows.append(
            f"<tr><td>{label}</td><td style='text-align:right'>{value}%</td>"
            f"<td>{sentiment_label}</td>"
            f"<td><div style='background:#e2e2e2;height:8px;border-radius:4px;width:120px'>"
            f"<div style='width:{max(4, min(100, value * 2))}%;background:{color};height:8px;border-radius:4px'></div></div></td></tr>"
        )

    action_rows = []
    for rec in recommendations[:5]:
        if not isinstance(rec, dict):
            continue
        action_rows.append(
            f"<tr><td><strong>{_esc(rec.get('title') or 'Recommendation')}</strong><br/>"
            f"{_esc(rec.get('text') or '')}</td><td>{_esc(rec.get('impact') or 'Medium')}</td></tr>"
        )
    if not action_rows:
        action_rows.append("<tr><td colspan='2'>Recommendations will appear once enough responses are analysed.</td></tr>")

    question_rows = _feedback_question_rows(aggregates)
    client_rows = _respondent_rows(respondents)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Feedback Results</title></head>
<body style="font-family:Helvetica,Arial,sans-serif;font-size:11px;color:#0f0f0f;margin:24px">
  <table style="width:100%;border-bottom:1px solid #e2e2e2;margin-bottom:16px"><tr>
    <td>{logo_html}</td>
    <td style="text-align:right;color:#787878;font-size:9px">Customer feedback report<br/>Confidential</td>
  </tr></table>

  <div style="font-size:9px;color:#787878;text-transform:uppercase;letter-spacing:.08em">Customer Feedback</div>
  <h1 style="font-size:22px;margin:4px 0 16px">Results — {loc_name}</h1>

  <table style="width:100%;margin-bottom:18px;border-collapse:collapse">
    <tr>
      <td style="padding:8px;border:1px solid #e2e2e2;text-align:center"><div style="font-size:18px;font-weight:700">{completed}</div><div style="font-size:9px;color:#787878">Completed</div></td>
      <td style="padding:8px;border:1px solid #e2e2e2;text-align:center"><div style="font-size:18px;font-weight:700">{response_rate}%</div><div style="font-size:9px;color:#787878">Response rate</div></td>
      <td style="padding:8px;border:1px solid #e2e2e2;text-align:center"><div style="font-size:18px;font-weight:700">{satisfaction_label}</div><div style="font-size:9px;color:#787878">Satisfaction</div></td>
      <td style="padding:8px;border:1px solid #e2e2e2;text-align:center"><div style="font-size:18px;font-weight:700">{unhappy}</div><div style="font-size:9px;color:#787878">Unhappy</div></td>
    </tr>
  </table>

  <h2 style="font-size:14px;margin:16px 0 8px">Key metrics</h2>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px" border="1" cellpadding="6">
    <tr style="background:#f6f5f2"><th align="left">Metric</th><th align="left">Value</th></tr>
    <tr><td>Would recommend</td><td>{recommend_label}</td></tr>
    <tr><td>Total scans</td><td>{scans}</td></tr>
    <tr><td>Total responses</td><td>{int(summary.get('responses') or 0)}</td></tr>
    <tr><td>Sessions started</td><td>{int(summary.get('sessions') or 0)}</td></tr>
  </table>

  <h2 style="font-size:14px;margin:16px 0 8px">Sentiment</h2>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px" border="1" cellpadding="6">
    <tr style="background:#f6f5f2"><th align="left">Tone</th><th align="right">Count</th><th align="right">%</th><th align="left">Distribution</th></tr>
    {''.join(sent_rows) if sent_rows else "<tr><td colspan='4'>No sentiment data yet.</td></tr>"}
  </table>

  <h2 style="font-size:14px;margin:16px 0 8px">Question breakdown</h2>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px" border="1" cellpadding="6">
    <tr style="background:#f6f5f2"><th align="left">Question</th><th align="left">Option</th><th align="right">Count</th><th align="right">%</th><th align="left">Bar</th></tr>
    {question_rows}
  </table>

  <h2 style="font-size:14px;margin:16px 0 8px">AI themes</h2>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px" border="1" cellpadding="6">
    <tr style="background:#f6f5f2"><th align="left">Theme</th><th align="right">Mention</th><th align="left">Sentiment</th><th align="left">Bar</th></tr>
    {''.join(theme_rows) if theme_rows else "<tr><td colspan='4'>Themes will appear once enough responses are analysed.</td></tr>"}
  </table>

  <h2 style="font-size:14px;margin:16px 0 8px">Recommended actions</h2>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px" border="1" cellpadding="6">
    <tr style="background:#f6f5f2"><th align="left">Action</th><th align="left">Impact</th></tr>
    {''.join(action_rows)}
  </table>

  <h2 style="font-size:14px;margin:16px 0 8px">Clients / respondents</h2>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px" border="1" cellpadding="6">
    <tr style="background:#f6f5f2"><th align="left">Mobile</th><th align="left">Sentiment</th><th align="left">Flagged</th><th align="left">Location</th><th align="left">When</th><th align="left">Quote</th></tr>
    {client_rows}
  </table>

  <p style="font-size:9px;color:#787878;margin-top:24px">Includes full mobile numbers for unhappy customer follow-up. Do not share outside your organisation.</p>
</body></html>"""


def build_feedback_results_pdf(payload: dict[str, Any]) -> bytes:
    from app.services.invoice_pdf_service import render_html_to_pdf_bytes

    html = build_feedback_results_export_html(payload)
    return render_html_to_pdf_bytes(html)
