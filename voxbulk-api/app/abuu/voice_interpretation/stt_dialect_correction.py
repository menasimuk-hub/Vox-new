"""Post-STT Palestinian/Jordanian dialect correction via DeepSeek."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.abuu.waiter.deepseek_client import WaiterDeepSeekClient

logger = logging.getLogger(__name__)

STT_DIALECT_PROMPT = (
    "طلب طعام بالعربي الفلسطيني. بدي شاورما دجاج. عندكم فلافل. بدي اطلب."
)

STT_CORRECTION_SYSTEM_PROMPT_AR = """أنت مساعد تصحيح نصوص للهجة الفلسطينية والأردنية لخدمة طلب طعام عبر واتساب. تستقبل نصوص مشوهة من تحويل صوت إلى نص. مهمتك تصحيح النص للجملة الأكثر منطقية في سياق طلب الطعام.

قواعد صارمة:
- السياق دائماً طلب طعام — فكر بكلمات الأكل أولاً
- أرجع الجملة العربية المصححة فقط بدون أي شرح أو مقدمة
- لا تضيف كلمات جديدة غير موجودة في المعنى الأصلي
- إذا كان النص صحيح أرجعه كما هو بدون تغيير
- إذا كان النص غير قابل للتصحيح أرجع كلمة: UNCLEAR
- أمثلة على التصحيح الشائع:
  إيدي = بدي
  شاور ماذا = شاورما
  جاج = دجاج
  فلافة = فلافل
  بيتزة = بيتزا
  سندوتش = ساندويش
  كوكا = كوكاكولا
  مي = ماء
  عصير بر = عصير برتقال
  ما لديك = شو عندكم
  اريد = بدي"""

STT_CORRECTION_SYSTEM_PROMPT_EN = """You correct garbled English speech-to-text for a food ordering WhatsApp bot.
Return only the corrected order sentence, no explanation. If already correct return unchanged. If uncorrectable return: UNCLEAR"""

_UNCLEAR_TOKEN = "UNCLEAR"
_ARABIC_CHAR = re.compile(r"[\u0600-\u06FF]")


def is_stt_garbage(raw: str, *, language: str = "ar") -> bool:
    text = str(raw or "").strip()
    if not text:
        return True
    if len(text) < 2:
        return True
    if re.fullmatch(r"\d{10,20}", text):
        return True
    stt_lang = str(language or "ar").strip().lower()
    if stt_lang.startswith("en"):
        return False
    letters = [ch for ch in text if ch.isalpha() or _ARABIC_CHAR.match(ch)]
    if not letters:
        return True
    arabic_count = sum(1 for ch in letters if _ARABIC_CHAR.match(ch))
    if (arabic_count / len(letters)) < 0.4:
        return True
    return False


def rescore_after_correction(
    *,
    raw: str,
    corrected: str,
    raw_confidence: float,
    correction_failed: bool = False,
) -> float:
    from app.abuu.services.abuu_voice_service import is_low_quality_transcript

    cleaned = str(corrected or "").strip()
    if correction_failed or cleaned.upper() == _UNCLEAR_TOKEN:
        return 0.2
    if is_low_quality_transcript(cleaned):
        return 0.2
    if cleaned == str(raw or "").strip():
        return float(raw_confidence)
    return 0.75


def correct_stt_transcript(
    main_db: Session,
    *,
    raw: str,
    phone: str,
    language: str = "ar",
) -> tuple[str, bool]:
    """Return (corrected_text, correction_failed)."""
    raw_text = str(raw or "").strip()
    if not raw_text:
        return raw_text, True

    stt_lang = str(language or "ar").strip().lower()
    system_prompt = STT_CORRECTION_SYSTEM_PROMPT_EN if stt_lang.startswith("en") else STT_CORRECTION_SYSTEM_PROMPT_AR
    user_content = (
        f"Correct this text: {raw_text}"
        if stt_lang.startswith("en")
        else f"صحح هاد النص: {raw_text}"
    )

    try:
        result = WaiterDeepSeekClient.complete(
            main_db,
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=100,
            temperature=0.1,
        )
        if result.fallback_used or not str(result.text or "").strip():
            logger.warning(
                "abuu_stt_correction_failed | phone=%s reason='empty_or_unclear' error=%r",
                phone,
                result.error,
            )
            return raw_text, True

        corrected = str(result.text or "").strip()
        if not corrected or corrected.upper() == _UNCLEAR_TOKEN:
            logger.warning(
                "abuu_stt_correction_failed | phone=%s reason='empty_or_unclear'",
                phone,
            )
            return raw_text, True
        return corrected, False
    except Exception as exc:
        logger.warning(
            "abuu_stt_correction_failed | phone=%s error=%r",
            phone,
            str(exc),
        )
        return raw_text, True
