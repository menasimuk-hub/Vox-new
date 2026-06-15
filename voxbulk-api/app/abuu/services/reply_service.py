"""Format Arabic-first WhatsApp replies for Abuu."""

from __future__ import annotations

from app.abuu.models.entities import CustomerOrder, Restaurant, RestaurantMenuItem


def format_shekel(agorot: int) -> str:
    return f"{agorot / 100:.2f} ₪"


def localized_name(row: RestaurantMenuItem | Restaurant, lang: str) -> str:
    if lang == "en":
        return getattr(row, "name_en", "") or getattr(row, "name_ar", "")
    return getattr(row, "name_ar", "") or getattr(row, "name_en", "")


def welcome_message(restaurant: Restaurant, lang: str) -> str:
    name = localized_name(restaurant, lang)
    if lang == "en":
        return (
            f"Welcome to {name}!\n"
            "Reply with a dish number to add it, then send CONFIRM to place your order.\n"
            "Send MENU to see items again or CANCEL to stop."
        )
    return (
        f"مرحباً بك في {name}!\n"
        "أرسل رقم الطبق لإضافته، ثم «تأكيد» لإتمام الطلب.\n"
        "أرسل «قائمة» لعرض الأصناف أو «إلغاء» للإيقاف."
    )


def personalized_greeting_message(
    *,
    first_name: str | None,
    lang: str,
    saved_address: str | None = None,
) -> str:
    name = first_name or ("there" if lang == "en" else "صديقي")
    if lang == "en":
        lines = [f"Hello {name}, what would you like to eat today?"]
        lines.append("Tell me chicken, fish, meat, salad, drinks, dessert, or vegetarian.")
        if saved_address:
            lines.append(f"We'll deliver to your saved address: {saved_address}")
        return "\n".join(lines)
    lines = [f"مرحباً {name}، شو حابب تاكل اليوم؟"]
    lines.append("اكتب: دجاج، سمك، لحم، سلطة، مشروبات، حلويات، أو نباتي.")
    if saved_address:
        lines.append(f"سنوصل إلى عنوانك المحفوظ: {saved_address}")
    return "\n".join(lines)


def ask_name_message(lang: str) -> str:
    if lang == "en":
        return "Welcome! What is your first name?"
    return "أهلاً! شو اسمك؟"


def ask_preference_message(*, first_name: str | None, lang: str) -> str:
    return personalized_greeting_message(first_name=first_name, lang=lang)


def category_clarification_message(categories: list[str], lang: str) -> str:
    from app.abuu.services.preference_service import category_label

    labels = [category_label(cat, lang) for cat in categories]
    joined = ", ".join(labels)
    if lang == "en":
        return f"Did you mean {joined}? Reply with one option."
    return f"هل تقصد {joined}؟ أرسل خياراً واحداً."


def already_confirmed_message(lang: str) -> str:
    if lang == "en":
        return "Your order is already confirmed and awaiting payment. Send ABUU to start a new order."
    return "طلبك مؤكد بالفعل وبانتظار الدفع. أرسل «abuu» لبدء طلب جديد."


def voice_low_confidence_message(lang: str) -> str:
    if lang == "en":
        return "I couldn't understand the voice note clearly. Please type your message."
    return "ما فهمت الرسالة الصوتية منيح. اكتب طلبك أو أعد إرسال مقطع أوضح."


def voice_unclear_transcript_message(lang: str) -> str:
    if lang == "en":
        return "I couldn't make out your voice note. What would you like to order? You can type it or send a clearer voice note."
    return "ما قدرت أفهم الرسالة الصوتية. شو حابب تطلب؟ اكتب طلبك أو ابعت رسالة صوتية أوضح."


