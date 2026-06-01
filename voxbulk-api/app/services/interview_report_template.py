"""Render per-candidate AI interview report HTML."""

from __future__ import annotations

import html
from typing import Any

from app.services.brand_assets import asset_path, email_logo_url, logo_data_uri

# PDF layout — compact A4 (unchanged; user confirmed PDF looks perfect)
REPORT_CSS_PDF = """
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

# Browser layout — matches interview_report.html (centered card, DM fonts)
REPORT_CSS_SCREEN = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#1a1a18;--ink-2:#4a4a46;--ink-3:#888780;--surface:#faf9f6;--surface-2:#f1efe8;--surface-3:#e5e3d8;--accent:#185fa5;--accent-light:#e6f1fb;--success:#3b6d11;--success-light:#eaf3de;--warn:#854f0b;--warn-light:#faeeda;--danger:#a32d2d;--danger-light:#fcebeb;--border:rgba(26,26,24,.12);--radius:10px;--radius-lg:16px}
body{font-family:'DM Sans',system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--surface);color:var(--ink);font-size:15px;line-height:1.65;padding:0}
.page{max-width:860px;margin:0 auto;padding:48px 40px 80px}
.report-header{display:grid;grid-template-columns:1fr auto;align-items:start;gap:24px;padding-bottom:32px;border-bottom:1px solid var(--border);margin-bottom:40px}
.report-badge{font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);margin-bottom:10px}
.report-title{font-family:'DM Serif Display',Georgia,serif;font-size:34px;line-height:1.15;color:var(--ink);margin-bottom:6px}
.report-subtitle{font-size:14px;color:var(--ink-2)}
.candidate-meta{text-align:right}
.candidate-avatar{width:52px;height:52px;border-radius:50%;background:var(--accent-light);color:var(--accent);font-weight:500;font-size:16px;display:flex;align-items:center;justify-content:center;margin-left:auto;margin-bottom:10px}
.meta-row{font-size:13px;color:var(--ink-2);margin-bottom:3px}
.meta-row strong{color:var(--ink);font-weight:500}
.score-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:48px}
.score-card{background:var(--surface-2);border-radius:var(--radius);padding:18px 16px;border:.5px solid var(--border);position:relative;overflow:hidden}
.score-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.score-card.ats::before{background:#378add}.score-card.interview::before{background:#1d9e75}
.score-card.culture::before{background:#ba7517}.score-card.overall::before{background:#533ab7}
.score-card-label{font-size:11px;font-weight:500;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-3);margin-bottom:8px}
.score-card-value{font-family:'DM Serif Display',Georgia,serif;font-size:36px;line-height:1;margin-bottom:6px}
.score-card.ats .score-card-value{color:#185fa5}.score-card.interview .score-card-value{color:#0f6e56}
.score-card.culture .score-card-value{color:#854f0b}.score-card.overall .score-card-value{color:#3c3489}
.score-card-sub{font-size:12px;color:var(--ink-3)}
.section{margin-bottom:48px}
.section-header{display:flex;align-items:center;gap:12px;margin-bottom:24px}
.section-icon{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.section-icon.blue{background:var(--accent-light);color:var(--accent)}
.section-icon.green{background:var(--success-light);color:var(--success)}
.section-icon.amber{background:var(--warn-light);color:var(--warn)}
.section-icon.purple{background:#eeedfe;color:#3c3489}
.section-title{font-family:'DM Serif Display',Georgia,serif;font-size:22px;color:var(--ink)}
.criteria-list{display:flex;flex-direction:column;gap:14px}
.criteria-row{display:grid;grid-template-columns:200px 1fr 48px;align-items:center;gap:16px;padding:14px 16px;background:#fff;border-radius:var(--radius);border:.5px solid var(--border)}
.criteria-label{font-size:13px;font-weight:500;color:var(--ink)}
.criteria-sublabel{font-size:11px;color:var(--ink-3);margin-top:2px}
.progress-wrap{height:6px;background:var(--surface-3);border-radius:99px;overflow:hidden}
.progress-fill{height:100%;border-radius:99px}
.fill-blue{background:#378add}.fill-green{background:#3b6d11}.fill-amber{background:#ef9f27}.fill-red{background:#e24b4a}
.criteria-score{font-size:14px;font-weight:500;text-align:right}
.keyword-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.keyword-section{padding:18px 16px;background:#fff;border-radius:var(--radius);border:.5px solid var(--border)}
.keyword-section-title{font-size:12px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);margin-bottom:12px}
.tags{display:flex;flex-wrap:wrap;gap:8px}
.tag{font-size:12px;padding:4px 10px;border-radius:99px;border:.5px solid}
.tag.found{background:var(--success-light);color:var(--success);border-color:#c0dd97}
.tag.missing{background:var(--danger-light);color:var(--danger);border-color:#f7c1c1}
.tag.partial{background:var(--warn-light);color:var(--warn);border-color:#fac775}
.competency-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.competency-card{background:#fff;border:.5px solid var(--border);border-radius:var(--radius);padding:16px}
.comp-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:10px}
.comp-name{font-size:13px;font-weight:500;color:var(--ink)}
.comp-category{font-size:11px;color:var(--ink-3);margin-top:2px}
.comp-score-badge{font-size:11px;font-weight:500;padding:3px 9px;border-radius:99px}
.badge-strong{background:var(--success-light);color:var(--success)}
.badge-good{background:var(--accent-light);color:var(--accent)}
.badge-average{background:var(--warn-light);color:var(--warn)}
.badge-weak{background:var(--danger-light);color:var(--danger)}
.comp-bar{height:4px;background:var(--surface-3);border-radius:99px;overflow:hidden;margin-bottom:10px}
.comp-note{font-size:12px;color:var(--ink-2);line-height:1.5;padding-top:8px;border-top:.5px solid var(--border)}
.interview-highlight{margin-top:20px;padding:18px 20px 18px 24px;background:#fff;border-radius:var(--radius);border:.5px solid var(--border);border-left:3px solid #1d9e75}
.highlight-label{font-size:11px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:#0f6e56;margin-bottom:8px}
.highlight-text{font-family:'DM Serif Display',Georgia,serif;font-style:italic;font-size:16px;color:var(--ink);line-height:1.55}
.concern-box{margin-top:14px;padding:14px 16px 14px 20px;background:var(--danger-light);border-radius:var(--radius);border-left:3px solid #e24b4a}
.concern-label{font-size:11px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:var(--danger);margin-bottom:6px}
.concern-text{font-size:13px;color:#501313;line-height:1.55}
.rec-banner{padding:28px;border-radius:var(--radius-lg);border:.5px solid var(--border);margin-bottom:28px;display:flex;align-items:center;gap:24px}
.rec-banner.proceed{background:var(--success-light);border-color:#c0dd97}
.rec-banner.hold{background:var(--warn-light);border-color:#fac775}
.rec-banner.reject{background:var(--danger-light);border-color:#f7c1c1}
.rec-icon{font-size:36px;flex-shrink:0}
.rec-verdict{font-family:'DM Serif Display',Georgia,serif;font-size:26px;line-height:1.1;margin-bottom:5px}
.rec-banner.proceed .rec-verdict{color:var(--success)}
.rec-banner.hold .rec-verdict{color:var(--warn)}
.rec-banner.reject .rec-verdict{color:var(--danger)}
.rec-description{font-size:14px;color:var(--ink-2);line-height:1.6}
.rec-points{display:flex;flex-direction:column;gap:10px;margin-bottom:24px}
.rec-point{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;background:#fff;border-radius:var(--radius);border:.5px solid var(--border)}
.rec-point-icon{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:500;flex-shrink:0;margin-top:1px}
.rec-point-icon.pos{background:var(--success-light);color:var(--success)}
.rec-point-icon.neg{background:var(--danger-light);color:var(--danger)}
.rec-point-icon.neutral{background:var(--accent-light);color:var(--accent)}
.rec-point-text{font-size:13px;color:var(--ink);line-height:1.55}
.rec-point-text strong{display:block;font-weight:500;margin-bottom:2px}
.qa-list{display:flex;flex-direction:column;gap:14px}
.qa-card{background:#fff;border:.5px solid var(--border);border-radius:var(--radius);padding:18px 20px}
.qa-q{font-size:14px;font-weight:500;color:var(--ink);margin-bottom:10px;line-height:1.45}
.qa-a{font-size:13px;color:var(--ink-2);line-height:1.6;padding:12px 14px;background:var(--surface-2);border-radius:8px;border-left:3px solid var(--accent);margin-bottom:8px;white-space:pre-wrap}
.qa-comment{font-size:12px;color:var(--ink-2);line-height:1.5;padding-top:8px;border-top:.5px dashed var(--border)}
.divider{height:.5px;background:var(--border);margin:40px 0}
.report-footer{display:flex;align-items:center;justify-content:space-between;padding-top:24px;border-top:.5px solid var(--border);font-size:12px;color:var(--ink-3)}
.footer-logo img{height:24px;width:auto;max-width:140px;display:block}
.cv-appendix{margin-top:40px;padding-top:24px;border-top:.5px solid var(--border)}
.cv-appendix h2{font-family:'DM Serif Display',Georgia,serif;font-size:20px;margin-bottom:12px}
.cv-pre{white-space:pre-wrap;font-size:12px;line-height:1.55;background:#fff;padding:16px;border:.5px solid var(--border);border-radius:var(--radius)}
@media (max-width:720px){
  .page{padding:24px 20px 48px}
  .report-header{grid-template-columns:1fr}
  .candidate-meta{text-align:left}
  .candidate-avatar{margin-left:0}
  .score-strip{grid-template-columns:1fr 1fr}
  .criteria-row{grid-template-columns:1fr;gap:10px}
  .competency-grid,.keyword-grid{grid-template-columns:1fr}
  .rec-banner{flex-direction:column;align-items:flex-start}
}
@media print{body{background:#fff}.page{padding:20px;max-width:100%}}
"""

