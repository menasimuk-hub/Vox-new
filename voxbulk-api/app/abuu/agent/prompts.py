"""Dynamic system prompts for Abuu conversational agent."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.agent.skills import enabled_tool_schemas
from app.abuu.models.entities import CustomerProfile, Restaurant
from app.abuu.services.customer_memory_service import first_name, saved_address_summary
from app.abuu.services.kb_service import format_greeting, resolve_settings
from app.abuu.services.reply_service import format_shekel


def _cart_summary(session: AgentSession, lang: str) -> str:
    if not session.cart:
        return "Empty" if lang == "en" else "فارغة"
    lines: list[str] = []
    total_agorot = 0
    for row in session.cart:
        line_total = int(row.get("price", 0) * 100) * int(row.get("quantity") or 1)
        total_agorot += line_total
        lines.append(f"- {row['name']} x{row['quantity']}")
    total = format_shekel(total_agorot)
    header = "Cart:" if lang == "en" else "السلة:"
    return f"{header}\n" + "\n".join(lines) + f"\nTotal: {total}" if lang == "en" else f"{header}\n" + "\n".join(lines) + f"\nالمجموع: {total}"


def build_system_prompt(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
) -> str:
    lang = session.language or "ar"
    restaurant_name = "multiple restaurants"
    if session.restaurant_id:
        restaurant = db.get(Restaurant, session.restaurant_id)
        if restaurant is not None:
            restaurant_name = restaurant.name_en if lang == "en" else restaurant.name_ar
            restaurant_name = restaurant_name or restaurant.name_en or restaurant.name_ar

    settings = resolve_settings(db, restaurant_id=session.restaurant_id)
    cart_summary = _cart_summary(session, lang)
    tool_names = ", ".join(schema["name"] for schema in enabled_tool_schemas(db))
    saved_addr = saved_address_summary(db, customer)
    name = first_name(customer.name)
    greeting = format_greeting(
        settings,
        first_name=name,
        lang=lang,
        saved_address=saved_addr,
    )

    dialect_note = (
        "For Arabic, use natural conversational Gulf/Levant dialect — not formal Arabic."
        if lang == "ar"
        else "Reply in clear, friendly English."
    )

    kb_bits: list[str] = []
    if settings.delivery_fee_agorot:
        kb_bits.append(f"Delivery fee: {format_shekel(settings.delivery_fee_agorot)}")
    if settings.prep_minutes:
        kb_bits.append(f"Prep time: ~{settings.prep_minutes} min")
    if settings.min_order_agorot:
        kb_bits.append(f"Minimum order: {format_shekel(settings.min_order_agorot)}")

    lines = [
        f"You are Abuu, a friendly AI food ordering assistant for {restaurant_name}.",
        "You help customers order food via WhatsApp in Arabic or English.",
        dialect_note,
        "Detect the customer's language from their message and reply in the same language.",
        f"Customer name: {name or 'unknown'}",
        f"Greeting context: {greeting}",
    ]
    if saved_addr:
        lines.append(f"Saved delivery address: {saved_addr}")
    lines.extend(
        [
            f"Current cart: {cart_summary}",
            f"Current stage: {session.stage}",
            "Business facts: " + "; ".join(kb_bits) if kb_bits else "",
            "",
            "You have access to these tools:",
            tool_names,
            "",
            "Rules:",
            "- Always search the menu before listing items — never invent items or prices",
            "- Be warm, concise, and helpful like a good waiter",
            "- Naturally suggest combos and sides after main items",
            "- When cart has items, offer to confirm or continue adding",
            "- Before confirming, ensure delivery location is saved; ask for WhatsApp location pin if missing",
            "- After confirming, give the order ID, estimated wait time, and note payment is pending manual confirmation",
            "- Never expose errors or technical details to the customer",
            "- Use save_customer_name if the customer introduces themselves and name is unknown",
            "- Use list_restaurants / select_restaurant when no restaurant is chosen yet",
        ]
    )
    return "\n".join(line for line in lines if line)
