import json

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.email_template import EmailTemplate
from app.models.service_order import ServiceOrderRecipient
from app.services.email_template_service import EmailTemplateService
from app.services.interview_booking_service import (
    BOOKING_LOCKED_MESSAGE,
    BOOKING_OPTED_OUT_MESSAGE,
    interview_booking_locked,
)
from app.services.interview_dialect_packs import (
    interview_call_workflow_for_dialect,
    interview_opening_template_for_dialect,
)
from app.services.interview_early_exit_service import classify_interview_session_outcome
from app.services.interview_session_outcome_email_service import (
    TEMPLATE_OPTED_OUT,
    TEMPLATE_RESCHEDULE,
    TEMPLATE_THANK_YOU,
)
from app.services.voice_agent_runtime import (
    InterviewAgentLanguageMismatch,
    assert_interview_agent_language_match,
)

report = {"ok": True, "checks": []}


def add(name, passed, detail=""):
    report["checks"].append({"name": name, "pass": bool(passed), "detail": detail})
    if not passed:
        report["ok"] = False


en = interview_call_workflow_for_dialect("GB")
ar = interview_call_workflow_for_dialect("EG")
add("EN workflow recording disclosure", "recorded for quality purposes" in en)
add("EN workflow not-free/reschedule", "not free" in en.lower() or "asks to reschedule" in en.lower())
add("EN workflow hangup after goodbye", "hangup" in en.lower() or "end_call" in en.lower())
add("EN workflow add-anything", "anything you'd like to add" in en)
add("EN opening", "Hello" in interview_opening_template_for_dialect("GB"))
add("AR workflow recording disclosure", "مسجّلة لأغراض الجودة" in ar)
add("AR workflow reschedule/not free", "إعادة جدولة" in ar or "مش فاضي" in ar)
add("AR workflow hangup", "hangup" in ar.lower() or "end_call" in ar.lower() or "أنهِ المكالمة" in ar)
add("AR workflow add-anything", "حابب تضيف" in ar)
ar_open = interview_opening_template_for_dialect("EG")
add("AR opening", "مرحباً" in ar_open or "مرحبا" in ar_open)

cases = [
    ("EN not free -> reschedule", 60, "I'm not free, can I reschedule?", "reschedule"),
    ("EN recording decline -> recording_declined", 40, "No I don't consent to being recorded.", "recording_declined"),
    ("EN wrong person -> wrong_person", 25, "Sorry wrong person, wrong number.", "wrong_person"),
    ("EN short silent -> technical_abort", 40, "", "technical_abort"),
    (
        "EN long reschedule no Q&A -> reschedule",
        240,
        "Is now a good time? I'm not free can I reschedule please? Use the email link. Bye.",
        "reschedule",
    ),
    (
        "EN mid-interview stop -> completed",
        240,
        "First question: tell me about your experience. I worked five years. "
        "Next question: describe a challenge. We fixed stock. I need to reschedule later.",
        "completed",
    ),
    (
        "AR mid-interview stop -> completed",
        200,
        "السؤال الأول خبرتك إيه؟ اشتغلت خمس سنين. السؤال التالي صف لي تحدي. صلحنا المخزون. محتاج إعادة جدولة.",
        "completed",
    ),
    ("AR not free -> reschedule", 70, "الوقت مش مناسب مش فاضي ممكن إعادة جدولة", "reschedule"),
    ("AR recording decline -> recording_declined", 45, "لا أوافق على التسجيل", "recording_declined"),
]
for name, secs, transcript, expect in cases:
    got = classify_interview_session_outcome(duration_seconds=secs, transcript=transcript)
    add(name, got == expect, f"got={got}")

# Structured signals alone can mark progress.
got_sig = classify_interview_session_outcome(
    duration_seconds=90,
    transcript="I need to reschedule later please.",
    session_signals={"questions_asked": 2},
)
add("signals questions_asked -> completed", got_sig == "completed", f"got={got_sig}")

