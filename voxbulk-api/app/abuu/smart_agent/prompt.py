"""System prompt for the Smart Waiter Agent (Arabic-first, tool-calling DeepSeek)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.market.registry import get_market_agent
from app.abuu.models.entities import CustomerProfile, Restaurant
from app.abuu.services.customer_memory_service import first_name, saved_address_summary
from app.abuu.services.kb_service import resolve_settings
from app.abuu.services.reply_service import format_shekel


def _cart_summary_ar(session: AgentSession) -> str:
    if not session.cart:
        return "فارغة"
    lines: list[str] = []
    total_agorot = 0
    for row in session.cart:
        line_total = int(row.get("price", 0) * 100) * int(row.get("quantity") or 1)
        total_agorot += line_total
        lines.append(f"- {row.get('name', '')} x{row.get('quantity', 1)}")
    return "\n".join(lines) + f"\nالمجموع: {format_shekel(total_agorot)}"


def _known_allergens_summary(session: AgentSession, lang: str) -> str:
    allergens = list(session.context.get("allergen_avoid") or [])
    dietary = list(session.context.get("dietary_tags") or [])
    if not allergens and not dietary:
        return "لا يوجد" if lang == "ar" else "none"
    bits: list[str] = []
    if allergens:
        bits.append(("حساسية: " if lang == "ar" else "Allergies: ") + ", ".join(allergens))
    if dietary:
        bits.append(("نظام: " if lang == "ar" else "Diet: ") + ", ".join(dietary))
    return " | ".join(bits)


def build_smart_prompt(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
) -> str:
    lang = session.language or "ar"
    market = get_market_agent(db)
    agent_label = market.display_name_ar if lang == "ar" else market.display_name_en

    restaurant_name = "غير محدد بعد" if lang == "ar" else "not picked yet"
    if session.restaurant_id:
        restaurant = db.get(Restaurant, session.restaurant_id)
        if restaurant is not None:
            restaurant_name = (restaurant.name_ar if lang == "ar" else restaurant.name_en) or restaurant.name_en or restaurant.name_ar

    settings = resolve_settings(db, restaurant_id=session.restaurant_id)
    saved_addr = saved_address_summary(db, customer)
    name = first_name(customer.name)
    cart = _cart_summary_ar(session)
    allergies = _known_allergens_summary(session, lang)

    kb_bits: list[str] = []
    if settings.delivery_fee_agorot:
        kb_bits.append(f"رسوم التوصيل: {format_shekel(settings.delivery_fee_agorot)}")
    if settings.prep_minutes:
        kb_bits.append(f"وقت التحضير: ~{settings.prep_minutes} دقيقة")
    if settings.min_order_agorot:
        kb_bits.append(f"الحد الأدنى: {format_shekel(settings.min_order_agorot)}")

    # System prompt is Arabic by default (Gaza/Palestine market). When the customer writes
    # in English, the agent should still understand but the persona is Palestinian Arabic.
    lines = [
        f"أنت {agent_label} — نادل واتساب ذكي ودود لمطاعم فلسطين/غزة.",
        market.dialect_prompt,
        "هدفك: تساعد العميل يطلب أكل بسرعة وأمان. أنت ذكي، تفهم نية العميل وتقترح بحكمة.",
        "",
        "## قواعد لازم تلتزم فيها",
        "1) استعمل الأدوات (tools) لكل تغيير: search_menu قبل أي اقتراح، add_to_cart بـ item_id حقيقي، confirm_order للإغلاق.",
        "2) ممنوع تختلق أصناف أو أسعار. كل صنف تذكره لازم يكون من نتائج search_menu أو القائمة المعروضة.",
        "3) دايماً اقترح 2-3 خيارات مرقمة مع سعرها + سطر قصير 'ليش' (ليش هذا الخيار مناسب — مثلاً: 'مشوي خفيف', 'بدون مكسرات', 'أرخص', 'الأكثر طلب', 'مناسب للنباتي').",
        "4) إذا العميل ذكر حساسية أو نظام غذائي (حليب، مكسرات، جلوتين، نباتي…)، نادي set_allergy فوراً علشان نحفظها له ولمرات قادمة.",
        "5) ممنوع تقترح صنف يحتوي على حساسية معروفة. لو نتيجة البحث مشكوك فيها (uncertain: true)، نبّه العميل بلطف وخلّيه يقرر.",
        "6) لا تطلب توضيح لو نوع الأكل واضح. إذا قال 'بدي شاورما' → اعرض شاورما مباشرة، ما تسأله 'شو بدك؟'.",
        "7) لما العميل يقول 'أكد' أو 'تأكيد' أو 'اطلب' أو 'OK اعمل الطلب' — نادي confirm_order. ممنوع تقول 'تم الطلب' بدون ما تنفذ الأداة.",
        "8) إذا السلة فاضية وحاول يأكد، قول له بلطف 'لازم نختار أول'.",
        "9) إذا ما في عنوان توصيل محفوظ وقت التأكيد، اطلب من العميل يبعت دبوس موقع واتساب (location pin) قبل ما تنادي confirm_order.",
        "10) ردود قصيرة (2-4 أسطر واتساب)، إيموجي خفيف (🍗😋📍🥗🐟🥤) لما يكون مناسب. صوتك دافئ مثل نادل غزاوي حقيقي، مش روبوت.",
        "11) لا تعرض IDs داخلية للعميل (مثل abuu-rest-xxx أو UUIDs). استخدمها داخلياً مع الأدوات فقط.",
        "12) إذا العميل بدّل رأيه أو طلب يلغي، نادي remove_from_cart أو cancel_order. لا تجادل.",
        "",
        "## معلومات الجلسة",
        f"اسم العميل: {name or 'غير معروف'}",
        f"اللغة المفضّلة: {lang}",
        f"المطعم الحالي: {restaurant_name}",
        f"الحساسيات/النظام المعروف: {allergies}",
        f"السلة الحالية: {cart}",
    ]
    if saved_addr:
        lines.append(f"عنوان التوصيل المحفوظ: {saved_addr}")
    else:
        lines.append("عنوان التوصيل: غير محفوظ — اطلب دبوس واتساب قبل التأكيد.")
    if kb_bits:
        lines.append("معلومات المطعم: " + " | ".join(kb_bits))

    prefetched_list = session.context.get("prefetched_restaurant_list")
    if isinstance(prefetched_list, str) and prefetched_list.strip() and not session.restaurant_id:
        lines.append("")
        lines.append("## المطاعم المتاحة (اعرضها بطبيعية، لا تكرر IDs)")
        lines.append(prefetched_list)

    prefetched_offers = session.context.get("prefetched_offers")
    if isinstance(prefetched_offers, str) and prefetched_offers.strip():
        lines.append("")
        lines.append("## عروض اليوم (اذكرها إذا مناسبة)")
        lines.append(prefetched_offers)

    lines.extend(
        [
            "",
            "## كيف تستعمل الأدوات",
            "- search_menu(query): يرجّع أصناف مع التاجات (allergens, dietary, recipe, protein). استعمل التاجات في 'الليش'.",
            "- add_to_cart(items=[{item_id, quantity, notes}]): يقبل عدة أصناف دفعة وحدة (مثلاً تنين شاورما + كولا).",
            "- set_allergy(allergens=[...], dietary=[...], note=''): يحفظ الحساسية في الجلسة وعلى ملف العميل لمرات قادمة.",
            "- confirm_order(): يقفل الطلب ويبعته للمطعم. لا تنادها إلا لما العميل وافق صراحة.",
            "- list_restaurants / select_restaurant / change_restaurant / list_offers / answer_policy / cancel_order / escalate_to_admin / save_customer_name: استعملها حسب الحاجة.",
            "",
            "ابدأ الآن بمساعدة العميل.",
        ]
    )

    return "\n".join(line for line in lines if line is not None)
