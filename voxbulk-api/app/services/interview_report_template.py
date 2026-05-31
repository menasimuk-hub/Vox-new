"""Render per-candidate AI interview report HTML."""

from __future__ import annotations

import html
from typing import Any

from app.services.brand_assets import asset_path, email_logo_url, logo_data_uri


REPORT_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#1a1a18;--ink-2:#4a4a46;--ink-3:#888780;--surface:#faf9f6;--surface-2:#f1efe8;--surface-3:#e5e3d8;--accent:#185fa5;--accent-light:#e6f1fb;--success:#3b6d11;--success-light:#eaf3de;--warn:#854f0b;--warn-light:#faeeda;--danger:#a32d2d;--danger-light:#fcebeb;--border:rgba(26,26,24,.12);--radius:10px}
@page{size:A4;margin:14mm 12mm}
body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:#fff;color:var(--ink);font-size:14px;line-height:1.55}
.page{max-width:100%;margin:0 auto;padding:0}
.logo-bar{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.logo-bar img{height:28px;width:auto;max-width:160px}
.report-header{display:block;margin-bottom:24px;padding-bottom:20px;border-bottom:1px solid var(--border)}
.report-header-top{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap}
.report-badge{font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);margin-bottom:8px}
.report-title{font-size:26px;line-height:1.2;margin-bottom:6px;font-weight:700}
.report-subtitle{font-size:13px;color:var(--ink-2)}
.candidate-meta{text-align:right;min-width:140px}
.candidate-avatar{width:48px;height:48px;border-radius:50%;background:var(--accent-light);color:var(--accent);font-weight:600;font-size:15px;display:flex;align-items:center;justify-content:center;margin-left:auto;margin-bottom:8px}
.meta-row{font-size:12px;color:var(--ink-2);margin-bottom:3px}
.score-table{width:100%;border-collapse:separate;border-spacing:8px 0;margin:0 -8px 28px}
.score-table td{background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius);padding:14px 12px;vertical-align:top;width:25%}
.score-card-label{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);margin-bottom:6px}
.score-card-value{font-size:28px;line-height:1;font-weight:700}
.score-card-value span{font-size:16px;opacity:.5;font-weight:500}
.section{margin-bottom:32px;page-break-inside:avoid}
.section-title{font-size:18px;font-weight:700;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.criteria-row{display:block;padding:12px 14px;background:#fff;border-radius:var(--radius);border:1px solid var(--border);margin-bottom:10px;page-break-inside:avoid}
.criteria-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:8px}
.criteria-label{font-size:13px;font-weight:600}.criteria-sublabel{font-size:11px;color:var(--ink-3);margin-top:2px}
.criteria-score{font-size:13px;font-weight:700;color:var(--accent);white-space:nowrap}
.progress-wrap{height:6px;background:var(--surface-3);border-radius:99px;overflow:hidden}
.progress-fill{height:100%;border-radius:99px;background:#378add}
.competency-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:14px;margin-bottom:10px;page-break-inside:avoid}
.comp-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px}
.comp-name{font-size:13px;font-weight:600}.comp-category{font-size:11px;color:var(--ink-3);margin-top:2px}
.comp-score{font-size:11px;font-weight:600;color:var(--accent);white-space:nowrap}
.comp-bar{height:4px;background:var(--surface-3);border-radius:99px;margin:8px 0;overflow:hidden}
.comp-note{font-size:12px;color:var(--ink-2);padding-top:8px;border-top:1px dashed var(--border);line-height:1.5}
.interview-highlight,.concern-box{padding:14px;border-radius:var(--radius);margin-top:12px;border:1px solid var(--border);background:#fff;page-break-inside:avoid}
.highlight-label,.concern-label{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);margin-bottom:6px}
.rec-banner{padding:16px;border-radius:var(--radius);margin-bottom:14px;border:1px solid var(--border);background:#fff;page-break-inside:avoid}
.rec-banner.proceed{border-color:#c0dd97;background:var(--success-light)}
.rec-verdict{font-size:16px;font-weight:700;margin-bottom:4px}
.rec-desc{font-size:13px;color:var(--ink-2);line-height:1.5}
.rec-point{display:flex;gap:10px;margin-bottom:12px;font-size:12px;line-height:1.5;page-break-inside:avoid}
.rec-point-icon{width:20px;height:20px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0;font-size:11px}
.rec-point-icon.pos{background:var(--success-light);color:var(--success)}
.rec-point-icon.neg{background:var(--danger-light);color:var(--danger)}
.rec-point-icon.neutral{background:var(--surface-2);color:var(--ink-2)}
.qa-list{display:block}
.qa-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px;margin-bottom:12px;page-break-inside:avoid}
.qa-q{font-size:14px;font-weight:600;color:var(--ink);margin-bottom:10px;line-height:1.45}
.qa-a{font-size:13px;color:var(--ink-2);line-height:1.6;padding:12px 14px;background:var(--surface-2);border-radius:8px;border-left:3px solid var(--accent);margin-bottom:8px;white-space:pre-wrap}
.qa-comment{font-size:12px;color:var(--ink-2);line-height:1.5;padding-top:8px;border-top:1px dashed var(--border)}
.report-footer{margin-top:28px;padding-top:14px;border-top:1px solid var(--border);font-size:11px;color:var(--ink-3);display:flex;justify-content:space-between}
.cv-appendix{margin-top:28px;padding-top:20px;border-top:1px solid var(--border);page-break-before:always}
.cv-appendix h2{font-size:16px;margin-bottom:10px}
.cv-pre{white-space:pre-wrap;font-size:11px;line-height:1.5;background:#fff;padding:14px;border:1px solid var(--border);border-radius:8px}
"""


def _e(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _logo_html(*, for_pdf: bool = False) -> str:
    if for_pdf:
        path = asset_path("logo-black")
        if path is not None:
            return f'<img src="{path.resolve().as_uri()}" alt="VOXBULK" />'
    url = email_logo_url()
    if url:
        return f'<img src="{url}" alt="VOXBULK" />'
    data = logo_data_uri(variant="logo-black")
    if data:
        return f'<img src="{data}" alt="VOXBULK" />'
    return "<strong>VOXBULK</strong>"


def _score_table(scores: dict[str, Any]) -> str:
    cells = [
        ("ATS Score", _safe_int(scores.get("ats")), "ats"),
        ("Interview Score", _safe_int(scores.get("interview")), "interview"),
        ("Culture Fit", _safe_int(scores.get("culture_fit")), "culture"),
        ("Overall", _safe_int(scores.get("overall")), "overall"),
    ]
    tds = []
    for label, val, _key in cells:
        tds.append(
            f"""<td><div class="score-card-label">{label}</div>
            <div class="score-card-value">{val}<span>/100</span></div></td>"""
        )
    return f'<table class="score-table"><tr>{"".join(tds)}</tr></table>'


def _criteria_rows(criteria: list[dict[str, Any]]) -> str:
    rows = []
    for c in criteria:
        pct = _safe_int(c.get("score") if c.get("score") is not None else c.get("percent"))
        rows.append(
            f"""<div class="criteria-row">
            <div class="criteria-head">
              <div><div class="criteria-label">{_e(c.get('label'))}</div>
              <div class="criteria-sublabel">{_e(c.get('sublabel'))}</div></div>
              <div class="criteria-score">{pct}%</div>
            </div>
            <div class="progress-wrap"><div class="progress-fill" style="width:{pct}%"></div></div>
            </div>"""
        )
    return "".join(rows)


def _competency_cards(items: list[dict[str, Any]]) -> str:
    cards = []
    for c in items:
        score10 = _safe_int(c.get("score_10") if c.get("score_10") is not None else c.get("score"), 0)
        if score10 > 10:
            score10 = max(1, min(10, round(score10 / 10)))
        score10 = max(0, min(10, score10))
        pct = score10 * 10
        cards.append(
            f"""<div class="competency-card">
            <div class="comp-head">
              <div><div class="comp-name">{_e(c.get('name'))}</div><div class="comp-category">{_e(c.get('category'))}</div></div>
              <div class="comp-score">{_e(c.get('badge'))} {score10}/10</div>
            </div>
            <div class="comp-bar"><div class="progress-fill" style="width:{pct}%;background:#3b6d11"></div></div>
            <div class="comp-note">{_e(c.get('note'))}</div></div>"""
        )
    return "".join(cards)


def _quality_comment(quality: str) -> str:
    q = str(quality or "adequate").strip().lower()
    if q == "strong":
        return "Strong, well-evidenced answer that directly addresses the question."
    if q == "weak":
        return "Answer lacked depth or did not fully address the question — follow up in the next stage."
    return "Adequate response with some useful detail; consider probing further in a human interview."


def _qa_section(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    cards = []
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not question and not answer:
            continue
        quality = str(item.get("quality") or "adequate").strip().lower()
        comment = str(item.get("comment") or item.get("assessor_note") or _quality_comment(quality)).strip()
        cards.append(
            f"""<div class="qa-card">
            <div class="qa-q">Q{i}. {_e(question or "Question")}</div>
            <div class="qa-a">{_e(answer or "No clear answer captured in the transcript.")}</div>
            <div class="qa-comment"><strong>Assessor note ({_e(quality)}):</strong> {_e(comment)}</div>
            </div>"""
        )
    if not cards:
        return ""
    return f"""<div class="section"><div class="section-title">Interview Q&amp;A</div>
    <div class="qa-list">{"".join(cards)}</div></div>"""


def build_candidate_report_html(payload: dict[str, Any], *, cv_text: str | None = None, for_pdf: bool = False) -> str:
    cand = payload.get("candidate") or {}
    scores = payload.get("scores") or {}
    ats = payload.get("ats") or {}
    interview = payload.get("interview") or {}
    logo_html = _logo_html(for_pdf=for_pdf)

    rec_class = "proceed" if interview.get("recommendation") == "Advance" else ""
    points_html = ""
    for p in interview.get("recommendation_points") or []:
        kind = str(p.get("kind") or "neutral")
        icon = "+" if kind == "pos" else "−" if kind == "neg" else "→"
        points_html += f"""<div class="rec-point"><div class="rec-point-icon {kind}">{icon}</div>
        <div class="rec-point-text"><strong>{_e(p.get('title'))}</strong> {_e(p.get('body'))}</div></div>"""

    standout = interview.get("standout_quote") or ""
    skill_gap = interview.get("skill_gap") or ""
    highlight = ""
    if standout:
        highlight = f'<div class="interview-highlight"><div class="highlight-label">Standout moment</div><div>{_e(standout)}</div></div>'
    concern = ""
    if skill_gap:
        concern = f'<div class="concern-box"><div class="concern-label">Identified skill gap</div><div>{_e(skill_gap)}</div></div>'

    cv_block = ""
    if cv_text and cv_text.strip():
        cv_block = f"""<div class="cv-appendix"><h2>CV — {_e(payload.get('cv_filename') or 'attachment')}</h2>
        <pre class="cv-pre">{_e(cv_text[:12000])}</pre></div>"""

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/>
<title>Interview Report — {_e(cand.get('name'))}</title><style>{REPORT_CSS}</style></head><body>
<div class="page">
  <div class="logo-bar">{logo_html}<div style="font-size:11px;color:var(--ink-3)">Confidential</div></div>
  <div class="report-header">
    <div class="report-header-top">
      <div>
        <div class="report-badge">Candidate AI Interview Report</div>
        <div class="report-title">{_e(cand.get('name'))}</div>
        <div class="report-subtitle">{_e(payload.get('role'))} · Applied {_e(cand.get('applied_at'))}</div>
      </div>
      <div class="candidate-meta">
        <div class="candidate-avatar">{_e(cand.get('initials'))}</div>
        <div class="meta-row">Interview: <strong>{_e(cand.get('interview_date'))}</strong></div>
        <div class="meta-row">{_e(payload.get('company_name'))}</div>
      </div>
    </div>
  </div>
  {_score_table(scores)}
  <div class="section"><div class="section-title">ATS score breakdown</div>
    {_criteria_rows(ats.get('criteria') or [])}
  </div>
  <div class="section"><div class="section-title">Interview score breakdown</div>
    {_competency_cards(interview.get('competencies') or [])}
    {highlight}{concern}
  </div>
  {_qa_section(interview.get('key_answers') or [])}
  <div class="section"><div class="section-title">Recommendation</div>
    <div class="rec-banner {rec_class}">
      <div class="rec-verdict">{_e(interview.get('recommendation_verdict'))}</div>
      <div class="rec-desc">{_e(interview.get('recommendation_description'))}</div>
    </div>
    {points_html}
  </div>
  {cv_block}
  <div class="report-footer"><div>VOXBULK</div><div>Generated {_e(payload.get('generated_at'))} · Confidential</div></div>
</div></body></html>"""