def preference_menu_message(
    restaurant: Restaurant,
    items: list[tuple[int, RestaurantMenuItem]],
    *,
    categories: list[str],
    lang: str,
) -> str:
    from app.abuu.services.preference_service import category_label

    labels = ", ".join(category_label(cat, lang) for cat in categories)
    lines: list[str] = []
    title = localized_name(restaurant, lang)
    if lang == "en":
        lines.append(f"{labels} options — {title}")
    else:
        lines.append(f"خيارات {labels} — {title}")
    for idx, item in items:
        label = localized_name(item, lang)
        lines.append(f"{idx}. {label} — {format_shekel(item.price_agorot)}")
    if lang == "en":
        lines.append("Reply with a number to add an item.")
    else:
        lines.append("أرسل رقم الطبق لإضافته.")
    return "\n".join(lines)


def conversational_menu_message(
    restaurant: Restaurant,
    items: list[tuple[int, RestaurantMenuItem]],
    *,
    categories: list[str],
    lang: str,
) -> str:
    from app.abuu.services.preference_service import category_label

    labels = ", ".join(category_label(cat, lang) for cat in categories)
    lines: list[str] = []
    title = localized_name(restaurant, lang)
    if lang == "en":
        lines.append(f"{labels} at {title}:")
    else:
        lines.append(f"{labels} — {title}:")
    for _idx, item in items[:6]:
        label = localized_name(item, lang)
        lines.append(f"• {label} — {format_shekel(item.price_agorot)}")
    if lang == "en":
        lines.append("Reply with the item name to add it.")
    else:
        lines.append("أرسل اسم الصنف لإضافته.")
    return "\n".join(lines)


def order_status_message(order: CustomerOrder, assignment, lang: str) -> str:
    status = order.status
    if lang == "en":
        lines = [f"Order status: {status.replace('_', ' ')}"]
        if assignment and assignment.status:
            lines.append(f"Driver: {assignment.status.replace('_', ' ')}")
        return "\n".join(lines)
    lines = [f"حالة الطلب: {status}"]
    if assignment and assignment.status:
        lines.append(f"السائق: {assignment.status}")
    return "\n".join(lines)


def menu_message(
    restaurant: Restaurant,
    items: list[tuple[int, RestaurantMenuItem]],
    lang: str,
) -> str:
    lines: list[str] = []
    title = localized_name(restaurant, lang)
    lines.append(f"{'Menu' if lang == 'en' else 'القائمة'} — {title}")
    for idx, item in items:
        label = localized_name(item, lang)
        lines.append(f"{idx}. {label} — {format_shekel(item.price_agorot)}")
    if lang == "en":
        lines.append("Reply with a number to add an item.")
    else:
        lines.append("أرسل رقم الطبق لإضافته.")
    return "\n".join(lines)


def item_added_message(item: RestaurantMenuItem, order: CustomerOrder, lang: str, *, addon_hint: str | None = None) -> str:
    label = localized_name(item, lang)
    total = format_shekel(order.total_agorot)
    if lang == "en":
        msg = f"Added {label}. Order total: {total}. Send CONFIRM when ready."
    else:
        msg = f"تمت إضافة {label}. المجموع: {total}. أرسل «تأكيد» عند الانتهاء."
    if addon_hint:
        msg += f"\n{addon_hint}"
    return msg


def confirm_pending_payment_message(order: CustomerOrder, lang: str) -> str:
    total = format_shekel(order.total_agorot)
    if lang == "en":
        return (
            f"Order confirmed. Total: {total}.\n"
            "Payment is pending — our team will confirm shortly. Thank you!"
        )
    return (
        f"تم تأكيد طلبك. المجموع: {total}.\n"
        "بانتظار تأكيد الدفع من فريقنا. شكراً لك!"
    )


def order_sent_to_restaurant_message(order: CustomerOrder, lang: str) -> str:
    total = format_shekel(order.total_agorot)
    if lang == "en":
        return (
            f"Order confirmed and sent to the restaurant. Total: {total}.\n"
            "We'll notify you when it's on the way. Thank you — Yallasay!"
        )
    return (
        f"تم تأكيد طلبك وإرساله للمطعم. المجموع: {total}.\n"
        "سنخبرك عندما يكون في الطريق. شكراً لك — يلا ساي!"
    )


