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


def item_added_message(item: RestaurantMenuItem, order: CustomerOrder, lang: str) -> str:
    label = localized_name(item, lang)
    total = format_shekel(order.total_agorot)
    if lang == "en":
        return f"Added {label}. Order total: {total}. Send CONFIRM when ready."
    return f"تمت إضافة {label}. المجموع: {total}. أرسل «تأكيد» عند الانتهاء."


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


def cancel_message(lang: str) -> str:
    if lang == "en":
        return "Order cancelled. Send ABUU anytime to start again."
    return "تم إلغاء الطلب. أرسل «abuu» أو «طلب» للبدء من جديد."


def unknown_message(lang: str) -> str:
    if lang == "en":
        return "Send a dish number, MENU, CONFIRM, or CANCEL."
    return "أرسل رقم الطبق، أو «قائمة»، أو «تأكيد»، أو «إلغاء»."


def voice_fallback_message(lang: str) -> str:
    if lang == "en":
        return "Please type your order as text for now (e.g. send ABUU to start)."
    return "يرجى كتابة طلبك كنص الآن (مثلاً: abuu أو طلب)."
