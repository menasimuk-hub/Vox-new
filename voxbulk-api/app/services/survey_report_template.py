from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Any

REPORT_CSS = """
:root {
  --ink:#0f0f0f; --ink2:#3a3a3a; --ink3:#787878; --ink4:#b0b0b0;
  --rule:#e2e2e2; --bg:#f6f5f2; --surface:#ffffff;
  --green:#1a7a52; --green-lt:#e3f5ec; --blue:#1854a8; --blue-lt:#e5edf9;
  --amber:#b05e10; --amber-lt:#fdf0e2; --red:#a32020; --red-lt:#fce8e8;
  --accent:#1a7a52; --radius:12px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink);font-size:13px;line-height:1.5}
.page{max-width:980px;margin:0 auto;padding:28px 24px 48px}
.logo-bar{display:flex;align-items:center;justify-content:space-between;padding-bottom:18px;margin-bottom:22px;border-bottom:1px solid var(--rule)}
.logo-bar img{height:34px;width:auto;display:block}
.logo-meta{font-size:10px;color:var(--ink3);text-align:right}
.report-header{display:flex;align-items:flex-end;justify-content:space-between;padding-bottom:18px;border-bottom:1.5px solid var(--ink);margin-bottom:24px}
.report-eyebrow{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3);margin-bottom:4px}
.report-title{font-size:28px;line-height:1.08;color:var(--ink);font-weight:700}
.report-title em{color:var(--accent);font-style:italic;font-weight:700}
.report-meta{display:flex;gap:22px}
.meta-val{font-size:18px;font-weight:600}
.meta-lbl{font-size:10px;color:var(--ink3)}
.split{display:grid;grid-template-columns:3fr 1fr;gap:16px;margin-bottom:16px}
.panel{background:var(--surface);border-radius:var(--radius);border:1px solid var(--rule);overflow:hidden;margin-bottom:16px}
.panel-head{padding:16px 18px 12px;border-bottom:1px solid var(--rule);display:flex;justify-content:space-between;gap:10px}
.ph-eyebrow{font-size:9px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3)}
.ph-title{font-size:17px;font-weight:700;line-height:1.2}
.panel-body{padding:18px}
.nps-main{display:grid;grid-template-columns:auto 1fr 1fr 1fr;gap:0;align-items:stretch}
.nps-big{font-size:64px;line-height:1;letter-spacing:-2px;font-weight:700}
.nps-stat{padding-left:18px;border-left:1px solid var(--rule)}
.nps-stat-val{font-size:30px;line-height:1;font-weight:700}
.nps-stat-label{font-size:10px;color:var(--ink3)}
.feat-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px 24px}
.feat-top{display:flex;justify-content:space-between;align-items:baseline}
.feat-name{font-size:12px;font-weight:600}
.feat-pct{font-size:18px;font-weight:600}
.feat-track{height:8px;background:var(--bg);border-radius:20px;overflow:hidden;margin:6px 0 4px}
.feat-fill{height:100%;border-radius:20px;background:var(--green)}
.feat-count{font-size:10px;color:var(--ink4)}
.side-card{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);overflow:hidden}
.side-body{padding:14px 16px}
.sent-row{margin-bottom:10px}
.sent-top{display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px}
.sent-track{height:5px;background:var(--bg);border-radius:20px;overflow:hidden}
.sent-fill{height:100%;border-radius:20px;background:var(--green)}
.actions-head{background:var(--ink);padding:16px 20px;color:#fff}
.actions-head h3{font-size:18px;font-weight:700}
.actions-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:0}
.action-item{padding:16px;border-top:1px solid var(--rule);border-right:1px solid var(--rule)}
.action-item:nth-child(2n){border-right:none}
.action-title{font-size:12px;font-weight:600;margin-bottom:6px}
.action-desc{font-size:11px;color:var(--ink3);line-height:1.45}
.tag{display:inline-block;padding:3px 8px;border-radius:20px;font-size:10px;font-weight:600;background:var(--green-lt);color:var(--green)}
.footer{margin-top:20px;font-size:10px;color:var(--ink4);text-align:center}
@media print{.page{padding:12px}}
"""