FONT_LINK = (
    '<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1'
    "&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300"
    '&display=swap" rel="stylesheet">'
)

ICON_ATS = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
    '<line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>'
)
ICON_INTERVIEW = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>'
    '<circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
)
ICON_QA = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
)
ICON_REC = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/>'
    '<path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>'
)


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


def _footer_logo(*, for_pdf: bool = False) -> str:
    logo = _logo_html(for_pdf=for_pdf)
    if logo.startswith("<img"):
        return f'<div class="footer-logo">{logo}</div>'
    return f'<div class="footer-logo">{_e("VOXBULK")}</div>'


def _score_sub(key: str, val: int) -> str:
    if key == "ats":
        return "Above threshold (70)" if val >= 70 else "Below threshold (70)"
    if key == "interview":
        if val >= 80:
            return "Strong performance"
        if val >= 65:
            return "Solid performance"
        return "Needs review"
    if key == "culture":
        if val >= 75:
            return "Strong alignment"
        if val >= 60:
            return "Moderate alignment"
        return "Alignment concerns"
    if val >= 75:
        return "Recommended to proceed"
    if val >= 60:
        return "Review recommended"
    return "Below hiring bar"


def _fill_class(pct: int) -> str:
    if pct >= 85:
        return "fill-green"
    if pct >= 70:
        return "fill-blue"
    if pct >= 55:
        return "fill-amber"
    return "fill-red"


