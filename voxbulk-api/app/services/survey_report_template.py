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

  --accent:#1a7a52; --radius:10px;

}

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

body{font-family:Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink);font-size:11px;line-height:1.4}

.page{max-width:920px;margin:0 auto;padding:20px 18px 36px}

.logo-bar{display:flex;align-items:center;justify-content:space-between;padding-bottom:12px;margin-bottom:16px;border-bottom:1px solid var(--rule)}

.logo-bar img{height:28px;width:auto;display:block;max-width:180px}

.logo-meta{font-size:9px;color:var(--ink3);text-align:right;line-height:1.35}

.report-header{display:flex;align-items:flex-end;justify-content:space-between;padding-bottom:14px;border-bottom:1.5px solid var(--ink);margin-bottom:18px;gap:12px;flex-wrap:wrap}

.report-eyebrow{font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);margin-bottom:3px}

.report-title{font-size:22px;line-height:1.08;color:var(--ink);font-weight:700}

.report-title em{color:var(--accent);font-style:italic;font-weight:700}

.report-meta{display:flex;gap:18px;flex-wrap:wrap}

.meta-val{font-size:16px;font-weight:600}

.meta-lbl{font-size:9px;color:var(--ink3)}

.split{display:grid;grid-template-columns:3fr 1fr;gap:12px;margin-bottom:12px}

.panel{background:var(--surface);border-radius:var(--radius);border:1px solid var(--rule);overflow:hidden;margin-bottom:12px;page-break-inside:avoid}

.panel-head{padding:12px 14px 10px;border-bottom:1px solid var(--rule);display:flex;justify-content:space-between;gap:8px}

.ph-eyebrow{font-size:8px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3)}

.ph-title{font-size:14px;font-weight:700;line-height:1.2}

.panel-body{padding:14px}

.nps-cards{display:grid;grid-template-columns:1.2fr 1fr 1fr 1fr;gap:8px}

.nps-main{background:var(--bg);border-radius:8px;padding:12px;text-align:center;border:1px solid var(--rule)}

.nps-big{font-size:42px;line-height:1;font-weight:700}

.nps-mood{font-size:11px;font-weight:700;margin-top:4px}

.nps-mood.good{color:var(--green)}

.nps-mood.unhappy{color:var(--red)}

.nps-mini{background:var(--bg);border-radius:8px;padding:10px;border:1px solid var(--rule)}

.nps-mini-val{font-size:18px;font-weight:700;line-height:1.1}

.nps-mini-lbl{font-size:8px;color:var(--ink3);margin-top:3px;text-transform:uppercase;letter-spacing:.04em}

.q-block{border:1px solid var(--rule);border-radius:8px;padding:10px 12px;margin-bottom:10px;page-break-inside:avoid}

.q-title{font-size:11px;font-weight:700;margin-bottom:2px;line-height:1.35}

.q-meta{font-size:9px;color:var(--ink3);margin-bottom:8px}

.q-row{display:grid;grid-template-columns:1.2fr 2fr auto auto;gap:6px;align-items:center;font-size:9px;margin-bottom:5px}

.q-track{height:5px;background:var(--bg);border-radius:20px;overflow:hidden}

.q-fill{height:100%;border-radius:20px;background:var(--green)}

.side-card{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);overflow:hidden}

.side-body{padding:12px}

.sent-row{margin-bottom:8px}

.sent-top{display:flex;justify-content:space-between;font-size:9px;margin-bottom:3px}

.sent-track{height:4px;background:var(--bg);border-radius:20px;overflow:hidden}

.sent-fill{height:100%;border-radius:20px;background:var(--green)}

.actions-head{background:var(--ink);padding:12px 14px;color:#fff}

.actions-head h3{font-size:14px;font-weight:700}

.actions-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:0}

.action-item{padding:12px;border-top:1px solid var(--rule);border-right:1px solid var(--rule);page-break-inside:avoid}

.action-item:nth-child(2n){border-right:none}

.action-title{font-size:10px;font-weight:700;margin-bottom:4px}

