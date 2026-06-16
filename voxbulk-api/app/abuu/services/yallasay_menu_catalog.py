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
    {
        "key": "mixed-grill-platter",
        "title_en": "Mixed Grill Platter",
        "title_ar": "عرض مشاوي مشكلة",
        "description_en": "Mixed grill + Arabic salad + 2 soft drinks",
        "description_ar": "مشاوي مشكلة + سلطة عربية + 2 مشروبات",
        "discount_pct": 15,
        "tags": ["meat", "food", "drinks"],
        "items": [
            {"item_key": "mixed-grill", "quantity": 1},
            {"item_key": "arabic-salad", "quantity": 1},
            {"item_key": "coca-cola", "quantity": 2},
        ],
    },
    {
        "key": "seafood-combo",
        "title_en": "Seafood Combo",
        "title_ar": "عرض السمك",
        "description_en": "Grilled fish + fries + Fanta",
        "description_ar": "سمك مشوي + بطاطا + فanta",
        "discount_pct": 14,
        "tags": ["fish", "food", "drinks"],
        "items": [
            {"item_key": "grilled-fish", "quantity": 1},
            {"item_key": "fries-regular", "quantity": 1},
            {"item_key": "fanta-orange", "quantity": 1},
        ],
    },
    {
        "key": "vegan-bowl-deal",
        "title_en": "Vegan Bowl Deal",
        "title_ar": "عرض الوعاء النباتي",
        "description_en": "Veggie bowl + fresh juice",
        "description_ar": "وعاء نباتي + عصير طازج",
        "discount_pct": 12,
        "tags": ["vegan", "food", "drinks"],
        "items": [
            {"item_key": "veggie-bowl", "quantity": 1},
            {"item_key": "orange-juice", "quantity": 1},
        ],
    },
]

YALLASAY_DRINK_CATEGORIES: list[CategorySpec] = [
    cat for cat in YALLASAY_FULL_MENU if cat["key"] in {"soft-drinks", "juices"}
]

YALLASAY_SHARED_CATEGORIES: list[CategorySpec] = [
    cat for cat in YALLASAY_FULL_MENU if cat["key"] in {"salads", "desserts", "addons"}
]

YALLASAY_PROFILE_MAINS: dict[str, list[CategorySpec]] = {
    "chicken": [
        YALLASAY_FULL_MENU[1],  # chicken
        {
            "key": "chicken-extras",
            "name_en": "Chicken Favorites",
            "name_ar": "مفضلات الدجاج",
            "items": [
                _item("crispy-chicken-burger", "Crispy chicken burger", "برجر دجاج مقرمش", "food", 4500),
                _item("nuggets-6", "Chicken nuggets (6)", "ناجتس دجاج (6)", "food", 3000),
            ],
        },
        YALLASAY_FULL_MENU[2],  # fast-snacks subset useful for chicken
    ],
    "meat": [
        {
            "key": "meat-grills",
            "name_en": "Grills & Kebab",
            "name_ar": "مشاوي وكباب",
            "items": [
                _item("mixed-grill", "Mixed grill platter", "طبق مشاوي مشكلة", "food", 7200),
                _item("kafta-plate", "Kafta plate", "طبق كفتة", "food", 5800),
                _item("kebab-skewers", "Kebab skewers (3)", "أسياخ كباب (3)", "food", 6200),
                _item("lamb-chops", "Lamb chops", "ريش غنم", "food", 7800),
                _item("shish-tawook", "Shish tawook plate", "طبق شيش طاووق", "food", 5600),
            ],
        },
        {
            "key": "meat-burgers",
            "name_en": "Burgers",
            "name_ar": "برجر",
            "items": [
                _item("classic-burger", "Classic beef burger", "برجر لحم كلاسيك", "food", 4200),
                _item("double-burger", "Double smash burger", "برجر دبل", "food", 5800),
                _item("cheese-burger", "Cheese burger", "برجر بالجبنة", "food", 4600),
            ],
        },
        YALLASAY_FULL_MENU[2],
    ],
    "fish": [
        {
            "key": "seafood-mains",
            "name_en": "Seafood Mains",
            "name_ar": "أطباق بحرية",
            "items": [
                _item("grilled-fish", "Grilled sea bream", "سمك دنيس مشوي", "food", 6800),
                _item("fish-fillet", "Fish fillet plate", "طبق فيليه سمك", "food", 6200),
                _item("shrimp-skewers", "Shrimp skewers", "أسياخ روبيان", "food", 7200),
                _item("fish-rice", "Seafood rice", "أرز بحري", "food", 5800),
                _item("fish-burger", "Fish burger", "برجر سمك", "food", 4400),
            ],
        },
        YALLASAY_FULL_MENU[2],
    ],
    "fastfood": [
        YALLASAY_FULL_MENU[0],
        YALLASAY_FULL_MENU[2],
    ],
    "vegan": [
        {
            "key": "plant-mains",
            "name_en": "Plant-Based Mains",
            "name_ar": "أطباق نباتية",
            "items": [
                _item("veggie-bowl", "Grilled vegetable bowl", "وعاء خضار مشوي", "food", 4500),
                _item("falafel-wrap", "Falafel wrap", "ساندwich فلافل", "food", 3800),
                _item("lentil-stew", "Lentil stew", "يخنة عدس", "food", 4200),
                _item("veggie-burger", "Veggie burger", "برجر نباتي", "food", 4000),
                _item("stuffed-vine", "Stuffed vine leaves", "ورق عنب", "food", 4000),
            ],
        },
        YALLASAY_FULL_MENU[5],  # salads
    ],
}