def _score_color(pct: int) -> str:
    if pct >= 85:
        return "#0f6e56"
    if pct >= 70:
        return "#185fa5"
    if pct >= 55:
        return "#854f0b"
    return "#a32d2d"


def _badge_class(badge: str) -> str:
    b = str(badge or "").lower()
    if "strong" in b:
        return "badge-strong"
    if "good" in b:
        return "badge-good"
    if "average" in b or "moderate" in b:
        return "badge-average"
    return "badge-weak"


def _comp_fill(score10: int) -> str:
    if score10 >= 8:
        return "fill-green"
    if score10 >= 6:
        return "fill-blue"
    return "fill-amber"


def _rec_class(recommendation: str) -> str:
    rec = str(recommendation or "").strip()
    if rec == "Advance":
        return "proceed"
    if rec == "Decline":
        return "reject"
    return "hold"


def _rec_icon(recommendation: str) -> str:
    rec = str(recommendation or "").strip()
    if rec == "Advance":
        return "✓"
    if rec == "Decline":
        return "✗"
    return "⏳"  # Hourglass for "Hold"


def _quality_comment(quality: str) -> str:
    q = str(quality or "adequate").strip().lower()
    if q == "strong":
        return "Strong, well-evidenced answer that directly addresses the question."
    if q == "weak":
        return "Answer lacked depth or did not fully address the question — follow up in the next stage."
    return "Adequate response with some useful detail; consider probing further in a human interview."


def _section_header(title: str, icon: str, color: str) -> str:
    return f"""<div class="section-header">
      <div class="section-icon {color}">{icon}</div>
      <div class="section-title">{title}</div>
    </div>"""


# --- PDF builders (compact) ---


def _pdf_score_table(scores: dict[str, Any]) -> str:
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


def _pdf_criteria_rows(criteria: list[dict[str, Any]]) -> str:
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


def _pdf_competency_cards(items: list[dict[str, Any]]) -> str:
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


def _pdf_qa_section(items: list[dict[str, Any]]) -> str:
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