try:
    from app.services.interview_telnyx_tool_service import hangup_interview_call, interview_tool_webhook_urls
    from app.services.interview_booking_service import admin_unlock_interview_booking
    from app.services.interview_outcome_sms_service import maybe_send_interview_outcome_sms

    urls = interview_tool_webhook_urls()
    add("end_call tool URL", "end_call" in urls and "api.voxbulk.com" in urls["end_call"])
    add("admin_unlock present", callable(admin_unlock_interview_booking))
    add("outcome SMS helper present", callable(maybe_send_interview_outcome_sms))
    add("hangup tool helper present", callable(hangup_interview_call))
except Exception as e:
    add("new helpers import", False, str(e))


class _A:
    def __init__(self, arabic: bool):
        self.name = "Jammal - Ar" if arabic else "Leo - En"
        self.voice_label = "Jammal" if arabic else "Leo"
        self.voice_type_label = ""
        self.slug = "jammal" if arabic else "leo"
        self.opening_disclosure_template = "مرحبا" if arabic else "Hello"
        self.system_prompt = "نص عربي" if arabic else "English prompt"
        self.accent_region = "EG" if arabic else "GB"


try:
    assert_interview_agent_language_match({"script_language_code": "en"}, _A(False))
    add("EN interview + EN agent OK", True)
except Exception as e:
    add("EN interview + EN agent OK", False, str(e))
try:
    assert_interview_agent_language_match({"script_language_code": "ar"}, _A(True))
    add("AR interview + AR agent OK", True)
except Exception as e:
    add("AR interview + AR agent OK", False, str(e))
try:
    assert_interview_agent_language_match({"script_language_code": "en"}, _A(True))
    add("EN interview + AR agent blocked", False, "should raise")
except InterviewAgentLanguageMismatch:
    add("EN interview + AR agent blocked", True)
except Exception as e:
    add("EN interview + AR agent blocked", False, str(e))
try:
    assert_interview_agent_language_match({"script_language_code": "ar"}, _A(False))
    add("AR interview + EN agent blocked", False, "should raise")
except InterviewAgentLanguageMismatch:
    add("AR interview + EN agent blocked", True)
except Exception as e:
    add("AR interview + EN agent blocked", False, str(e))


def recip(status, result):
    return ServiceOrderRecipient(
        order_id="x",
        row_number=1,
        name="t",
        status=status,
        result_json=json.dumps(result),
    )


add("lock completed", interview_booking_locked(recip("completed", {})) == BOOKING_LOCKED_MESSAGE)
add(
    "unlock provisional completed",
    interview_booking_locked(recip("completed", {"session_outcome_provisional": True})) is None,
)
add(
    "unlock awaiting reschedule",
    interview_booking_locked(recip("pending", {"awaiting_candidate_action": True})) is None,
)
add(
    "lock opted_out",
    interview_booking_locked(recip("opted_out", {"opted_out": True})) == BOOKING_OPTED_OUT_MESSAGE,
)

db = get_sessionmaker()()
try:
    EmailTemplateService.ensure_system_templates(db)
    for key in [TEMPLATE_THANK_YOU, TEMPLATE_RESCHEDULE, TEMPLATE_OPTED_OUT, "interview_booking_reschedule_link"]:
        row = EmailTemplateService.get(db, key=key)
        add(
            f"DB template {key}",
            row is not None and bool(getattr(row, "is_enabled", True)),
            (str(row.subject)[:70] if row else "missing"),
        )
finally:
    db.close()

from app.services import interview_early_exit_service as eex
from app.services import interview_session_outcome_email_service as oem

add("outcome email dispatcher present", hasattr(oem, "dispatch_interview_session_outcome_email"))
add("reclassify present", hasattr(eex, "maybe_reclassify_completed_interview_after_transcript"))
add("LLM classify present", hasattr(eex, "classify_interview_session_outcome_with_llm"))

print(json.dumps(report, ensure_ascii=False, indent=2))
