"""Render per-candidate AI interview report HTML (matches interview_report.html design)."""

from __future__ import annotations

import html
from typing import Any

from app.services.brand_assets import logo_data_uri

REPORT_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#1a1a18;--ink-2:#4a4a46;--ink-3:#888780;--surface:#faf9f6;--surface-2:#f1efe8;--surface-3:#e5e3d8;--accent:#185fa5;--accent-light:#e6f1fb;--success:#3b6d11;--success-light:#eaf3de;--warn:#854f0b;--warn-light:#faeeda;--danger:#a32d2d;--danger-light:#fcebeb;--border:rgba(26,26,24,.12);--radius:10px}
body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--surface);color:var(--ink);font-size:15px;line-height:1.65}
.page{max-width:1200px;margin:0 auto;padding:48px 40px 80px}
.logo-bar{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;padding-bottom:16px;border-bottom:1px solid var(--border)}
.logo-bar img{height:32px;width:auto}
.report-header{display:grid;grid-template-columns:1fr auto;gap:24px;padding-bottom:32px;border-bottom:1px solid var(--border);margin-bottom:40px}
.report-badge{font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);margin-bottom:10px}
.report-title{font-size:34px;line-height:1.15;margin-bottom:6px;font-weight:700}
.report-subtitle{font-size:14px;color:var(--ink-2)}
.candidate-meta{text-align:right}
.candidate-avatar{width:52px;height:52px;border-radius:50%;background:var(--accent-light);color:var(--accent);font-weight:500;font-size:16px;display:flex;align-items:center;justify-content:center;margin-left:auto;margin-bottom:10px}
.meta-row{font-size:13px;color:var(--ink-2);margin-bottom:3px}
.score-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:48px}
.score-card{background:var(--surface-2);border-radius:var(--radius);padding:18px 16px;border:.5px solid var(--border);position:relative;overflow:hidden}
.score-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.score-card.ats::before{background:#378add}.score-card.interview::before{background:#1d9e75}
.score-card.culture::before{background:#ba7517}.score-card.overall::before{background:#533ab7}
.score-card-label{font-size:11px;font-weight:500;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-3);margin-bottom:8px}
.score-card-value{font-size:36px;line-height:1;margin-bottom:6px;font-weight:700}
.score-card-sub{font-size:12px;color:var(--ink-3)}
.section{margin-bottom:48px}
.section-header{display:flex;align-items:center;gap:12px;margin-bottom:24px}
.section-title{font-size:22px;font-weight:700}
.criteria-row{display:grid;grid-template-columns:200px 1fr 48px;align-items:center;gap:16px;padding:14px 16px;background:#fff;border-radius:var(--radius);border:.5px solid var(--border);margin-bottom:14px}
.criteria-label{font-size:13px;font-weight:500}.criteria-sublabel{font-size:11px;color:var(--ink-3)}
.progress-wrap{height:6px;background:var(--surface-3);border-radius:99px;overflow:hidden}
.progress-fill{height:100%;border-radius:99px;background:#378add}
.competency-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.competency-card{background:#fff;border:.5px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:14px}
.comp-name{font-size:13px;font-weight:500}.comp-category{font-size:11px;color:var(--ink-3)}
.comp-score-badge{font-size:11px;font-weight:500;padding:3px 9px;border-radius:99px;background:var(--accent-light);color:var(--accent)}
.comp-bar{height:4px;background:var(--surface-3);border-radius:99px;margin:10px 0;overflow:hidden}
.comp-note{font-size:12px;color:var(--ink-2);padding-top:8px;border-top:.5px solid var(--border)}
.tags{display:flex;flex-wrap:wrap;gap:8px}
.tag{font-size:12px;padding:4px 10px;border-radius:99px;border:.5px solid}
.tag.found{background:var(--success-light);color:var(--success);border-color:#c0dd97}
.tag.missing{background:var(--danger-light);color:var(--danger);border-color:#f7c1c1}
.interview-highlight,.concern-box{padding:18px 16px;border-radius:var(--radius);margin-top:16px;border:.5px solid var(--border);background:#fff}
.highlight-label,.concern-label{font-size:11px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);margin-bottom:8px}
.rec-banner{display:flex;gap:16px;padding:20px;border-radius:var(--radius);margin-bottom:20px;border:.5px solid var(--border);background:#fff}
.rec-banner.proceed{border-color:#c0dd97;background:var(--success-light)}
.rec-verdict{font-size:18px;font-weight:700;margin-bottom:6px}
.rec-point{display:flex;gap:12px;margin-bottom:14px;font-size:13px}
.rec-point-icon{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0}
.rec-point-icon.pos{background:var(--success-light);color:var(--success)}
.rec-point-icon.neg{background:var(--danger-light);color:var(--danger)}
.rec-point-icon.neutral{background:var(--surface-2);color:var(--ink-2)}
.report-footer{margin-top:48px;padding-top:24px;border-top:1px solid var(--border);font-size:12px;color:var(--ink-3);display:flex;justify-content:space-between}
.qa-list{display:flex;flex-direction:column;gap:16px}
.qa-card{background:#fff;border:.5px solid var(--border);border-radius:var(--radius);padding:20px 22px}
.qa-q{font-size:15px;font-weight:600;color:var(--ink);margin-bottom:12px;line-height:1.45}
.qa-a{font-size:14px;color:var(--ink-2);line-height:1.65;padding:14px 16px;background:var(--surface-2);border-radius:8px;border-left:3px solid var(--accent);margin-bottom:10px;white-space:pre-wrap}
.qa-comment{font-size:13px;color:var(--ink-2);padding-top:10px;border-top:.5px dashed var(--border)}
.qa-badge{display:inline-block;font-size:11px;font-weight:600;padding:3px 10px;border-radius:99px;margin-bottom:8px;text-transform:capitalize}
.qa-badge.strong{background:var(--success-light);color:var(--success)}
.qa-badge.adequate{background:var(--warn-light);color:var(--warn)}
.qa-badge.weak{background:var(--danger-light);color:var(--danger)}
.cv-appendix{margin-top:40px;padding-top:24px;border-top:1px solid var(--border);page-break-before:always}
@media print{body{background:#fff}.page{padding:20px}}
"""


def _e(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _score_strip(scores: dict[str, Any]) -> str:
    return f"""
    <div class="score-strip">
      <div class="score-card ats"><div class="score-card-label">ATS Score</div>
        <div class="score-card-value">{int(scores.get('ats') or 0)}<span style="font-size:18px;opacity:.5">/100</span></div></div>
      <div class="score-card interview"><div class="score-card-label">Interview Score</div>
        <div class="score-card-value">{int(scores.get('interview') or 0)}<span style="font-size:18px;opacity:.5">/100</span></div></div>
      <div class="score-card culture"><div class="score-card-label">Culture Fit</div>
        <div class="score-card-value">{int(scores.get('culture_fit') or 0)}<span style="font-size:18px;opacity:.5">/100</span></div></div>
      <div class="score-card overall"><div class="score-card-label">Overall</div>
        <div class="score-card-value">{int(scores.get('overall') or 0)}<span style="font-size:18px;opacity:.5">/100</span></div></div>
    </div>"""


def _criteria_rows(criteria: list[dict[str, Any]]) -> str:
    rows = []
    for c in criteria:
        pct = int(c.get("score") or c.get("percent") or 0)
        rows.append(
            f"""<div class="criteria-row"><div><div class="criteria-label">{_e(c.get('label'))}</div>
            <div class="criteria-sublabel">{_e(c.get('sublabel'))}</div></div>
            <div class="progress-wrap"><div class="progress-fill" style="width:{pct}%"></div></div>
            <div class="criteria-score">{pct}%</div></div>"""
        )
    return "".join(rows)


def _competency_cards(items: list[dict[str, Any]]) -> str:
    cards = []
    for c in items:
        score10 = int(c.get("score_10") or 0)
        pct = score10 * 10
        cards.append(
            f"""<div class="competency-card"><div style="display:flex;justify-content:space-between;margin-bottom:8px">
            <div><div class="comp-name">{_e(c.get('name'))}</div><div class="comp-category">{_e(c.get('category'))}</div></div>
            <span class="comp-score-badge">{_e(c.get('badge'))} {score10}/10</span></div>
            <div class="comp-bar"><div class="progress-fill" style="width:{pct}%;background:#3b6d11"></div></div>
            <div class="comp-note">{_e(c.get('note'))}</div></div>"""
        )
    return f'<div class="competency-grid">{"".join(cards)}</div>'


def _tags(words: list[Any], css: str) -> str:
    return "".join(f'<span class="tag {css}">{_e(w)}</span>' for w in words if str(w).strip())


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
        if quality not in {"strong", "adequate", "weak"}:
            quality = "adequate"
        comment = str(item.get("comment") or item.get("assessor_note") or _quality_comment(quality)).strip()
        cards.append(
            f"""<div class="qa-card">
            <div class="qa-badge {quality}">{_e(quality)}</div>
            <div class="qa-q">Q{i}. {_e(question or "Question")}</div>
            <div class="qa-a">{_e(answer or "No clear answer captured in the transcript.")}</div>
            <div class="qa-comment"><strong>Assessor note:</strong> {_e(comment)}</div>
            </div>"""
        )
    if not cards:
        return ""
    return f"""<div class="section"><div class="section-header"><div class="section-title">Interview Q&amp;A</div></div>
    <div class="qa-list">{"".join(cards)}</div></div>"""


def build_candidate_report_html(payload: dict[str, Any], *, cv_text: str | None = None) -> str:
    cand = payload.get("candidate") or {}
    scores = payload.get("scores") or {}
    ats = payload.get("ats") or {}
    interview = payload.get("interview") or {}
    logo = logo_data_uri(variant="logo-black") or ""
    logo_html = f'<img src="{logo}" alt="VOXBULK" />' if logo else "<strong>VOXBULK</strong>"

    rec_class = "proceed" if interview.get("recommendation") == "Advance" else ""
    points_html = ""
    for p in interview.get("recommendation_points") or []:
        kind = str(p.get("kind") or "neutral")
        points_html += f"""<div class="rec-point"><div class="rec-point-icon {kind}">{'+' if kind=='pos' else '−' if kind=='neg' else '→'}</div>
        <div class="rec-point-text"><strong>{_e(p.get('title'))}</strong> {_e(p.get('body'))}</div></div>"""

    standout = interview.get("standout_quote") or ""
    skill_gap = interview.get("skill_gap") or ""
    highlight = ""
    if standout:
        highlight = f'<div class="interview-highlight"><div class="highlight-label">Standout Moment</div><div>{_e(standout)}</div></div>'
    concern = ""
    if skill_gap:
        concern = f'<div class="concern-box"><div class="concern-label">Identified Skill Gap</div><div>{_e(skill_gap)}</div></div>'

    cv_block = ""
    if cv_text and cv_text.strip():
        cv_block = f"""<div class="cv-appendix"><h2 style="margin-bottom:12px">CV — {_e(payload.get('cv_filename') or 'attachment')}</h2>
        <pre style="white-space:pre-wrap;font-size:12px;line-height:1.5;background:#fff;padding:16px;border:1px solid var(--border);border-radius:8px">{_e(cv_text[:12000])}</pre></div>"""

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/>
<title>Interview Report — {_e(cand.get('name'))}</title><style>{REPORT_CSS}</style></head><body>
<div class="page">
  <div class="logo-bar">{logo_html}<div style="font-size:12px;color:var(--ink-3)">Confidential</div></div>
  <div class="report-header">
    <div><div class="report-badge">Candidate AI Interview Report</div>
      <div class="report-title">{_e(cand.get('name'))}</div>
      <div class="report-subtitle">{_e(payload.get('role'))} · Applied {_e(cand.get('applied_at'))}</div></div>
    <div class="candidate-meta"><div class="candidate-avatar">{_e(cand.get('initials'))}</div>
      <div class="meta-row">Interview: <strong>{_e(cand.get('interview_date'))}</strong></div>
      <div class="meta-row">{_e(payload.get('company_name'))}</div></div>
  </div>
  {_score_strip(scores)}
  <div class="section"><div class="section-header"><div class="section-title">ATS Score Breakdown</div></div>
    {_criteria_rows(ats.get('criteria') or [])}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px">
      <div><div class="highlight-label">Keywords Found</div><div class="tags">{_tags(ats.get('keywords_found') or [], 'found')}</div></div>
      <div><div class="highlight-label">Missing Keywords</div><div class="tags">{_tags(ats.get('keywords_missing') or [], 'missing')}</div></div>
    </div>
  </div>
  <div class="section"><div class="section-header"><div class="section-title">Interview Score Breakdown</div></div>
    {_competency_cards(interview.get('competencies') or [])}
    {highlight}{concern}
  </div>
  {_qa_section(interview.get('key_answers') or [])}
  <div class="section"><div class="section-header"><div class="section-title">Recommendation</div></div>
    <div class="rec-banner {rec_class}"><div>
      <div class="rec-verdict">{_e(interview.get('recommendation_verdict'))}</div>
      <div style="color:var(--ink-2);font-size:14px;margin-top:6px">{_e(interview.get('recommendation_description'))}</div>
    </div></div>
    {points_html}
  </div>
  {cv_block}
  <div class="report-footer"><div>VOXBULK</div><div>Generated {_e(payload.get('generated_at'))} · Confidential</div></div>
</div></body></html>"""