def _build_pdf_html(payload: dict[str, Any], *, cv_text: str | None = None) -> str:
    cand = payload.get("candidate") or {}
    scores = payload.get("scores") or {}
    ats = payload.get("ats") or {}
    interview = payload.get("interview") or {}
    logo_html = _logo_html(for_pdf=True)

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
<title>Interview Report — {_e(cand.get('name'))}</title><style>{REPORT_CSS_PDF}</style></head><body>
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
  {_pdf_score_table(scores)}
  <div class="section"><div class="section-title">ATS score breakdown</div>
    {_pdf_criteria_rows(ats.get('criteria') or [])}
  </div>
  <div class="section"><div class="section-title">Interview score breakdown</div>
    {_pdf_competency_cards(interview.get('competencies') or [])}
    {highlight}{concern}
  </div>
  {_pdf_qa_section(interview.get('key_answers') or [])}
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


# --- Screen builders (original design) ---


def _screen_score_strip(scores: dict[str, Any]) -> str:
    cards = [
        ("ats", "ATS Score", _safe_int(scores.get("ats"))),
        ("interview", "Interview Score", _safe_int(scores.get("interview"))),
        ("culture", "Culture Fit", _safe_int(scores.get("culture_fit"))),
        ("overall", "Overall", _safe_int(scores.get("overall"))),
    ]
    parts = []
    for key, label, val in cards:
        parts.append(
            f"""<div class="score-card {key}">
            <div class="score-card-label">{label}</div>
            <div class="score-card-value">{val}<span style="font-size:18px;opacity:0.5">/100</span></div>
            <div class="score-card-sub">{_e(_score_sub(key, val))}</div>
            </div>"""
        )
    return f'<div class="score-strip">{"".join(parts)}</div>'


def _screen_criteria_rows(criteria: list[dict[str, Any]]) -> str:
    rows = []
    for c in criteria:
        pct = _safe_int(c.get("score") if c.get("score") is not None else c.get("percent"))
        fill = _fill_class(pct)
        color = _score_color(pct)
        rows.append(
            f"""<div class="criteria-row">
            <div>
              <div class="criteria-label">{_e(c.get('label'))}</div>
              <div class="criteria-sublabel">{_e(c.get('sublabel'))}</div>
            </div>
            <div class="progress-wrap"><div class="progress-fill {fill}" style="width:{pct}%"></div></div>
            <div class="criteria-score" style="color:{color}">{pct}%</div>
            </div>"""
        )
    return f'<div class="criteria-list">{"".join(rows)}</div>'


def _screen_keywords(ats: dict[str, Any]) -> str:
    found = [str(x).strip() for x in (ats.get("keywords_found") or []) if str(x).strip()]
    missing = [str(x).strip() for x in (ats.get("keywords_missing") or []) if str(x).strip()]
    if not found and not missing:
        return ""
    found_tags = "".join(f'<span class="tag found">{_e(k)}</span>' for k in found[:12])
    missing_tags = "".join(f'<span class="tag missing">{_e(k)}</span>' for k in missing[:12])
    blocks = []
    if found_tags:
        blocks.append(
            f"""<div class="keyword-section">
            <div class="keyword-section-title">Keywords Found</div>
            <div class="tags">{found_tags}</div></div>"""
        )
    if missing_tags:
        blocks.append(
            f"""<div class="keyword-section">
            <div class="keyword-section-title">Missing Keywords</div>
            <div class="tags">{missing_tags}</div></div>"""
        )
    cols = "1fr 1fr" if len(blocks) == 2 else "1fr"
    return f'<div class="keyword-grid" style="grid-template-columns:{cols}">{"".join(blocks)}</div>'


def _screen_competency_cards(items: list[dict[str, Any]]) -> str:
    cards = []
    for c in items:
        score10 = _safe_int(c.get("score_10") if c.get("score_10") is not None else c.get("score"), 0)
        if score10 > 10:
            score10 = max(1, min(10, round(score10 / 10)))
        score10 = max(0, min(10, score10))
        pct = score10 * 10
        badge = str(c.get("badge") or "Average")
        cards.append(
            f"""<div class="competency-card">
            <div class="comp-header">
              <div><div class="comp-name">{_e(c.get('name'))}</div><div class="comp-category">{_e(c.get('category'))}</div></div>
              <span class="comp-score-badge {_badge_class(badge)}">{score10}/10</span>
            </div>
            <div class="comp-bar"><div class="progress-fill {_comp_fill(score10)}" style="width:{pct}%"></div></div>
            <div class="comp-note">{_e(c.get('note'))}</div></div>"""
        )
    return f'<div class="competency-grid">{"".join(cards)}</div>'


