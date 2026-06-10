"""Additional candidate details in interview analysis and reports."""

from app.services.interview_analysis_service import _normalize_analysis
from app.services.interview_report_template import build_candidate_report_html


def test_normalize_additional_candidate_details_dedupes_existing_content():
    raw = {
        "short_summary": "Strong communicator.",
        "score": 72,
        "culture_fit_score": 70,
        "recommendation": "Advance",
        "recommendation_summary": "Good fit.",
        "sentiment": "Enthusiastic",
        "strengths": ["Knows Linux administration"],
        "concerns": [],
        "key_answers": [
            {"question": "Tell me about your experience", "answer": "I know Linux", "quality": "strong"},
        ],
        "competencies": [],
        "standout_quote": "",
        "skill_gap": "",
        "additional_candidate_details": [
            "Knows Linux administration",
            "Has a driving licence",
            "Can work weekends",
        ],
        "completion_quality": "complete",
    }
    out = _normalize_analysis(raw)
    assert "Has a driving licence" in out["additional_candidate_details"]
    assert "Can work weekends" in out["additional_candidate_details"]
    assert "Knows Linux administration" not in out["additional_candidate_details"]


def test_report_renders_additional_candidate_details_section():
    payload = {
        "candidate": {"name": "Alex Candidate", "initials": "AC", "applied_at": "01 Jan 2026", "interview_date": "02 Jan 2026"},
        "role": "Engineer",
        "company_name": "Acme Ltd",
        "campaign_brief": {},
        "scores": {"ats": 70, "interview": 75, "culture_fit": 72, "overall": 73},
        "ats": {"criteria": [], "keywords_found": [], "keywords_missing": []},
        "interview": {
            "competencies": [],
            "key_answers": [],
            "standout_quote": "",
            "skill_gap": "",
            "recommendation": "Advance",
            "recommendation_verdict": "Proceed to Final Round",
            "recommendation_description": "Strong fit.",
            "recommendation_points": [],
            "additional_candidate_details": [
                "Speaks Arabic and English",
                "Has own car for site visits",
            ],
        },
        "generated_at": "03 Jan 2026",
    }
    html = build_candidate_report_html(payload, for_pdf=False)
    assert "Additional comments" in html
    assert "Additional Candidate Details" not in html
    rec_idx = html.index("Recommendation")
    comments_idx = html.index("Additional comments")
    assert comments_idx > rec_idx
    assert "Speaks Arabic and English" in html
    assert "Has own car for site visits" in html