.action-desc{font-size:9px;color:var(--ink3);line-height:1.4}

.tag{display:inline-block;padding:2px 7px;border-radius:20px;font-size:8px;font-weight:600;background:var(--green-lt);color:var(--green)}

.footer{margin-top:14px;font-size:8px;color:var(--ink4);text-align:center}

.statbox{background:var(--bg);border-radius:8px;padding:10px;margin-bottom:8px;border:1px solid var(--rule)}

.statbox .val{font-size:18px;font-weight:700}

.statbox .lbl{font-size:8px;color:var(--ink3)}

@media print{.page{padding:10px}}

"""





def _esc(text: Any) -> str:

    return (

        str(text if text is not None else "")

        .replace("&", "&amp;")

        .replace("<", "&lt;")

        .replace(">", "&gt;")

        .replace('"', "&quot;")

    )





def _repo_root() -> Path:

    return Path(__file__).resolve().parents[3]





def logo_data_uri() -> str:

    candidates = [

        _repo_root() / "dashboard.voxbulk.com" / "dashboard-web" / "public" / "brand" / "logo-black.svg",

        _repo_root() / "admin.voxbulk.com" / "adim-web" / "public" / "brand" / "logo-black.svg",

        _repo_root() / "dashboard.voxbulk.com" / "dashboard-web" / "public" / "logo-dark.svg",

        _repo_root() / "admin.voxbulk.com" / "adim-web" / "public" / "logo-dark.svg",

        Path("/www/voxbulk/dashboard.voxbulk.com/dashboard-web/public/brand/logo-black.svg"),

        Path("/www/voxbulk/admin.voxbulk.com/adim-web/public/brand/logo-black.svg"),

        Path("/www/voxbulk/dashboard.voxbulk.com/dashboard-web/public/logo-dark.svg"),

        Path("/www/voxbulk/admin.voxbulk.com/adim-web/public/logo-dark.svg"),

    ]

    for logo in candidates:

        if logo.is_file():

            encoded = base64.b64encode(logo.read_bytes()).decode("ascii")

            return f"data:image/svg+xml;base64,{encoded}"

    return ""





def _bar_color(pct: int) -> str:

    if pct >= 80:

        return "var(--green)"

    if pct >= 65:

        return "var(--blue)"

    if pct >= 50:

        return "var(--amber)"

    return "var(--red)"





def _question_blocks(aggregates: list[dict[str, Any]]) -> str:

    blocks = []

    for block in aggregates:

        question = _esc(block.get("question") or "Question")

        block_total = max(1, int(block.get("total") or 1))

        rows = []

        for row in block.get("responses") or []:

            answer = _esc(row.get("answer") or "—")

            count = int(row.get("count") or 0)

            pct = round((count / block_total) * 100)

            rows.append(

                f"""<div class="q-row">

                  <span>{answer}</span>

                  <div class="q-track"><div class="q-fill" style="width:{max(4,pct)}%;background:{_bar_color(pct)}"></div></div>

                  <span>{pct}%</span>

                  <span>({count})</span>

                </div>"""

            )

        blocks.append(

            f"""<div class="q-block">

              <div class="q-title">{question}</div>

              <div class="q-meta">{block_total} responses</div>

              {''.join(rows) if rows else '<div class="q-meta">No answers recorded.</div>'}

            </div>"""

        )

    return "".join(blocks) if blocks else '<div class="q-meta">No aggregated answers yet.</div>'





def build_survey_results_html(payload: dict[str, Any], *, logo_uri: str | None = None) -> str:

    order = payload.get("order") or {}

    summary = payload.get("summary") or {}

    aggregates = payload.get("aggregates") or []

    recommendations = payload.get("recommendations") or []

    company = _esc(order.get("organisation_name") or order.get("goal") or "Your organisation")

    title = _esc(order.get("title") or "Survey results")

    logo_uri = logo_uri if logo_uri is not None else logo_data_uri()

    logo_html = f'<img src="{logo_uri}" alt="VOXBULK"/>' if logo_uri else ""



    nps_score = summary.get("nps_score")

    nps_label = str(summary.get("nps_label") or "").strip()

    mood_class = "good" if nps_label.lower() == "good" else "unhappy"

    promoters_pct = summary.get("nps_promoters_pct") or 0

    passives_pct = summary.get("nps_passives_pct") or 0

    detractors_pct = summary.get("nps_detractors_pct") or 0



    completed = int(summary.get("completed_count") or 0)

    total = max(1, int(summary.get("total_recipients") or completed or 1))

    response_rate = summary.get("response_rate_pct") or round((completed / total) * 100)



    period = ""

    if order.get("started_at"):

        try:

            period = datetime.fromisoformat(str(order["started_at"]).replace("Z", "+00:00")).strftime("%b %Y")

        except Exception:

            period = str(order.get("started_at") or "")[:7]



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

    for rec in recommendations[:5]:

        action_items.append(

            f"""<div class="action-item">

              <div class="action-title">{_esc(rec.get('title') or 'Recommendation')}</div>

              <div class="action-desc">{_esc(rec.get('text'))}</div>

            </div>"""

        )

    if not action_items:

        action_items.append('<div class="action-item"><div class="action-desc">Recommendations will appear once survey data is analysed.</div></div>')



    sat5 = summary.get("average_satisfaction_5")

    sat_label = f"{sat5}/5" if sat5 is not None else "—"



    logo_bar = f'<div class="logo-bar"><div>{logo_html}</div><div class="logo-meta">Anonymous aggregate report<br/>Confidential</div></div>' if logo_html else ""



    return f"""<!DOCTYPE html>

