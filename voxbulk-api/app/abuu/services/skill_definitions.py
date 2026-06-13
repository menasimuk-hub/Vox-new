"""Abuu agent skill names and default configuration."""

from __future__ import annotations

SKILL_GREET_CUSTOMER = "greet_customer"
SKILL_CAPTURE_NAME = "capture_name"
SKILL_CAPTURE_LOCATION = "capture_location"
SKILL_RESTAURANT_SEARCH = "restaurant_search"
SKILL_MENU_RECOMMEND = "menu_recommend"
SKILL_SUGGEST_ADDONS = "suggest_addons"
SKILL_BUILD_CART = "build_cart"
SKILL_CONFIRM_ORDER = "confirm_order"
SKILL_CREATE_PAYMENT = "create_payment"
SKILL_NOTIFY_RESTAURANT = "notify_restaurant"
SKILL_ASSIGN_DRIVER = "assign_driver"
SKILL_ORDER_STATUS = "order_status"
SKILL_CANCEL_OR_REFUND = "cancel_or_refund"
SKILL_HANDOFF_TO_ADMIN = "handoff_to_admin"
SKILL_ANSWER_KB = "answer_kb"

ALL_SKILLS: tuple[str, ...] = (
    SKILL_GREET_CUSTOMER,
    SKILL_CAPTURE_NAME,
    SKILL_CAPTURE_LOCATION,
    SKILL_RESTAURANT_SEARCH,
    SKILL_MENU_RECOMMEND,
    SKILL_SUGGEST_ADDONS,
    SKILL_BUILD_CART,
    SKILL_CONFIRM_ORDER,
    SKILL_CREATE_PAYMENT,
    SKILL_NOTIFY_RESTAURANT,
    SKILL_ASSIGN_DRIVER,
    SKILL_ORDER_STATUS,
    SKILL_CANCEL_OR_REFUND,
    SKILL_HANDOFF_TO_ADMIN,
    SKILL_ANSWER_KB,
)

SKILL_DESCRIPTIONS: dict[str, str] = {
    SKILL_GREET_CUSTOMER: "Welcome the customer and ask what they want to eat.",
    SKILL_CAPTURE_NAME: "Save the customer's first name.",
    SKILL_CAPTURE_LOCATION: "Save delivery location or address.",
    SKILL_RESTAURANT_SEARCH: "List nearby restaurants or show more options.",
    SKILL_MENU_RECOMMEND: "Show menu items matching food preference.",
    SKILL_SUGGEST_ADDONS: "Suggest complementary add-ons after an item is added.",
    SKILL_BUILD_CART: "Add a menu item to the cart.",
    SKILL_CONFIRM_ORDER: "Confirm the order once before payment.",
    SKILL_CREATE_PAYMENT: "Mark order payment as pending manual confirmation.",
    SKILL_NOTIFY_RESTAURANT: "Notify restaurant of a new order.",
    SKILL_ASSIGN_DRIVER: "Explain driver assignment status.",
    SKILL_ORDER_STATUS: "Tell the customer their order status.",
    SKILL_CANCEL_OR_REFUND: "Cancel order or share cancellation/refund policy.",
    SKILL_HANDOFF_TO_ADMIN: "Escalate to human support using KB escalation text.",
    SKILL_ANSWER_KB: "Answer a policy or business info question from KB.",
}


def default_skills_config() -> dict[str, dict[str, bool]]:
    return {skill: {"enabled": True} for skill in ALL_SKILLS}
