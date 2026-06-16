"""Dynamic system prompts for Gaza Agent (DeepSeek chat waiter)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.agent.skills import enabled_tool_schemas
from app.abuu.market.registry import get_market_agent
from app.abuu.models.entities import CustomerProfile, Restaurant
from app.abuu.services.customer_memory_service import first_name, saved_address_summary
from app.abuu.services.kb_service import format_greeting, resolve_settings
from app.abuu.services.reply_service import format_shekel
from app.core.config import get_settings


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
    if lang == "en":
        return f"{header}\n" + "\n".join(lines) + f"\nTotal: {total}"
    return f"{header}\n" + "\n".join(lines) + f"\nالمجموع: {total}"


def build_system_prompt(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
) -> str:
    lang = session.language or "ar"
    market = get_market_agent(db)
    agent_label = market.display_name_ar if lang == "ar" else market.display_name_en

    restaurant_name = "multiple restaurants"
    if session.restaurant_id:
        restaurant = db.get(Restaurant, session.restaurant_id)
        if restaurant is not None:
            restaurant_name = restaurant.name_en if lang == "en" else restaurant.name_ar
            restaurant_name = restaurant_name or restaurant.name_en or restaurant.name_ar

    settings = resolve_settings(db, restaurant_id=session.restaurant_id)
    cart_summary = _cart_summary(session, lang)
    saved_addr = saved_address_summary(db, customer)
    name = first_name(customer.name)
    greeting = format_greeting(
        settings,
        first_name=name,
        lang=lang,
        saved_address=saved_addr,
    )

    kb_bits: list[str] = []
    if settings.delivery_fee_agorot:
        kb_bits.append(f"Delivery fee: {format_shekel(settings.delivery_fee_agorot)}")
    if settings.prep_minutes:
        kb_bits.append(f"Prep time: ~{settings.prep_minutes} min")
    if settings.min_order_agorot:
        kb_bits.append(f"Minimum order: {format_shekel(settings.min_order_agorot)}")

    lines = [
        f"You are {agent_label} — a friendly Gaza restaurant waiter on WhatsApp.",
        market.dialect_prompt,
        "Scope: food ordering ONLY (restaurants, menu, offers, cart, delivery, confirm). "
        "If off-topic, gently redirect to ordering.",
        "Sound like a real waiter — NOT an IVR phone tree. Do not say 'press 1' or 'choose a number' unless asked.",
        "When no restaurant is selected, mention ALL available restaurants BY NAME in natural speech.",
        "Never auto-pick a restaurant the customer did not choose.",
        "Keep replies under 3 short WhatsApp lines.",
        "Use ONLY menu/prices from the facts below — never invent items.",
        f"Customer name: {name or 'unknown'}",
        f"Greeting context: {greeting}",
    ]
    if saved_addr:
        lines.append(f"Saved delivery address: {saved_addr}")

    prefetched_list = session.context.get("prefetched_restaurant_list")
    if isinstance(prefetched_list, str) and prefetched_list.strip() and not session.restaurant_id:
        lines.append(f"Restaurants (facts — weave into natural speech):\n{prefetched_list}")

    prefetched_menu = session.context.get("prefetched_menu")
    if isinstance(prefetched_menu, str) and prefetched_menu.strip() and session.restaurant_id:
        lines.append(f"Menu (facts):\n{prefetched_menu}")

    prefetched_offers = session.context.get("prefetched_offers")
    if isinstance(prefetched_offers, str) and prefetched_offers.strip():
        lines.append(f"Offers (facts):\n{prefetched_offers}")

    lines.extend(
        [
            f"Current cart: {cart_summary}",
            f"Current stage: {session.stage}",
            "Business facts: " + "; ".join(kb_bits) if kb_bits else "",
        ]
    )

    if not get_settings().abuu_agent_waiter_mode:
        tool_names = ", ".join(schema["name"] for schema in enabled_tool_schemas(db))
        lines.extend(
            [
                "",
                "You have access to these tools:",
                tool_names,
                "",
                "Rules:",
                "- Use tools for cart changes and confirmations.",
                "- Never assume a restaurant without customer choice.",
            ]
        )
    else:
        lines.append(
            "Waiter mode: reply in natural language only this turn. "
            "Cart changes happen server-side when customer picks items by name or number from the menu facts."
        )

    return "\n".join(line for line in lines if line)
