"""Single-LLM conversation brain for YallaSay WhatsApp waiter."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.session import _cart_from_order, save_session
from app.abuu.conversation.restaurant_guard import RestaurantGuard, bind_restaurant_context, clear_switch_context
from app.abuu.conversation.wa_sanitize import wa_customer_sanitize
from app.abuu.market.registry import get_market_agent
from app.abuu.menu_intelligence.dietary_detector import DietaryDetector
from app.abuu.menu_intelligence.query import MenuQuery
from app.abuu.menu_intelligence.query_expansion import expand_food_query, expansion_context_payload
from app.abuu.menu_intelligence.search_service import MenuSearchService
from app.abuu.models.entities import CustomerOrder, CustomerProfile, Restaurant, RestaurantMenuCategory, RestaurantMenuItem
from app.abuu.agent.session_reset import cancel_empty_draft, clear_restaurant_binding
from app.abuu.services.customer_memory_service import apply_saved_address_to_order, first_name, saved_address_summary
from app.abuu.services.intent_service import is_abuu_start_message
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.preference_service import match_food_categories
from app.abuu.services.reply_service import ask_name_message, format_shekel, localized_name, personalized_greeting_message
from app.abuu.services.restaurant_discovery_service import (
    RankedRestaurant,
    format_restaurant_list,
    pick_restaurant_by_ref,
    rank_restaurants,
)
from app.abuu.voice_interpretation.fuzzy_match import best_fuzzy_match
from app.abuu.waiter.deepseek_client import WaiterDeepSeekClient
from app.abuu.waiter.interpretation import InterpretationResult, WaiterInterpretation
from app.abuu.waiter.session_store import WaiterSessionStore
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_CONFIRM_WORDS = frozenset({"أكد", "تأكيد", "confirm", "yes", "ok", "تمام", "يلا", "نعم"})
FORBIDDEN_REPLY_FRAGMENTS = ("كيف بقدر أساعدك", "ما لقيت أطباق")
_DEFAULT_SEARCH_LIMIT = 10
_REFINE_SEARCH_LIMIT = 15
_SHOW_ALL_LIMIT = 20

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_REFINE_MARKERS = (
    "لا بدي",
    "مش هيك",
    "مو هيك",
    "لا ",
    "مش ",
    "مو ",
    "no i need",
    "no ",
    "not ",
    "actually",
)

_SHOW_ALL_RE = re.compile(r"(ورّ?يني الكل|كل ال|show all|show me all)", re.I)

_MASTER_PROMPT = """أنت يلا ساي (YallaSay) — نادل واتساب ذكي للمطاعم في فلسطين/الأردن.
تتكلم باللهجة الفلسطينية/الأردنية الطبيعية (مش فصحى رسمية).
أنت مو روبوت — أنت نادل محلي ودود يفهم "بدي"، "شو"، "إيش"، "جاج"=دجاج، "مش"=لا.

## هويتك
- اسمك: يلا ساي
- دورك: تساعد الزبون يختار مطعم، يطلب أكل، يضيف إضافات، ويأكد الطلب
- قاعدة ذهبية: كل طلب = مطعم واحد. رسوم التوصيل 15 ₪ لكل طلب مطعم

## بيانات الجلسة
- اسم الزبون: {customer_name}
- رقم الهاتف: {phone}
- العنوان المحفوظ: {saved_address}
- حساسيات معروفة: {allergens}
- المطعم المختار: {selected_restaurant}
- السلة: {cart_items}
- مجموع السلة: {cart_total}

## آخر المحادثة
{conversation_history}

## المطاعم المتاحة (إذا ما في مطعم مختار)
{restaurant_list}

## أفضل النتائج للعرض الآن (لا تعرض أكثر من 10 إلا إذا طلب)
{search_results}

## فهرس المنيو (للمرجع فقط — لا تنسخه كامل للزبون)
{menu_catalog_summary}

## آخر بحث طعام
{last_food_search}

## رسالة الزبون الآن
{customer_message}

## قواعد فهم الأرقام (مهم جداً)
1. إذا آخر رسالة منك كانت قائمة مطاعم مرقّمة و الزبون قال رقم (1، ٢، ١، "واحد"):
   → action = "select_restaurant"
   → restaurant_id = ID المطعم من القائمة
   → reply = ترحيب بالمطعم + اسأل شو بدو يطلب
   → ممنوع تقول "كيف بقدر أساعدك" أو أي رد عام

2. إذا عرضت أطباق مرقّمة و الزبون قال رقم:
   → action = "add_to_cart" أو "ask_addons"
   → item_id = ID الطبق من المنيو

3. حوّل الأرقام العربية ٠١٢٣ إلى 123 داخلياً