def item_unavailable_message(item_name: str, lang: str) -> str:
    if lang == "en":
        return (
            f"Sorry — {item_name} is out of stock for your order.\n"
            "Reply with what you'd like instead (e.g. one more shawarma)."
        )
    return (
        f"عذراً — {item_name} غير متوفر في طلبك.\n"
        "رد برسالة بالبديل الذي تريده (مثال: شاورما إضافية)."
    )


def substitution_prompt_message(item_name: str, lang: str) -> str:
    if lang == "en":
        return (
            f"We couldn't match that item. {item_name} is unavailable.\n"
            "Please reply with the menu item name you want instead."
        )
    return (
        f"لم نتمكن من مطابقة هذا الصنف. {item_name} غير متوفر.\n"
        "يرجى الرد باسم الصنف البديل من القائمة."
    )


def order_substitution_updated_message(
    order: CustomerOrder,
    replacement: object,
    quantity: int,
    lang: str,
) -> str:
    name = getattr(replacement, "name_en", "item") if lang == "en" else getattr(replacement, "name_ar", "item")
    total = format_shekel(order.total_agorot)
    if lang == "en":
        return f"Order updated: added {quantity}× {name}. New total: {total}. Thank you!"
    return f"تم تحديث طلبك: أضفنا {quantity}× {name}. المجموع الجديد: {total}. شكراً لك!"


def driver_outside_message(lang: str) -> str:
    if lang == "en":
        return "Your Yallasay driver is outside / at your door."
    return "سائق يلا ساي وصل إلى بابك / في الخارج."


def cancel_message(lang: str) -> str:
    if lang == "en":
        return "Order cancelled. Send ABUU anytime to start again."
    return "تم إلغاء الطلب. أرسل «abuu» أو «طلب» للبدء من جديد."


def unknown_message(lang: str) -> str:
    if lang == "en":
        return "Send a dish number, MENU, CONFIRM, or CANCEL."
    return "أرسل رقم الطبق، أو «قائمة»، أو «تأكيد»، أو «إلغاء»."


def address_saved_message(lang: str) -> str:
    if lang == "en":
        return "Delivery address saved. Send CONFIRM when your order is ready."
    return "تم حفظ عنوان التوصيل. أرسل «تأكيد» عندما يكون طلبك جاهزاً."


def need_delivery_address_message(lang: str) -> str:
    if lang == "en":
        return (
            "Please share your delivery location (WhatsApp location pin) "
            "or type your address as text, then send CONFIRM."
        )
    return (
        "يرجى إرسال موقع التوصيل (دبوس واتساب) "
        "أو كتابة عنوانك كنص، ثم أرسل «تأكيد»."
    )


def location_clarification_message(lang: str) -> str:
    if lang == "en":
        return (
            "We could not find that address. Please send a WhatsApp location pin "
            "or a clearer address (area, landmark, or street)."
        )
    return (
        "لم نتمكن من تحديد العنوان. يرجى إرسال موقع واتساب "
        "أو عنوان أوضح (الحي، معلم، أو الشارع)."
    )


def out_of_delivery_area_message(lang: str, *, distance_km: float, radius_km: float) -> str:
    if lang == "en":
        return (
            f"Sorry, that location is {distance_km:.1f} km away — "
            f"we deliver within {radius_km:.1f} km only."
        )
    return (
        f"عذراً، الموقع على بعد {distance_km:.1f} كم — "
        f"نغطي التوصيل ضمن {radius_km:.1f} كم فقط."
    )


def voice_fallback_message(lang: str, *, active_order: bool = False) -> str:
    if active_order:
        if lang == "en":
            return (
                "Voice notes aren't supported yet. "
                "Please type a dish number, send MENU, CONFIRM, or CANCEL."
            )
        return (
            "الرسائل الصوتية غير مدعومة حالياً. "
            "يرجى كتابة رقم الطبق، أو «قائمة»، أو «تأكيد»، أو «إلغاء»."
        )
    if lang == "en":
        return "Please type your order as text for now (e.g. send ABUU to start)."
    return "يرجى كتابة طلبك كنص الآن (مثلاً: abuu أو طلب)."
