"""Bilingual Yallasay fast-food menu catalog (categories, items, offer templates)."""

from __future__ import annotations

from typing import Any

MenuItemSpec = dict[str, Any]
CategorySpec = dict[str, Any]
OfferSpec = dict[str, Any]


def _item(
    key: str,
    en: str,
    ar: str,
    item_type: str,
    agorot: int,
    *,
    description_en: str | None = None,
    description_ar: str | None = None,
) -> MenuItemSpec:
    return {
        "key": key,
        "name_en": en,
        "name_ar": ar,
        "item_type": item_type,
        "price_agorot": agorot,
        "description_en": description_en,
        "description_ar": description_ar,
    }


YALLASAY_FULL_MENU: list[CategorySpec] = [
    {
        "key": "burgers",
        "name_en": "Burgers & Meals",
        "name_ar": "برجر ووجبات",
        "items": [
            _item("classic-burger", "Classic beef burger", "برجر لحم كلاسيك", "food", 4200),
            _item("cheese-burger", "Cheese burger", "برجر بالجبنة", "food", 4600),
            _item("double-burger", "Double smash burger", "برجر دبل", "food", 5800),
            _item("crispy-chicken-burger", "Crispy chicken burger", "برجر دجاج مقرمش", "food", 4500),
            _item("spicy-chicken-burger", "Spicy chicken burger", "برجر دجاج حار", "food", 4700),
            _item("fish-burger", "Fish burger", "برجر سمك", "food", 4400),
            _item("veggie-burger", "Veggie burger", "برجر نباتي", "food", 4000),
            _item("combo-burger-meal", "Burger combo meal", "وجبة برجر كاملة", "food", 6200,
                  description_en="Burger + fries + soft drink", description_ar="برجر + بطاطا + مشروب"),
        ],
    },
    {
        "key": "chicken",
        "name_en": "Chicken & Grills",
        "name_ar": "دجاج ومشاوي",
        "items": [
            _item("charcoal-half", "Charcoal chicken half", "نصف دجاج على الفحم", "food", 5500),
            _item("charcoal-quarter", "Charcoal chicken quarter", "ربع دجاج على الفحم", "food", 3200),
            _item("shawarma-plate", "Chicken shawarma plate", "طبق شاورما دجاج", "food", 4800),
            _item("shawarma-wrap", "Shawarma wrap", "ساندwich شاورما", "food", 3500),
            _item("grilled-wings", "Grilled wings (6 pcs)", "أجنحة مشوية (6)", "food", 4200),
            _item("crispy-strips", "Crispy strips (5 pcs)", "ستrips مقرمش (5)", "food", 3900),
            _item("chicken-rice", "Chicken rice bowl", "أرز بالدجاج", "food", 4600),
        ],
    },
    {
        "key": "fast-snacks",
        "name_en": "Fast Snacks",
        "name_ar": "وجبات سريعة",
        "items": [
            _item("loaded-fries", "Loaded fries box", "صندوق بطاطا محشية", "food", 3200),
            _item("fries-regular", "French fries", "بطاطا مقلية", "sides", 1800),
            _item("fries-large", "Large fries", "بطاطا كبيرة", "sides", 2400),
            _item("onion-rings", "Onion rings", "حلقات بصل", "sides", 2200),
            _item("mozzarella-sticks", "Mozzarella sticks", "أصابع موزاريلا", "sides", 2600),
            _item("hot-dog", "Hot dog", "هوت دوغ", "food", 2800),
            _item("hot-dog-combo", "Hot dog combo", "وجبة هوت دوغ", "food", 3800),
            _item("nuggets-6", "Chicken nuggets (6)", "ناجتس دجاج (6)", "food", 3000),
            _item("nuggets-9", "Chicken nuggets (9)", "ناجتس دجاج (9)", "food", 3900),
        ],
    },
    {
        "key": "soft-drinks",
        "name_en": "Soft Drinks",
        "name_ar": "مشروبات غازية",
        "items": [
            _item("coca-cola", "Coca-Cola", "كوكا كولا", "drink", 1000),
            _item("coca-cola-zero", "Coca-Cola Zero", "كوكا كولا زيرو", "drink", 1000),
            _item("pepsi", "Pepsi", "بيبسي", "drink", 1000),
            _item("7up", "7UP", "سفن أب", "drink", 1000),
            _item("fanta-orange", "Fanta Orange", "فانتا برتقال", "drink", 1000),
            _item("sprite", "Sprite", "سبرايت", "drink", 1000),
            _item("mirinda", "Mirinda", "ميرندا", "drink", 1000),
            _item("mountain-dew", "Mountain Dew", "Mountain Dew", "drink", 1100),
            _item("mineral-water", "Mineral water", "ماء معدني", "drink", 800),
            _item("sparkling-water", "Sparkling water", "ماء فوار", "drink", 900),
        ],
    },
    {
        "key": "juices",
        "name_en": "Juices & Shakes",
        "name_ar": "عصائر وميلك شيك",
        "items": [
            _item("orange-juice", "Fresh orange juice", "عصير برتقال طازج", "drink", 1400),
            _item("lemon-mint", "Lemon mint", "ليمون بالنعناع", "drink", 1200),
            _item("mango-juice", "Mango juice", "عصير مانجو", "drink", 1500),
            _item("avocado-juice", "Avocado juice", "عصير أفوكado", "drink", 1600),
            _item("chocolate-shake", "Chocolate milkshake", "ميلك شيك شوكolate", "drink", 2200),
            _item("vanilla-shake", "Vanilla milkshake", "ميلك شيك فانيلا", "drink", 2200),
            _item("strawberry-shake", "Strawberry milkshake", "ميلk شيك فراولة", "drink", 2200),
            _item("ayran", "Ayran", "عيران", "drink", 1100),
        ],
    },
    {
        "key": "salads",
        "name_en": "Salads",
        "name_ar": "سلطات",
        "items": [
            _item("arabic-salad", "Arabic salad", "سلطة عربية", "salad", 2400),
            _item("fattoush", "Fattoush", "فتوش", "salad", 2800),
            _item("tabbouleh", "Tabbouleh", "تبولة", "salad", 2600),
            _item("coleslaw", "Coleslaw", "سلطة ملفوف", "salad", 2000),
            _item("caesar-salad", "Caesar salad", "سلطة سيزر", "salad", 3200),
        ],
    },
    {
        "key": "desserts",
        "name_en": "Desserts",
        "name_ar": "حلويات",
        "items": [
            _item("chocolate-cake", "Chocolate cake slice", "قطعة كيك شوكolata", "desserts", 2500),
            _item("cheesecake", "Cheesecake slice", "قطعة تشيز كيك", "desserts", 2800),
            _item("kunafa-portion", "Kunafa portion", "ح portion كنافة", "desserts", 3000),
            _item("ice-cream-cup", "Ice cream cup", "كوب آيس كريم", "desserts", 1800),
            _item("brownie", "Warm brownie", "براوني ساخن", "desserts", 2200),
        ],
    },
    {
        "key": "addons",
        "name_en": "Add-ons",
        "name_ar": "إضافات",
        "items": [
            _item("extra-cheese", "Extra cheese", "جبنة إضافية", "addon", 600),
            _item("extra-sauce", "Extra sauce", "صلصة إضافية", "addon", 400),
            _item("garlic-sauce", "Garlic sauce", "صلصة ثوم", "addon", 500),
            _item("spicy-sauce", "Spicy sauce", "صلصة حارة", "addon", 500),
            _item("pita-bread", "Pita bread", "خبز pita", "addon", 400),
        ],
    },
]