## قواعد المحادثة الطبيعية
- تكلم مثل نادل بشري: ردود قصيرة وودودة
- طلب عام ("بدي دجاج") → اعرض أفضل 10 من {search_results} مرقّمة + "في كمان خيارات — حدّد أكثر 😋"
- رفض ("لا بدي هندي") → اعترف بلطف ثم اعرض قائمة أضيق
- لا تلصق 30+ صنف في رسالة واحدة
- "نفس الشي" → أعد آخر صنف
- "أكد" / "تمام" / "يلا" → action = "confirm_order" إذا السلة جاهزة

## ممنوعات
- لا ترد "كيف بقدر أساعدك في طلبك؟" إذا في سياق واضح
- لا تخترع أطباق أو IDs — استخدم فقط IDs من البيانات أعلاه

## المخرجات
أجب JSON فقط بدون markdown:
{{"reply":"...","action":"select_restaurant|show_restaurants|show_menu|add_to_cart|ask_addons|confirm_order|ask_address|none","restaurant_id":null|"uuid","item_id":null|"uuid","order_confirmed":false|true}}"""


@dataclass
class ParsedAction:
    reply: str
    action: str = "none"
    restaurant_id: str | None = None
    item_id: str | None = None
    order_confirmed: bool = False


@dataclass
class SearchBuildResult:
    formatted: str
    items: list[RestaurantMenuItem]
    index: dict[str, str]
    meta: dict[str, Any]
    cross_restaurant: bool = False
    item_restaurants: dict[str, str] | None = None


def _pilot_ids(db: Session) -> tuple[str, ...] | None:
    if not get_settings().abuu_pilot_only:
        return None
    return get_market_agent(db).pilot_restaurant_ids


def _smart_log(event: str, **fields: Any) -> None:
    logger.info("abuu_smart_pipeline_%s | %s", event, " ".join(f"{k}={v}" for k, v in fields.items()))


def _normalize_selection(text: str) -> str:
    return str(text or "").strip().translate(_ARABIC_DIGITS)


def _is_numeric_pick(text: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}", _normalize_selection(text)))


def _is_refinement(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return any(marker in lowered for marker in _REFINE_MARKERS)


def _merge_search_text(text: str, ctx: dict[str, Any]) -> str:
    last = ctx.get("last_food_search") or {}
    if not isinstance(last, dict):
        return text
    if not _is_refinement(text):
        return text
    prev = str(last.get("expanded") or last.get("raw") or "").strip()
    cleaned = str(text or "")
    for marker in _REFINE_MARKERS:
        cleaned = cleaned.replace(marker, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if prev and cleaned:
        return f"{prev} {cleaned}".strip()
    return cleaned or text


def _search_limit(text: str, ctx: dict[str, Any]) -> int:
    if _SHOW_ALL_RE.search(str(text or "")):
        return _SHOW_ALL_LIMIT
    if _is_refinement(text):
        return _REFINE_SEARCH_LIMIT
    return _DEFAULT_SEARCH_LIMIT


def _ranked_restaurants(abuu_db: Session) -> list[RankedRestaurant]:
    pilot = _pilot_ids(abuu_db)
    restaurant_ids = list(pilot) if pilot else None
    return rank_restaurants(abuu_db, lat=None, lng=None, categories=None, limit=15, restaurant_ids=restaurant_ids)


def _refresh_restaurant_index(session, ranked: list[RankedRestaurant]) -> dict[str, str]:
    index = {str(i): row.restaurant.id for i, row in enumerate(ranked, start=1)}
    session.context = dict(session.context or {})
    session.context["smart_restaurant_index"] = index
    session.context["ranked_restaurant_ids"] = [row.restaurant.id for row in ranked]
    if not session.restaurant_id:
        session.context["awaiting_restaurant_pick"] = True
    return index


def _format_history(session, *, lang: str) -> str:
    messages = list((session.context or {}).get("messages") or [])
    if not messages:
        return "(لا يوجد)"
    lines: list[str] = []
    for entry in messages[-10:]:
        role = str(entry.get("role") or "")
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        label = "العميل" if role == "customer" else "يلا"
        lines.append(f"{label}: {text}")
    return "\n".join(lines) if lines else "(لا يوجد)"


def _format_cart(session, lang: str) -> tuple[str, str]:
    if not session.cart:
        empty = "فاضية" if lang == "ar" else "empty"
        return empty, "0.00 ₪"
    lines = []
    total = 0.0
    for line in session.cart:
        name = str(line.get("name") or "صنف")
        qty = int(line.get("quantity") or 1)
        price = float(line.get("price") or 0)
        lines.append(f"- {name} x{qty} — {price * qty:.2f} ₪")
        total += price * qty
    return "\n".join(lines), f"{total:.2f} ₪"


def _format_items_numbered(items: list[RestaurantMenuItem], lang: str) -> tuple[str, dict[str, str]]:
    lines: list[str] = []
    index: dict[str, str] = {}
    for i, item in enumerate(items, start=1):
        key = str(i)
        index[key] = item.id
        lines.append(f"{i}. {localized_name(item, lang)} — {format_shekel(item.price_agorot)}")
    return "\n".join(lines), index


def _format_cross_restaurant_numbered(
    hits: list[tuple[RestaurantMenuItem, Restaurant]],
    lang: str,
) -> tuple[str, dict[str, str], dict[str, str]]:
    lines: list[str] = []
    index: dict[str, str] = {}
    item_restaurants: dict[str, str] = {}
    for i, (item, restaurant) in enumerate(hits, start=1):
        key = str(i)
        index[key] = item.id
        item_restaurants[item.id] = restaurant.id
        rest_name = localized_name(restaurant, lang)
        lines.append(f"{i}. {localized_name(item, lang)} — {format_shekel(item.price_agorot)} ({rest_name})")
    return "\n".join(lines), index, item_restaurants


def _is_food_query(text: str, ctx: dict[str, Any], main_db: Session) -> bool:
    merged = _merge_search_text(text, ctx)
    if match_food_categories(merged) or match_food_categories(text):
        return True
    from app.abuu.menu_intelligence.query_expansion import apply_food_synonyms

    if apply_food_synonyms(merged) != merged.strip():
        return True
    expansion = expand_food_query(main_db, raw=merged)
    return not expansion.unknown and bool(str(expansion.expanded or "").strip())


def _restaurant_ids_for_search(abuu_db: Session) -> list[str]:
    pilot = _pilot_ids(abuu_db)
    if pilot:
        return list(pilot)
    ranked = rank_restaurants(abuu_db, lat=None, lng=None, categories=None, limit=15)
    return [row.restaurant.id for row in ranked]


def _search_one_restaurant(
    abuu_db: Session,
    *,
    restaurant_id: str,
    query: MenuQuery,
    customer: CustomerProfile,
) -> list[RestaurantMenuItem]:
    restaurant = abuu_db.get(Restaurant, restaurant_id)
    if restaurant is None or restaurant.is_deleted or not restaurant.is_available:
        return []
    return MenuSearchService.search(abuu_db, restaurant_id, query, customer=customer)


def _cross_restaurant_search(
    abuu_db: Session,
    main_db: Session,
    *,
    session,
    customer: CustomerProfile,
    text: str,
    lang: str,
) -> SearchBuildResult:
    ctx = session.context or {}
    merged = _merge_search_text(text, ctx)
    limit = _search_limit(text, ctx)
    expansion = expand_food_query(main_db, raw=merged)
    session.context = dict(ctx)
    session.context["last_query_expansion"] = expansion_context_payload(expansion)
    search_text = expansion.expanded if not expansion.unknown else merged

    categories = list(match_food_categories(search_text))
    for cat in match_food_categories(merged):
        if cat not in categories:
            categories.append(cat)

    allergen_avoid = list(ctx.get("allergen_avoid") or [])
    dietary_required = list(ctx.get("dietary_tags") or [])

    query = MenuQuery.from_categories(categories, limit=limit)
    query.text_query = search_text
    query.allergen_avoid = allergen_avoid
    query.dietary_required = dietary_required

    hits: list[tuple[RestaurantMenuItem, Restaurant]] = []
    seen_items: set[str] = set()
    for rid in _restaurant_ids_for_search(abuu_db):
        if len(hits) >= limit:
            break
        restaurant = abuu_db.get(Restaurant, rid)
        if restaurant is None:
            continue
        per_query = query
        items = _search_one_restaurant(abuu_db, restaurant_id=rid, query=per_query, customer=customer)
        if not items and search_text != merged:
            per_query = MenuQuery.from_categories(categories, limit=limit)
            per_query.text_query = merged
            per_query.allergen_avoid = allergen_avoid
            per_query.dietary_required = dietary_required
            items = _search_one_restaurant(abuu_db, restaurant_id=rid, query=per_query, customer=customer)
        for item in items:
            if item.id in seen_items:
                continue
            seen_items.add(item.id)
            hits.append((item, restaurant))
            if len(hits) >= limit:
                break

    formatted, index, item_restaurants = _format_cross_restaurant_numbered(hits, lang)
    items_only = [item for item, _rest in hits]
    meta = {
        "raw": merged,
        "expanded": search_text,
        "item_ids": [item.id for item in items_only],
        "shown_count": len(items_only),
        "cross_restaurant": True,
    }
    session.context["last_food_search"] = meta
    session.context["smart_menu_index"] = index
    session.context["smart_menu_item_restaurants"] = item_restaurants
    if items_only:
        session.context["awaiting_dish_pick"] = True
    return SearchBuildResult(
        formatted=formatted or "(لا نتائج)",
        items=items_only,
        index=index,
        meta=meta,
        cross_restaurant=True,
        item_restaurants=item_restaurants,
    )


def _menu_catalog_summary(abuu_db: Session, restaurant_id: str, lang: str) -> str:
    items = AbuuOrderDraftService.list_menu_items(abuu_db, restaurant_id, limit=500)
    if not items:
        return "(لا يوجد منيو)"
    by_type: dict[str, int] = {}
    for item in items:
        key = str(item.item_type or "other")
        by_type[key] = by_type.get(key, 0) + 1
    parts = [f"{k}: {v}" for k, v in sorted(by_type.items())]
    return f"إجمالي {len(items)} صنف — " + ", ".join(parts[:12])


def _build_search_results(
    abuu_db: Session,
    main_db: Session,
    *,
    session,
    customer: CustomerProfile,
    text: str,
    lang: str,
) -> SearchBuildResult:
    ctx = session.context or {}
    if not session.restaurant_id:
        if _is_food_query(text, ctx, main_db):
            return _cross_restaurant_search(
                abuu_db, main_db, session=session, customer=customer, text=text, lang=lang
            )
        return SearchBuildResult(
            formatted="(اختر مطعم — قول رقم أو اسمه)",
            items=[],
            index={},
            meta={"cross_restaurant": False},
        )

    merged = _merge_search_text(text, ctx)
    limit = _search_limit(text, ctx)
    expansion = expand_food_query(main_db, raw=merged)
    session.context = dict(ctx)
    session.context["last_query_expansion"] = expansion_context_payload(expansion)
    search_text = expansion.expanded if not expansion.unknown else merged

    categories = list(match_food_categories(search_text))
    for cat in match_food_categories(merged):
        if cat not in categories:
            categories.append(cat)

    allergen_avoid = list(ctx.get("allergen_avoid") or [])
    dietary_required = list(ctx.get("dietary_tags") or [])

    query = MenuQuery.from_categories(categories, limit=limit)
    query.text_query = search_text
    query.allergen_avoid = allergen_avoid
    query.dietary_required = dietary_required

    items = MenuSearchService.search(abuu_db, session.restaurant_id, query, customer=customer)
    if not items and search_text != merged:
        query.text_query = merged
        items = MenuSearchService.search(abuu_db, session.restaurant_id, query, customer=customer)

    formatted, index = _format_items_numbered(items, lang)
    meta = {
        "raw": merged,
        "expanded": search_text,
        "item_ids": [item.id for item in items],
        "shown_count": len(items),
    }
    session.context["last_food_search"] = meta
    session.context["smart_menu_index"] = index
    if items:
        session.context["awaiting_dish_pick"] = True
    return SearchBuildResult(formatted=formatted or "(لا نتائج)", items=items, index=index, meta=meta)


def _load_order(abuu_db: Session, phone: str) -> CustomerOrder | None:
    draft = AbuuOrderDraftService.get_session(abuu_db, phone)
    if draft and draft.active_order_id:
        return abuu_db.get(CustomerOrder, draft.active_order_id)
    return None


def _handle_start_message(
    abuu_db: Session,
    *,
    phone: str,
    session,
    customer: CustomerProfile,
    text: str,
    lang: str,
) -> ParsedAction | None:
    if not is_abuu_start_message(text):
        return None

    ctx = dict(session.context or {})
    order = _load_order(abuu_db, phone)
    if ctx.get("restaurant_selected") and ctx.get("greeting_sent") and order and order.status == "draft":
        return None

    if order and order.status == "draft":
        cancel_empty_draft(abuu_db, order)
    clear_restaurant_binding(abuu_db, session, full_reset=False)

    default_address = saved_address_summary(abuu_db, customer)
    lat = lng = None
    from app.abuu.services.location_service import get_default_address

    addr = get_default_address(abuu_db, customer.id)
    if addr and addr.latitude is not None and addr.longitude is not None:
        lat, lng = addr.latitude, addr.longitude
    restaurant = AbuuOrderDraftService.default_restaurant(abuu_db, lat=lat, lng=lng)
    if restaurant is None:
        return ParsedAction(
            reply="لا توجد مطاعم متاحة حالياً." if lang == "ar" else "No restaurants are available right now.",
            action="none",
        )

    order = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=restaurant)
    apply_saved_address_to_order(abuu_db, order, customer)
    session.restaurant_id = restaurant.id
    session.active_order_id = order.id
    session.context = bind_restaurant_context({}, restaurant.id)
    session.context["greeting_sent"] = False
    session.context["active_categories"] = []
    session.context["suggested_items"] = []

    if not customer.name:
        session.stage = "awaiting_name"
        return ParsedAction(reply=ask_name_message(lang), action="none", restaurant_id=restaurant.id)

    session.context["greeting_sent"] = True
    session.stage = "awaiting_preference"
    reply = personalized_greeting_message(
        first_name=first_name(customer.name),
        lang=lang,
        saved_address=default_address,
    )
    return ParsedAction(reply=reply, action="none", restaurant_id=restaurant.id)


def _bind_restaurant(
    abuu_db: Session,
    *,
    session,
    customer: CustomerProfile,
    order: CustomerOrder | None,
    restaurant: Restaurant,
) -> CustomerOrder:
    session.restaurant_id = restaurant.id
    session.context = bind_restaurant_context(
        clear_switch_context(dict(session.context or {})),
        restaurant.id,
    )
    session.context.pop("smart_restaurant_index", None)
    session.context.pop("awaiting_restaurant_pick", None)
    session.context["awaiting_dish_pick"] = False
    session.stage = "browsing"
    order = AbuuOrderDraftService.ensure_order(
        abuu_db,
        customer=customer,
        restaurant=restaurant,
        existing_order=order,
        context=session.context,
    )
    session.active_order_id = order.id
    return order


def _restaurant_welcome(restaurant: Restaurant, lang: str) -> str:
    name = localized_name(restaurant, lang)
    if lang == "en":
        return f"Welcome to {name}! 🍗 What would you like to order?"
    return f"أهلاً في {name}! 🍗 شو بدك تطلب؟"


def _resolve_restaurant_pick(text: str, ctx: dict[str, Any], ranked: list[RankedRestaurant]) -> Restaurant | None:
    normalized = _normalize_selection(text)
    index = ctx.get("smart_restaurant_index") or {}
    if _is_numeric_pick(normalized):
        rid = index.get(normalized)
        if rid:
            return next((row.restaurant for row in ranked if row.restaurant.id == rid), None)
    return pick_restaurant_by_ref(ranked, normalized)


def _item_restaurant(abuu_db: Session, item: RestaurantMenuItem, session) -> Restaurant | None:
    if session.restaurant_id:
        rest = abuu_db.get(Restaurant, session.restaurant_id)
        if rest:
            return rest
    cat = abuu_db.get(RestaurantMenuCategory, item.category_id)
    if cat is None:
        return None
    return abuu_db.get(Restaurant, cat.restaurant_id)


def _is_menu_browse_query(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if match_food_categories(normalized):
        browse_markers = ("بدي", "شو", "عندك", "إيش", "what", "menu", "منيو", "قائمة", "show")
        if any(m in normalized for m in browse_markers):
            return True
    return False


def _resolve_menu_pick(text: str, ctx: dict[str, Any]) -> str | None:
    normalized = _normalize_selection(text)
    index = ctx.get("smart_menu_index") or {}
    if _is_numeric_pick(normalized):
        return index.get(normalized)
    return None


def _try_deterministic(
    abuu_db: Session,
    *,
    session,
    customer: CustomerProfile,
    order: CustomerOrder | None,
    text: str,
    ranked: list[RankedRestaurant],
    lang: str,
) -> ParsedAction | None:
    ctx = session.context or {}
    normalized = _normalize_selection(text)

    if normalized.lower() in _CONFIRM_WORDS:
        return None

    if not session.restaurant_id:
        if _is_numeric_pick(normalized) or ctx.get("awaiting_restaurant_pick"):
            picked = _resolve_restaurant_pick(text, ctx, ranked)
            if picked is not None:
                _bind_restaurant(abuu_db, session=session, customer=customer, order=order, restaurant=picked)
                return ParsedAction(
                    reply=_restaurant_welcome(picked, lang),
                    action="select_restaurant",
                    restaurant_id=picked.id,
                )

    if session.restaurant_id:
        item_id = _resolve_menu_pick(text, ctx)
        if item_id and (_is_numeric_pick(normalized) or ctx.get("awaiting_dish_pick")):
            return ParsedAction(reply="", action="add_to_cart", item_id=item_id)

        if (
            len(normalized) > 2
            and not _is_numeric_pick(normalized)
            and not _is_refinement(text)
            and not _is_menu_browse_query(text)
        ):
            items = AbuuOrderDraftService.list_menu_items(abuu_db, session.restaurant_id, limit=80, customer=customer)
            pool = [
                {
                    "id": item.id,
                    "name": localized_name(item, lang),
                    "name_ar": item.name_ar,
                    "name_en": item.name_en,
                }
                for item in items
            ]
            best, score, _ranked = best_fuzzy_match(normalized, pool, language=lang, min_score=55)
            if best and score >= 55:
                return ParsedAction(reply="", action="add_to_cart", item_id=str(best["id"]))

    return None


def _build_prompt_with_db(
    abuu_db: Session,
    *,
    session,
    customer: CustomerProfile,
    phone: str,
    text: str,
    ranked: list[RankedRestaurant],
    search: SearchBuildResult,
    lang: str,
) -> str:
    ctx = session.context or {}
    fn = first_name(customer.name) or ("صديقي" if lang == "ar" else "friend")
    addr = saved_address_summary(abuu_db, customer) or "—"
    allergens = ", ".join(ctx.get("allergen_avoid") or []) or "—"
    selected = "—"
    if session.restaurant_id:
        rest = abuu_db.get(Restaurant, session.restaurant_id)
        if rest:
            selected = f"{localized_name(rest, lang)} (id={rest.id})"

    cart_text, cart_total = _format_cart(session, lang)
    if session.restaurant_id:
        restaurant_list = "(مطعم مختار بالفعل)"
    else:
        restaurant_list = format_restaurant_list(
            ranked, lang=lang, page=0, page_size=max(15, len(ranked)), include_ids=True
        )

    catalog = "—"
    if session.restaurant_id:
        catalog = _menu_catalog_summary(abuu_db, session.restaurant_id, lang)

    last_search = json.dumps(ctx.get("last_food_search") or {}, ensure_ascii=False)

    return _MASTER_PROMPT.format(
        customer_name=fn,
        phone=phone,
        saved_address=addr,
        allergens=allergens,
        selected_restaurant=selected,
        cart_items=cart_text,
        cart_total=cart_total,
        conversation_history=_format_history(session, lang=lang),
        restaurant_list=restaurant_list,
        search_results=search.formatted,
        menu_catalog_summary=catalog,
        last_food_search=last_search,
        customer_message=text,
    )


def _parse_ai_response(raw: str) -> ParsedAction:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return ParsedAction(
                reply=str(parsed.get("reply") or "").strip(),
                action=str(parsed.get("action") or "none").strip() or "none",
                restaurant_id=parsed.get("restaurant_id") or None,
                item_id=parsed.get("item_id") or None,
                order_confirmed=bool(parsed.get("order_confirmed")),
            )
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return ParsedAction(
                        reply=str(parsed.get("reply") or text).strip(),
                        action=str(parsed.get("action") or "none").strip() or "none",
                        restaurant_id=parsed.get("restaurant_id") or None,
                        item_id=parsed.get("item_id") or None,
                        order_confirmed=bool(parsed.get("order_confirmed")),
                    )
            except json.JSONDecodeError:
                pass
    return ParsedAction(reply=text, action="none")


def _execute_action(
    abuu_db: Session,
    *,
    parsed: ParsedAction,
    session,
    customer: CustomerProfile,
    order: CustomerOrder | None,
    ranked: list[RankedRestaurant],
    lang: str,
    user_text: str,
) -> tuple[ParsedAction, CustomerOrder | None, str | None]:
    """Returns (parsed, order, delegate). delegate may be 'confirm'."""
    ctx = session.context or {}
    action = parsed.action

    if parsed.action == "confirm_order" and parsed.order_confirmed:
        return parsed, order, "confirm"

    if action == "select_restaurant" or parsed.restaurant_id:
        rid = str(parsed.restaurant_id or "").strip()
        if not rid:
            rid = _resolve_restaurant_pick(user_text, ctx, ranked)
            rid = rid.id if rid else ""
        if rid:
            restaurant = abuu_db.get(Restaurant, rid)
            if restaurant:
                order = _bind_restaurant(
                    abuu_db, session=session, customer=customer, order=order, restaurant=restaurant
                )
                if not parsed.reply:
                    parsed.reply = _restaurant_welcome(restaurant, lang)
                parsed.restaurant_id = restaurant.id
                parsed.action = "select_restaurant"

    if action == "show_restaurants" or (action == "show_menu" and not session.restaurant_id):
        _refresh_restaurant_index(session, ranked)
        if not parsed.reply:
            parsed.reply = format_restaurant_list(ranked, lang=lang, page=0, page_size=max(15, len(ranked)))
        parsed.action = "show_restaurants"

    if parsed.action in {"add_to_cart", "ask_addons"}:
        explicit_item_id = str(parsed.item_id or "").strip() or None
        item = abuu_db.get(RestaurantMenuItem, explicit_item_id) if explicit_item_id else None
        if item is None and explicit_item_id:
            parsed.action = "none"
            if not parsed.reply:
                parsed.reply = (
                    "ما لقيت هاد الصنف — قول اسم أو رقم من القائمة 🙏"
                    if lang == "ar"
                    else "I couldn't find that item — pick from the list 🙏"
                )
        elif item is None:
            resolved_id = _resolve_menu_pick(user_text, ctx)
            item = abuu_db.get(RestaurantMenuItem, str(resolved_id)) if resolved_id else None
        if item is not None:
            restaurant = _item_restaurant(abuu_db, item, session)
            if restaurant:
                guard = RestaurantGuard.try_add_item(
                    abuu_db,
                    customer=customer,
                    order=order,
                    context=session.context,
                    item=item,
                    restaurant=restaurant,
                    lang=lang,
                )
                if guard.ok and guard.order:
                    order = guard.order
                    session.active_order_id = order.id
                    session.restaurant_id = restaurant.id
                    session.context = bind_restaurant_context(dict(session.context or {}), restaurant.id)
                    session.context["last_added_item"] = {
                        "menu_item_id": item.id,
                        "restaurant_id": restaurant.id,
                        "name": localized_name(item, lang),
                    }
                    session.cart = _cart_from_order(abuu_db, order)
                    if not parsed.reply:
                        parsed.reply = (
                            f"تمام! {localized_name(item, lang)} انضاف 🛒"
                            if lang == "ar"
                            else f"Added {localized_name(item, lang)} 🛒"
                        )
                    parsed.action = "add_to_cart"
                elif guard.action == "cross_restaurant_blocked":
                    parsed.reply = (
                        "هاد الصنف من مطعم ثاني — كل طلب لمطعم واحد 🍽️"
                        if lang == "ar"
                        else "That item is from another restaurant."
                    )

    if parsed.action == "ask_address":
        session.stage = "confirming"

    return parsed, order, None


def _finalize_reply(
    parsed: ParsedAction,
    *,
    search: SearchBuildResult,
    lang: str,
    ranked: list[RankedRestaurant] | None = None,
) -> str:
    reply = str(parsed.reply or "").strip()
    if parsed.action in {"show_menu", "none", "show_restaurants"} and search.items and not reply:
        header = "هاي أحلى الخيارات:" if lang == "ar" else "Top picks:"
        hint = (
            "\n\nفي كمان خيارات — حدّد أكثر (مشوي، هندي، برجر) 😋"
            if lang == "ar"
            else "\n\nMore options available — be more specific 😋"
        )
        reply = f"{header}\n{search.formatted}{hint}"
    if (
        not reply
        and not search.items
        and ranked
        and parsed.action in {"show_menu", "none", "show_restaurants"}
    ):
        prefix = "المطاعم المتاحة:" if lang == "ar" else "Available restaurants:"
        reply = prefix + "\n" + format_restaurant_list(ranked, lang=lang, page=0, page_size=max(15, len(ranked)))
    if not reply:
        reply = "تمام 👌" if lang == "ar" else "OK 👌"
    return reply


class SmartPipeline:
    @staticmethod
    def handle(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        text: str,
        message_id: str | None = None,
        org_id: str | None = None,
        interpretation: InterpretationResult | None = None,
        is_voice: bool = False,
        stt_confidence: float = 0.0,
        stt_needs_clarification: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del org_id, kwargs
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        session, _state = WaiterSessionStore.load(abuu_db, phone)
        session.language = customer.preferred_language or session.language or "ar"
        lang = session.language or "ar"

        working_text = text
        if interpretation is None and is_voice:
            interpretation = WaiterInterpretation.interpret(
                abuu_db,
                main_db,
                transcript=text,
                stt_confidence=stt_confidence,
                session=session,
                customer=customer,
                lang=lang,
                is_voice=True,
                stt_needs_clarification=stt_needs_clarification,
            )
        if interpretation:
            working_text = interpretation.corrected_transcript or text
            WaiterSessionStore.apply_interpretation(session, interpretation)
            if (
                interpretation.needs_clarification
                and interpretation.clarification_prompt
                and interpretation.should_block_turn()
            ):
                ctx = session.context or {}
                if not ctx.get("voice_clarification_sent"):
                    session.context = dict(ctx)
                    session.context["voice_clarification_sent"] = True
                    save_session(abuu_db, session, message_id=message_id)
                    return {
                        "handled": True,
                        "action": "voice_clarification",
                        "reply": interpretation.clarification_prompt,
                        "reason": interpretation.clarification_reason,
                    }

        _smart_log("in", phone=phone, text=working_text[:120], voice=is_voice)
        WaiterSessionStore.append_context_message(session, role="customer", text=working_text)

        start_result = _handle_start_message(
            abuu_db,
            phone=phone,
            session=session,
            customer=customer,
            text=working_text,
            lang=lang,
        )
        if start_result is not None:
            reply = wa_customer_sanitize(str(start_result.reply or ""))
            WaiterSessionStore.append_context_message(session, role="agent", text=reply)
            session.context["session_schema_version"] = 3
            session.context["smart_pipeline"] = True
            WaiterSessionStore.save(abuu_db, session, message_id=message_id)
            _smart_log("out", phone=phone, action="started", preview=reply[:120])
            return {
                "handled": True,
                "action": "started",
                "reply": reply,
                "intent": "order_food",
                "restaurant_id": session.restaurant_id,
                "order_id": session.active_order_id,
                "step": session.stage,
            }

        voice_ctx = (session.context or {}).get("voice_interpretation") or {}
        allergy_uncertain = bool(voice_ctx.get("allergy_uncertain"))
        dietary = DietaryDetector.detect(working_text)
        if dietary.allergens_avoid and not allergy_uncertain:
            session.context["allergen_avoid"] = dietary.allergens_avoid
        if dietary.dietary_tags:
            session.context["dietary_tags"] = dietary.dietary_tags

        ranked = _ranked_restaurants(abuu_db)
        if not session.restaurant_id:
            _refresh_restaurant_index(session, ranked)

        order = _load_order(abuu_db, phone)
        if order and order.status == "draft":
            session.active_order_id = order.id
            ctx = dict(session.context or {})
            if order.restaurant_id and (ctx.get("restaurant_selected") or ctx.get("restaurant_id")):
                session.restaurant_id = order.restaurant_id
                if ctx.get("restaurant_selected"):
                    session.context["restaurant_id"] = order.restaurant_id

        deterministic = _try_deterministic(
            abuu_db,
            session=session,
            customer=customer,
            order=order,
            text=working_text,
            ranked=ranked,
            lang=lang,
        )

        search = _build_search_results(
            abuu_db, main_db, session=session, customer=customer, text=working_text, lang=lang
        )

        parsed: ParsedAction
        delegate: str | None = None

        if deterministic and deterministic.action == "select_restaurant":
            parsed = deterministic
            order = _load_order(abuu_db, phone)
        elif deterministic and deterministic.action == "add_to_cart" and deterministic.item_id:
            parsed = deterministic
            parsed, order, delegate = _execute_action(
                abuu_db,
                parsed=parsed,
                session=session,
                customer=customer,
                order=order,
                ranked=ranked,
                lang=lang,
                user_text=working_text,
            )
        else:
            prompt = _build_prompt_with_db(
                abuu_db,
                session=session,
                customer=customer,
                phone=phone,
                text=working_text,
                ranked=ranked,
                search=search,
                lang=lang,
            )
            _smart_log("prompt", phone=phone, chars=len(prompt))
            result = WaiterDeepSeekClient.complete(
                main_db,
                system_prompt=prompt,
                user_content=".",
                max_tokens=600,
                temperature=0.2,
            )
            if not result.text:
                _smart_log("parse_fail", phone=phone, raw="empty")
                parsed = ParsedAction(
                    reply=_finalize_reply(
                        ParsedAction(reply="", action="show_menu"),
                        search=search,
                        lang=lang,
                        ranked=ranked,
                    ),
                    action="show_menu" if search.items else "none",
                )
            else:
                parsed = _parse_ai_response(result.text)
                if parsed.action == "none" and not parsed.reply:
                    _smart_log("parse_fail", phone=phone, raw=result.text[:200])
            parsed, order, delegate = _execute_action(
                abuu_db,
                parsed=parsed,
                session=session,
                customer=customer,
                order=order,
                ranked=ranked,
                lang=lang,
                user_text=working_text,
            )

        if delegate == "confirm":
            WaiterSessionStore.save(abuu_db, session, message_id=message_id)
            return {"handled": True, "action": "delegate_confirm", "intent": "confirm_order"}

        reply = wa_customer_sanitize(_finalize_reply(parsed, search=search, lang=lang, ranked=ranked))
        WaiterSessionStore.append_context_message(session, role="agent", text=reply)
        session.messages.append({"role": "user", "content": working_text})
        session.messages.append({"role": "assistant", "content": reply})
        session.context["session_schema_version"] = 3
        session.context["smart_pipeline"] = True
        WaiterSessionStore.save(abuu_db, session, message_id=message_id)

        _smart_log("out", phone=phone, action=parsed.action, preview=reply[:120])
        return {
            "handled": True,
            "action": parsed.action,
            "reply": reply,
            "intent": parsed.action,
            "restaurant_id": session.restaurant_id,
            "order_id": session.active_order_id,
            "step": session.stage,
        }