def _screen_qa_section(items: list[dict[str, Any]]) -> str:
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
    return f"""<div class="section">
      {_section_header("Interview Q&amp;A", ICON_QA, "amber")}
      <div class="qa-list">{"".join(cards)}</div>
    </div>"""


def _screen_rec_points(interview: dict[str, Any]) -> str:
    parts = []
    for p in interview.get("recommendation_points") or []:
        kind = str(p.get("kind") or "neutral")
        icon = "+" if kind == "pos" else "−" if kind == "neg" else "→"
        parts.append(
            f"""<div class="rec-point">
            <div class="rec-point-icon {kind}">{icon}</div>
            <div class="rec-point-text"><strong>{_e(p.get('title'))}</strong>{_e(p.get('body'))}</div>
            </div>"""
        )
    if not parts:
        return ""
    return f'<div class="rec-points">{"".join(parts)}</div>'


def _build_screen_html(payload: dict[str, Any], *, cv_text: str | None = None) -> str:
    cand = payload.get("candidate") or {}
    scores = payload.get("scores") or {}
    ats = payload.get("ats") or {}
    interview = payload.get("interview") or {}

    rec_class = _rec_class(str(interview.get("recommendation") or ""))
    rec_icon = _rec_icon(str(interview.get("recommendation") or ""))

    standout = interview.get("standout_quote") or ""
    skill_gap = interview.get("skill_gap") or ""
    highlight = ""
    if standout:
        highlight = f"""<div class="interview-highlight">
          <div class="highlight-label">Standout Moment</div>
          <div class="highlight-text">&ldquo;{_e(standout)}&rdquo;</div>
        </div>"""
    concern = ""
    if skill_gap:
        concern = f"""<div class="concern-box">
          <div class="concern-label">Identified Skill Gap</div>
          <div class="concern-text">{_e(skill_gap)}</div>
        </div>"""

    cv_block = ""
    if cv_text and cv_text.strip():
        cv_block = f"""<div class="divider"></div>
        <div class="cv-appendix"><h2>CV — {_e(payload.get('cv_filename') or 'attachment')}</h2>
        <pre class="cv-pre">{_e(cv_text[:12000])}</pre></div>"""

    qa_block = _screen_qa_section(interview.get("key_answers") or [])
    qa_divider = '<div class="divider"></div>' if qa_block else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Interview Report — {_e(cand.get('name'))}</title>
{FONT_LINK}
<style>{REPORT_CSS_SCREEN}</style>
</head>
<body>
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-badge">Candidate AI Interview Report</div>
      <div class="report-title">{_e(cand.get('name'))}</div>
      <div class="report-subtitle">{_e(payload.get('role'))} · Applied {_e(cand.get('applied_at'))}</div>
    </div>
    <div class="candidate-meta">
      <div class="candidate-avatar">{_e(cand.get('initials'))}</div>
      <div class="meta-row">Interview Date: <strong>{_e(cand.get('interview_date'))}</strong></div>
      <div class="meta-row">{_e(payload.get('company_name'))}</div>
    </div>
  </div>

  {_screen_score_strip(scores)}

  <div class="section">
    {_section_header("ATS Score Breakdown", ICON_ATS, "blue")}
    {_screen_criteria_rows(ats.get("criteria") or [])}
    {_screen_keywords(ats)}
  </div>

  <div class="divider"></div>

  <div class="section">
    {_section_header("Interview Score Breakdown", ICON_INTERVIEW, "green")}
    {_screen_competency_cards(interview.get("competencies") or [])}
    {highlight}{concern}
  </div>

  {qa_divider}{qa_block}

  <div class="divider"></div>

  <div class="section">
    {_section_header("Recommendation", ICON_REC, "purple")}
    <div class="rec-banner {rec_class}">
      <div class="rec-icon">{rec_icon}</div>
      <div>
        <div class="rec-verdict">{_e(interview.get('recommendation_verdict'))}</div>
        <div class="rec-description">{_e(interview.get('recommendation_description'))}</div>
      </div>
    </div>
    {_screen_rec_points(interview)}
  </div>

  {cv_block}

  <div class="report-footer">
    {_footer_logo()}
    <div>Generated {_e(payload.get('generated_at'))} · Confidential · Internal use only</div>
  </div>
</div>
</body>
</html>"""


def build_candidate_report_html(payload: dict[str, Any], *, cv_text: str | None = None, for_pdf: bool = False) -> str:
    if for_pdf:
        return _build_pdf_html(payload, cv_text=cv_text)
    return _build_screen_html(payload, cv_text=cv_text)
