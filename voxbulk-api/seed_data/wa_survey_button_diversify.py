"""Topic-specific button labels to replace generic Excellent/Good/Poor."""

from __future__ import annotations

EGP = ("Excellent", "Good", "Poor")

# Overall / summary questions may keep Excellent / Good / Poor.
KEEP_EXCELLENT_GOOD_POOR_TOPICS: frozenset[str] = frozenset(
    {
        "Overall experience today",
        "Overall care rating",
        "Overall service rating",
        "Overall dining rating",
        "Overall stay rating",
        "Overall tenancy rating",
        "Overall shopping rating",
        "Overall garage rating",
        "Overall course rating",
        "Overall experience rating",
        "Overall delivery rating",
        "Overall event rating",
        "Overall employee experience",
        "Internal communication",
    }
)

# Best-first order (top = best). Values are lists of 3 labels.
TOPIC_BUTTON_OVERRIDES: dict[str, list[str]] = {
    "Reception staff rating": ["Very professional", "Adequate", "Needs improvement"],
    "Online/app experience": ["Very easy to use", "Adequate", "Frustrating"],
    "Candidate experience": ["Outstanding", "Good", "Disappointing"],
    "Communication quality": ["Very clear", "Adequate", "Unclear"],
    "Communication": ["Very responsive", "Adequate", "Poor"],
    "Food quality": ["Delicious", "Average", "Disappointing"],
    "Drink quality": ["Great taste", "Acceptable", "Poor taste"],
    "Outdoor seating experience": ["Wonderful", "Pleasant", "Unpleasant"],
    "Takeaway packaging": ["Secure & neat", "Acceptable", "Poor quality"],
    "Delivery experience": ["On time & careful", "Acceptable", "Poor"],
    "Check-in experience": ["Very smooth", "Acceptable", "Stressful"],
    "Breakfast quality": ["Delicious", "Average", "Disappointing"],
    "Facilities rating": ["Well maintained", "Adequate", "Below standard"],
    "Check-out experience": ["Quick & pleasant", "Acceptable", "Slow"],
    "Wi-Fi quality": ["Very fast", "Acceptable", "Too slow"],
    "Pool/gym facilities": ["Well equipped", "Adequate", "Below standard"],
    "Evening turndown service": ["Thoughtful", "Adequate", "Not provided"],
    "Viewing experience": ["Very helpful", "Adequate", "Disappointing"],
    "Online portal experience": ["Very easy", "Adequate", "Frustrating"],
    "Product quality": ["High quality", "Acceptable", "Below expectations"],
    "Packaging quality": ["Secure & neat", "Acceptable", "Damaged"],
    "Customer service rating": ["Very helpful", "Adequate", "Unhelpful"],
    "In-store experience": ["Very pleasant", "Adequate", "Poor"],
    "Click & collect experience": ["Quick & smooth", "Acceptable", "Frustrating"],
    "Work quality": ["Expert work", "Acceptable", "Below standard"],
    "MOT experience": ["Very smooth", "Acceptable", "Stressful"],
    "Parts quality": ["Genuine & reliable", "Acceptable", "Questionable"],
    "Course quality": ["Outstanding", "Good", "Below expectations"],
    "Trainer rating": ["Outstanding", "Good", "Below expectations"],
    "Facilities": ["Well equipped", "Adequate", "Below standard"],
    "Course material quality": ["Very useful", "Adequate", "Not useful"],
    "Support quality": ["Very helpful", "Adequate", "Unhelpful"],
    "Online learning experience": ["Engaging", "Adequate", "Frustrating"],
    "Pre-course communication": ["Very clear", "Adequate", "Unclear"],
    "Digital tools experience": ["Very easy", "Adequate", "Frustrating"],
    "Session quality": ["Energising", "Adequate", "Disappointing"],
    "Membership value": ["Great value", "Fair", "Poor value"],
    "Changing room quality": ["Very clean", "Adequate", "Below standard"],
    "App/online portal rating": ["Very easy", "Adequate", "Frustrating"],
    "Digital platform rating": ["Very easy", "Adequate", "Frustrating"],
    "Claims experience": ["Handled well", "Acceptable", "Poor"],
    "Communication/tracking": ["Very accurate", "Adequate", "Unreliable"],
    "Collection experience": ["Quick & easy", "Acceptable", "Frustrating"],
    "Customer service quality": ["Very helpful", "Adequate", "Unhelpful"],
    "App/portal experience": ["Very easy", "Adequate", "Frustrating"],
    "International delivery rating": ["Smooth", "Acceptable", "Problematic"],
    "Venue quality": ["Impressive", "Adequate", "Below standard"],
    "Food & drink quality": ["Great variety", "Adequate", "Limited"],
    "Speaker/performer rating": ["Outstanding", "Good", "Disappointing"],
    "Sound & AV quality": ["Crystal clear", "Adequate", "Poor"],
    "Programme/schedule quality": ["Well paced", "Adequate", "Disorganised"],
    "Merchandise experience": ["Easy & pleasant", "Adequate", "Frustrating"],
}


def is_generic_egp(options: list[str]) -> bool:
    norm = [str(o).strip().lower() for o in options or []]
    return norm == ["excellent", "good", "poor"]


def diversify_question_options(name: str, options: list[str]) -> list[str]:
    topic = str(name or "").strip()
    if topic in KEEP_EXCELLENT_GOOD_POOR_TOPICS and is_generic_egp(options):
        return list(EGP)
    override = TOPIC_BUTTON_OVERRIDES.get(topic)
    if override:
        return list(override)
    if is_generic_egp(options) and topic not in KEEP_EXCELLENT_GOOD_POOR_TOPICS:
        return ["Very satisfied", "Satisfied", "Dissatisfied"]
    return list(options)
