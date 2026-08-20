"""Throwaway elections Customer Feedback demo (one org, not in the wizard)."""

from __future__ import annotations

from typing import Any

ELECTIONS_INDUSTRY_SLUG = "elections"
ELECTIONS_LOCATION_NAME = "الانتخابات التشريعية 2026"
ELECTIONS_OWNER_EMAIL = "jomlauk@gmail.com"
SESSION_MENU_ROLE = "session_menu"
FEEDBACK_MAX_TOPIC_STEPS = 7
WA_NUMBER_HINT = "جاوب برقم، مثلاً 1"

ELECTIONS_THANK_YOU = (
    "شكرًا إلك 🙏\n"
    "إجاباتك بتساعدنا نفهم شو أهم القضايا اللي بتهم الناس.\n"
    "إذا بتحب، فيك الآن تسأل عن برنامج المرشح بأي موضوع، ورح نجاوبك بالمعلومات والمصادر."
)

ELECTIONS_QUESTIONS: list[dict[str, Any]] = [
    {
        "slug": "top_issue",
        "name": "أهم قضية",
        "intro": (
            "بدنا نعرف شو أهم شيء بالنسبة إلك بالانتخابات. "
            "ما رح نطلب اسمك أو أي معلومات شخصية.\n\n"
            "1️⃣ شو أهم قضية بالنسبة إلك؟"
        ),
        "options": [
            "فرص العمل والدخل",
            "الأسعار وتكاليف المعيشة",
            "التعليم",
            "الصحة",
            "الخدمات والبنية التحتية",
            "مكافحة الفساد",
            "قضية أخرى",
        ],
    },
    {
        "slug": "why_not_vote",
        "name": "سبب عدم الانتخاب",
        "intro": "شكرًا. سؤال ثاني 👇\n\n2️⃣ شو أكثر سبب ممكن يخليك ما تنتخب؟",
        "options": [
            "ما بثق بالمرشحين",
            "ما بشوف فرق بينهم",
            "محبط وما بتوقع يتغير شيء",
            "ما بعرف البرامج الانتخابية",
            "ما بدي أصوّت بسبب انتماءات سياسية",
            "ما عندي مانع أنتخب",
        ],
    },
    {
        "slug": "candidate_priority",
        "name": "أهم شيء بالمرشح",
        "intro": "شكرًا. سؤال ثالث 👇\n\n3️⃣ لما تقرر تنتخب، شو أهم شيء بتدور عليه بالمرشح؟",
        "options": [
            "برنامج واضح",
            "نزاهة وشفافية",
            "خبرة وكفاءة",
            "إنجازات سابقة",
            "فهمه لمشاكل الناس",
            "الانتماء للتنظيم",
            "شيء آخر",
        ],
    },
    {
        "slug": "one_minute_question",
        "name": "سؤال للدقيقة",
        "intro": "شكرًا. سؤال رابع 👇\n\n4️⃣ لو عندك دقيقة مع المرشح، شو السؤال اللي بتسأله؟",
        "options": [
            "شو خطتك لتوفير فرص العمل؟",
            "شو خطتك لتحسين الوضع الاقتصادي؟",
            "كيف رح تحارب الفساد؟",
            "شو رح تعمل للتعليم والصحة؟",
            "كيف رح تنفذ وعودك؟",
            "سؤال آخر",
        ],
    },
    {
        "slug": "learn_programme",
        "name": "طريقة معرفة البرنامج",
        "intro": "شكرًا. سؤال خامس 👇\n\n5️⃣ شو الطريقة اللي بتفضل تعرف فيها برنامج المرشح؟",
        "options": [
            "فيديو قصير 🎥",
            "شرح على WhatsApp 💬",
            "مقارنة بين البرامج 📊",
            "أسأل AI وأحصل على جواب",
            "لقاء مباشر مع المرشح",
            "قراءة البرنامج كامل",
        ],
    },
    {
        "slug": "ask_candidate",
        "name": "سؤال مباشر للمرشح",
        "intro": "شكرًا. سؤال سادس 👇\n\n6️⃣ هل بتحب تسأل المرشح سؤال مباشرة؟",
        "options": [
            "نعم، اسألني",
            "نعم، بس بشكل مجهول",
            "لا",
        ],
    },
    {
        "slug": "give_chance",
        "name": "فرصة للمرشح",
        "intro": "شكرًا. آخر سؤال ❤️\n\n7️⃣ إذا اقتنعت أن المرشح عنده برنامج واضح وقابل للتنفيذ، هل ممكن تعطيه فرصة؟",
        "options": [
            "نعم",
            "ممكن",
            "لا",
            "مش متأكد",
        ],
    },
]


def is_elections_industry_slug(slug: str | None) -> bool:
    return str(slug or "").strip().lower() == ELECTIONS_INDUSTRY_SLUG


def is_elections_feedback_template(db: Any, tpl: Any) -> bool:
    """True when the row belongs to the throwaway elections industry (never Meta)."""
    if tpl is None or db is None:
        return False
    from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType

    industry_id = getattr(tpl, "industry_id", None)
    if industry_id:
        ind = db.get(FeedbackIndustry, industry_id)
        if is_elections_industry_slug(getattr(ind, "slug", None)):
            return True
    survey_type_id = getattr(tpl, "survey_type_id", None)
    if survey_type_id:
        st = db.get(FeedbackSurveyType, survey_type_id)
        if st is not None:
            ind = db.get(FeedbackIndustry, st.industry_id)
            if is_elections_industry_slug(getattr(ind, "slug", None)):
                return True
    return False


def is_session_menu_template(tpl: Any) -> bool:
    if tpl is None:
        return False
    return str(getattr(tpl, "step_role", None) or "").strip().lower() == SESSION_MENU_ROLE