YALLASAY_OFFER_TEMPLATES: list[OfferSpec] = [
    {
        "key": "family-burger",
        "title_en": "Family Burger Deal",
        "title_ar": "عرض البرجر العائلي",
        "description_en": "2 classic burgers + large fries + 2 Coca-Cola",
        "description_ar": "2 برجر كلاسيك + بطاطا كبيرة + 2 كوكا كولا",
        "discount_pct": 18,
        "tags": ["food", "drinks", "chicken"],
        "items": [
            {"item_key": "classic-burger", "quantity": 2},
            {"item_key": "fries-large", "quantity": 1},
            {"item_key": "coca-cola", "quantity": 2},
        ],
    },
    {
        "key": "lunch-combo",
        "title_en": "Lunch Combo — 20% off",
        "title_ar": "وجبة الغداء — خصم 20٪",
        "description_en": "Crispy chicken burger + fries + any soft drink",
        "description_ar": "برجر دجاج مقرمش + بطاطa + مشروب غازي",
        "discount_pct": 20,
        "tags": ["food", "drinks"],
        "items": [
            {"item_key": "crispy-chicken-burger", "quantity": 1},
            {"item_key": "fries-regular", "quantity": 1},
            {"item_key": "7up", "quantity": 1},
        ],
    },
    {
        "key": "shawarma-duo",
        "title_en": "Shawarma Duo Deal",
        "title_ar": "عرض الشاورما الثنائي",
        "description_en": "2 shawarma wraps + 2 Fanta",
        "description_ar": "2 ساندwich شاورما + 2 فanta",
        "discount_pct": 15,
        "tags": ["chicken", "drinks"],
        "items": [
            {"item_key": "shawarma-wrap", "quantity": 2},
            {"item_key": "fanta-orange", "quantity": 2},
        ],
    },
    {
        "key": "drinks-six-pack",
        "title_en": "Soft Drink 6-Pack",
        "title_ar": "عرض 6 مشروبات غازية",
        "description_en": "Mix any 6 soft drinks — save 12%",
        "description_ar": "اختر 6 مشروبات غازية — وفر 12٪",
        "discount_pct": 12,
        "tags": ["drinks"],
        "items": [
            {"item_key": "coca-cola", "quantity": 2},
            {"item_key": "sprite", "quantity": 2},
            {"item_key": "fanta-orange", "quantity": 2},
        ],
    },
    {
        "key": "wings-feast",
        "title_en": "Wings Feast",
        "title_ar": "وليمة الأجنحة",
        "description_en": "Grilled wings + large fries + Pepsi",
        "description_ar": "أجنحة مشوية + بطاطا كبيرة + بيبسي",
        "discount_pct": 16,
        "tags": ["chicken", "food"],
        "items": [
            {"item_key": "grilled-wings", "quantity": 1},
            {"item_key": "fries-large", "quantity": 1},
            {"item_key": "pepsi", "quantity": 1},
        ],
    },
]