<html lang="en"><head><meta charset="utf-8"/><title>{title}</title><style>{REPORT_CSS}</style></head><body>

<div class="page">

  {logo_bar}

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

      <div class="panel-head"><div><div class="ph-eyebrow">Loyalty score</div><div class="ph-title">Net Promoter Score</div></div><span class="tag">Anonymous</span></div>

      <div class="panel-body">

        <div class="nps-cards">

          <div class="nps-main">

            <div class="nps-big">{nps_score if nps_score is not None else '—'}</div>

            <div style="font-size:9px;color:var(--ink4)">out of 100</div>

            <div class="nps-mood {mood_class}">{_esc(nps_label or '—')}</div>

          </div>

          <div class="nps-mini"><div class="nps-mini-val" style="color:var(--green)">{promoters_pct}%</div><div class="nps-mini-lbl">Promoters</div></div>

          <div class="nps-mini"><div class="nps-mini-val">{passives_pct}%</div><div class="nps-mini-lbl">Passives</div></div>

          <div class="nps-mini"><div class="nps-mini-val" style="color:var(--red)">{detractors_pct}%</div><div class="nps-mini-lbl">Detractors</div></div>

        </div>

      </div>

    </div>

    <div class="side-card">

      <div class="panel-head"><div><div class="ph-eyebrow">Sentiment</div><div class="ph-title">Overall tone</div></div></div>

      <div class="side-body">{''.join(sent_rows) if sent_rows else '<div class="q-meta">No sentiment data yet.</div>'}</div>

    </div>

  </div>

  <div class="split">

    <div class="panel">

      <div class="panel-head"><div><div class="ph-eyebrow">Questions</div><div class="ph-title">Answer summary</div></div><span class="tag">{len(aggregates)} questions</span></div>

      <div class="panel-body">{_question_blocks(aggregates)}</div>

    </div>

    <div class="side-card">

      <div class="panel-head"><div><div class="ph-eyebrow">Snapshot</div><div class="ph-title">Key metrics</div></div></div>

      <div class="side-body">

        <div class="statbox"><div class="val">{sat_label}</div><div class="lbl">Average satisfaction</div></div>

        <div class="statbox"><div class="val">{summary.get('recommend_pct') or '—'}%</div><div class="lbl">Would recommend</div></div>

        <div class="statbox"><div class="val">{_esc(summary.get('average_call_duration_label') or '—')}</div><div class="lbl">Avg call length</div></div>

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