YALLASAY_PILOT_RESTAURANTS: dict[str, str] = {
    "abuu-rest-chicken": "chicken",
    "abuu-rest-meat": "meat",
    "abuu-rest-fish": "fish",
    "abuu-rest-fastfood": "fastfood",
    "abuu-rest-vegetarian": "vegan",
}

YALLASAY_PILOT_RESTAURANT_IDS: tuple[str, ...] = tuple(YALLASAY_PILOT_RESTAURANTS.keys())

YALLASAY_OFFERS_BY_PROFILE: dict[str, list[str]] = {
    "chicken": ["shawarma-duo", "wings-feast", "lunch-combo", "drinks-six-pack"],
    "meat": ["mixed-grill-platter", "family-burger", "drinks-six-pack"],
    "fish": ["seafood-combo", "drinks-six-pack"],
    "fastfood": ["family-burger", "lunch-combo", "drinks-six-pack"],
    "vegan": ["vegan-bowl-deal", "drinks-six-pack"],
}

_OFFER_BY_KEY = {spec["key"]: spec for spec in YALLASAY_OFFER_TEMPLATES}


def menu_for_profile(profile: str) -> list[CategorySpec]:
    mains = YALLASAY_PROFILE_MAINS.get(profile) or YALLASAY_PROFILE_MAINS["fastfood"]
    shared = list(YALLASAY_SHARED_CATEGORIES)
    if profile == "vegan":
        shared = [cat for cat in shared if cat["key"] != "addons"] + [
            {
                "key": "addons",
                "name_en": "Add-ons",
                "name_ar": "إضافات",
                "items": [
                    _item("extra-sauce", "Extra sauce", "صلصة إضافية", "addon", 400),
                    _item("pita-bread", "Pita bread", "خبز pita", "addon", 400),
                ],
            }
        ]
    return list(mains) + list(YALLASAY_DRINK_CATEGORIES) + shared


def offers_for_profile(profile: str) -> list[OfferSpec]:
    keys = YALLASAY_OFFERS_BY_PROFILE.get(profile) or YALLASAY_OFFERS_BY_PROFILE["fastfood"]
    return [_OFFER_BY_KEY[key] for key in keys if key in _OFFER_BY_KEY]


def profile_for_restaurant(restaurant_id: str) -> str:
    return YALLASAY_PILOT_RESTAURANTS.get(restaurant_id, "fastfood")