def _esc(text: Any) -> str:
    return (
        str(text if text is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def logo_data_uri() -> str:
    root = Path(__file__).resolve().parents[2]
    logo = root / "dashboard.voxbulk.com" / "dashboard-web" / "public" / "logo-dark.svg"
    if not logo.is_file():
        return ""
    raw = logo.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _bar_color(pct: int) -> str:
    if pct >= 80:
        return "var(--green)"
    if pct >= 65:
        return "var(--blue)"
    if pct >= 50:
        return "var(--amber)"
    return "var(--red)"


def _nps_parts(summary: dict[str, Any]) -> tuple[int, int, int, int]:
    nps = summary.get("nps_score")
    score = int(round(float(nps))) if nps is not None else 0
    completed = max(1, int(summary.get("completed_count") or 1))
    promoters = int(round(completed * 0.55))
    passives = int(round(completed * 0.25))
    detractors = max(0, completed - promoters - passives)
    return score, promoters, passives, detractors


def build_survey_results_html(payload: dict[str, Any], *, logo_uri: str | None = None) -> str:
    order = payload.get("order") or {}
    summary = payload.get("summary") or {}
    aggregates = payload.get("aggregates") or []
    recommendations = payload.get("recommendations") or []
    company = _esc(order.get("organisation_name") or order.get("goal") or "Your organisation")
    title = _esc(order.get("title") or "Survey results")
    logo_uri = logo_uri if logo_uri is not None else logo_data_uri()
    logo_html = f'<img src="{logo_uri}" alt="VOXBULK"/>' if logo_uri else "<strong>VOXBULK</strong>"

    nps_score, promoters, passives, detractors = _nps_parts(summary)
    completed = int(summary.get("completed_count") or 0)
    total = max(1, int(summary.get("total_recipients") or completed or 1))
    response_rate = summary.get("response_rate_pct") or round((completed / total) * 100)

    period = ""
    if order.get("started_at"):
        try:
            period = datetime.fromisoformat(str(order["started_at"]).replace("Z", "+00:00")).strftime("%b %Y")
        except Exception:
            period = str(order.get("started_at") or "")[:7]

    feat_blocks = []
    for block in aggregates[:6]:
        question = _esc(block.get("question") or "Question")
        block_total = max(1, int(block.get("total") or 1))
        top = (block.get("responses") or [{}])[0]
        top_answer = _esc(top.get("answer") or "—")
        top_count = int(top.get("count") or 0)
        pct = round((top_count / block_total) * 100)
        feat_blocks.append(
            f"""<div class="feat-item">
              <div class="feat-top"><span class="feat-name">{question}</span><span class="feat-pct">{pct}%</span></div>
              <div class="feat-track"><div class="feat-fill" style="width:{pct}%;background:{_bar_color(pct)}"></div></div>
              <span class="feat-count">{block_total} responses · Top: {top_answer}</span>
            </div>"""
        )

    sentiment = summary.get("sentiment_counts") or {}
    sent_rows = []
    for label, key, color in (
        ("Positive", "positive", "var(--green)"),
        ("Neutral", "neutral", "var(--blue)"),
        ("Negative", "negative", "var(--red)"),
    ):
        count = int(sentiment.get(key) or 0)
        pct = round((count / max(1, completed)) * 100) if completed else 0
        sent_rows.append(
            f"""<div class="sent-row"><div class="sent-top"><span>{label}</span><span>{pct}%</span></div>
            <div class="sent-track"><div class="sent-fill" style="width:{max(4,pct)}%;background:{color}"></div></div></div>"""
        )

    action_items = []
    for idx, rec in enumerate(recommendations[:4]):
        action_items.append(
            f"""<div class="action-item">
              <div class="action-title">Recommendation {idx + 1}</div>
              <div class="action-desc">{_esc(rec.get('text'))}</div>
            </div>"""
        )
    if not action_items:
        action_items.append(
            '<div class="action-item"><div class="action-desc">Recommendations will appear once enough calls are analysed.</div></div>'
        )

    sat5 = summary.get("average_satisfaction_5")
    sat_label = f"{sat5}/5" if sat5 is not None else "—"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>{title}</title><style>{REPORT_CSS}</style></head><body>
<div class="page">
  <div class="logo-bar">
    <div>{logo_html}</div>
    <div class="logo-meta">Anonymous aggregate report<br/>Confidential · Generated by VOXBULK</div>
  </div>
  <div class="report-header">
    <div>
      <div class="report-eyebrow">{company}</div>
      <div class="report-title">Survey <em>Results</em><br/>{title}</div>
    </div>
    <div class="report-meta">
      <div><div class="meta-val">{completed}</div><div class="meta-lbl">Responses</div></div>
      <div><div class="meta-val">{response_rate}%</div><div class="meta-lbl">Response rate</div></div>
      <div><div class="meta-val">{_esc(period or '—')}</div><div class="meta-lbl">Field period</div></div>
    </div>
  </div>
  <div class="split">
    <div class="panel">
      <div class="panel-head"><div><div class="ph-eyebrow">Block 01 — Loyalty</div><div class="ph-title">Net Promoter Score</div></div><span class="tag">Anonymous</span></div>
      <div class="panel-body">
        <div class="nps-main">
          <div style="padding-right:24px;border-right:1px solid var(--rule);margin-right:24px">
            <div class="nps-big">{nps_score if nps_score is not None else '—'}</div>
            <div style="font-size:12px;color:var(--ink4)">/100 NPS</div>
          </div>
          <div class="nps-stat"><div class="nps-stat-val" style="color:var(--green)">{round(promoters/max(1,completed)*100)}%</div><div class="nps-stat-label">Promoters</div></div>
          <div class="nps-stat"><div class="nps-stat-val">{round(passives/max(1,completed)*100)}%</div><div class="nps-stat-label">Passives</div></div>
          <div class="nps-stat"><div class="nps-stat-val" style="color:var(--red)">{round(detractors/max(1,completed)*100)}%</div><div class="nps-stat-label">Detractors</div></div>
        </div>
      </div>
    </div>
    <div class="side-card">
      <div class="panel-head"><div><div class="ph-eyebrow">Sentiment</div><div class="ph-title">Call tone</div></div></div>
      <div class="side-body">{''.join(sent_rows) if sent_rows else '<div class="feat-count">No sentiment data yet.</div>'}</div>
    </div>
  </div>
  <div class="split">
    <div class="panel">
      <div class="panel-head"><div><div class="ph-eyebrow">Block 02 — Questions</div><div class="ph-title">Answer summary</div></div><span class="tag">{len(aggregates)} questions</span></div>
      <div class="panel-body"><div class="feat-grid">{''.join(feat_blocks) if feat_blocks else '<div class="feat-count">No aggregated answers yet.</div>'}</div></div>
    </div>
    <div class="side-card">
      <div class="panel-head"><div><div class="ph-eyebrow">Snapshot</div><div class="ph-title">Key metrics</div></div></div>
      <div class="side-body">
        <div style="background:var(--bg);border-radius:8px;padding:12px;margin-bottom:10px"><div style="font-size:26px;font-weight:700">{sat_label}</div><div style="font-size:10px;color:var(--ink3)">Average satisfaction</div></div>
        <div style="background:var(--bg);border-radius:8px;padding:12px;margin-bottom:10px"><div style="font-size:26px;font-weight:700">{summary.get('recommend_pct') or '—'}%</div><div style="font-size:10px;color:var(--ink3)">Would recommend</div></div>
        <div style="background:var(--bg);border-radius:8px;padding:12px"><div style="font-size:26px;font-weight:700">{_esc(summary.get('average_call_duration_label') or '—')}</div><div style="font-size:10px;color:var(--ink3)">Avg call length</div></div>
      </div>
    </div>
  </div>
  <div class="panel">
    <div class="actions-head"><h3>Recommended actions</h3></div>
    <div class="actions-grid">{''.join(action_items)}</div>
  </div>
  <div class="footer">Individual names and transcripts are never included in customer-facing survey reports.</div>
</div>
</body></html>"""
