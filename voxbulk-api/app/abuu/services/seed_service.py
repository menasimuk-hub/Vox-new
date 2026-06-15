"""Seed four pilot restaurants with bilingual menus."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, insert, inspect, select
from sqlalchemy.orm import Session

from app.abuu.models.entities import Driver, Restaurant, RestaurantMenuCategory, RestaurantMenuItem


def _table_columns(db: Session, table: str) -> set[str]:
    try:
        return {c["name"] for c in inspect(db.bind).get_columns(table)}
    except Exception:
        return set()


def _insert_row(db: Session, model, values: dict) -> None:
    cols = _table_columns(db, model.__tablename__)
    filtered = {k: v for k, v in values.items() if k in cols}
    db.execute(insert(model.__table__).values(**filtered))


class AbuuSeedService:
    @staticmethod
    def seed_restaurants_if_empty(db: Session) -> int:
        existing = db.execute(select(func.count()).select_from(Restaurant)).scalar_one()
        if int(existing or 0) > 0:
            return 0
        now = datetime.utcnow()
        created = 0
        for spec in _RESTAURANT_SPECS:
            _insert_row(
                db,
                Restaurant,
                dict(
                    id=spec["id"],
                    name_en=spec["name_en"],
                    name_ar=spec["name_ar"],
                    status="active",
                    is_available=True,
                    delivery_radius_km=5.0,
                    latitude=spec["latitude"],
                    longitude=spec["longitude"],
                    address_text=spec["address_text"],
                    phone=spec["phone"],
                    login_email=spec.get("login_email"),
                    password_hash=spec.get("password_hash"),
                    created_at=now,
                    updated_at=now,
                    is_deleted=False,
                    deleted_at=None,
                ),
            )
            created += 1
            for cat_idx, cat in enumerate(spec["categories"], start=1):
                _insert_row(
                    db,
                    RestaurantMenuCategory,
                    dict(
                        id=cat["id"],
                        restaurant_id=spec["id"],
                        parent_category_id=cat.get("parent_category_id"),
                        name_en=cat["name_en"],
                        name_ar=cat["name_ar"],
                        sort_order=cat_idx * 10,
                        is_available=True,
                        created_at=now,
                        updated_at=now,
                        is_deleted=False,
                        deleted_at=None,
                    ),
                )
                for item in cat["items"]:
                    _insert_row(
                        db,
                        RestaurantMenuItem,
                        dict(
                            id=item["id"],
                            category_id=cat["id"],
                            name_en=item["name_en"],
                            name_ar=item["name_ar"],
                            description_en=item.get("description_en"),
                            description_ar=item.get("description_ar"),
                            item_type=item["item_type"],
                            price_agorot=item["price_agorot"],
                            parent_menu_item_id=item.get("parent_menu_item_id"),
                            photo_storage_key=item.get("photo_storage_key"),
                            is_available=True,
                            created_at=now,
                            updated_at=now,
                            is_deleted=False,
                            deleted_at=None,
                        ),
                    )
        db.flush()
        return created

    @staticmethod
    def seed_city_expansion(db: Session) -> dict:
        """Add restaurants up to 15 and drivers up to 4 for E2E testing."""
        from app.abuu.models.entities import Driver

        restaurant_count = int(db.execute(select(func.count()).select_from(Restaurant)).scalar_one() or 0)
        driver_count = int(db.execute(select(func.count()).select_from(Driver)).scalar_one() or 0)
        created_restaurants = 0
        created_drivers = 0
        now = datetime.utcnow()

        for spec in _EXPANSION_RESTAURANT_SPECS:
            if restaurant_count >= 15:
                break
            existing = db.get(Restaurant, spec["id"])
            if existing is not None:
                continue
            _insert_row(
                db,
                Restaurant,
                dict(
                    id=spec["id"],
                    name_en=spec["name_en"],
                    name_ar=spec["name_ar"],
                    status="active",
                    is_available=True,
                    delivery_radius_km=5.0,
                    latitude=spec["latitude"],
                    longitude=spec["longitude"],
                    address_text=spec["address_text"],
                    phone=spec["phone"],
                    created_at=now,
                    updated_at=now,
                    is_deleted=False,
                    deleted_at=None,
                ),
            )
            created_restaurants += 1
            restaurant_count += 1
            for cat_idx, cat in enumerate(spec["categories"], start=1):
                _insert_row(
                    db,
                    RestaurantMenuCategory,
                    dict(
                        id=cat["id"],
                        restaurant_id=spec["id"],
                        name_en=cat["name_en"],
                        name_ar=cat["name_ar"],
                        sort_order=cat_idx * 10,
                        is_available=True,
                        created_at=now,
                        updated_at=now,
                        is_deleted=False,
                        deleted_at=None,
                    ),
                )
                for item in cat["items"]:
                    _insert_row(
                        db,
                        RestaurantMenuItem,
                        dict(
                            id=item["id"],
                            category_id=cat["id"],
                            name_en=item["name_en"],
                            name_ar=item["name_ar"],
                            item_type=item["item_type"],
                            price_agorot=item["price_agorot"],
                            is_available=True,
                            created_at=now,
                            updated_at=now,
                            is_deleted=False,
                            deleted_at=None,
                        ),
                    )

        for spec in _DRIVER_SPECS:
            if driver_count >= 4:
                break
            existing = db.get(Driver, spec["id"])
            if existing is not None:
                continue
            _insert_row(
                db,
                Driver,
                dict(
                    id=spec["id"],
                    name=spec["name"],
                    phone=spec["phone"],
                    status="active",
                    is_available=True,
                    vehicle_info=spec.get("vehicle_info"),
                    created_at=now,
                    updated_at=now,
                    is_deleted=False,
                    deleted_at=None,
                ),
            )
            created_drivers += 1
            driver_count += 1

        db.flush()
        return {"restaurants": created_restaurants, "drivers": created_drivers}

    @staticmethod
    def seed_gaza_relocation(db: Session) -> dict:
        """Re-center seed restaurants and drivers to Gaza Strip coordinates."""
        updated_restaurants = 0
        updated_drivers = 0
        now = datetime.utcnow()

        all_specs = list(_RESTAURANT_SPECS) + list(_EXPANSION_RESTAURANT_SPECS)
        for idx, spec in enumerate(all_specs):
            row = db.get(Restaurant, spec["id"])
            if row is None:
                continue
            lat = _BASE_LAT + (idx * 0.002)
            lng = _BASE_LNG + (idx * 0.0015)
            row.latitude = lat
            row.longitude = lng
            row.address_text = f"Gaza — {spec['name_en']}"
            row.updated_at = now
            db.add(row)
            updated_restaurants += 1

        for idx, spec in enumerate(_DRIVER_SPECS):
            row = db.get(Driver, spec["id"])
            if row is None:
                continue
            row.latitude = _BASE_LAT + 0.01 + (idx * 0.001)
            row.longitude = _BASE_LNG + 0.01 + (idx * 0.001)
            row.updated_at = now
            db.add(row)
            updated_drivers += 1

        db.flush()
        return {"restaurants": updated_restaurants, "drivers": updated_drivers}

    @staticmethod
    def seed_offers_if_empty(db: Session) -> int:
        import json

        from app.abuu.models.entities import RestaurantPromoOffer

        existing = int(db.execute(select(func.count()).select_from(RestaurantPromoOffer)).scalar_one() or 0)
        if existing > 0:
            return 0
        now = datetime.utcnow()
        specs = [
            {
                "id": "abuu-offer-chicken-1",
                "restaurant_id": "abuu-rest-chicken",
                "title_en": "Sham Chicken Family Deal",
                "title_ar": "عرض عائلي دجاج الشام",
                "offer_price_agorot": 8900,
                "original_price_agorot": 11000,
                "tags": ["chicken"],
                "items": [{"menu_item_id": "abuu-item-chicken-1", "quantity": 1}, {"menu_item_id": "abuu-item-chicken-d2", "quantity": 2}],
            },
            {
                "id": "abuu-offer-fish-1",
                "restaurant_id": "abuu-rest-fish",
                "title_en": "Fresh Fish Combo",
                "title_ar": "عرض السمك الطازج",
                "offer_price_agorot": 7500,
                "original_price_agorot": 9200,
                "tags": ["fish"],
                "items": [{"menu_item_id": "abuu-item-fish-1", "quantity": 1}, {"menu_item_id": "abuu-item-fish-d1", "quantity": 1}],
            },
        ]
        created = 0
        for spec in specs:
            if db.get(Restaurant, spec["restaurant_id"]) is None:
                continue
            _insert_row(
                db,
                RestaurantPromoOffer,
                dict(
                    id=spec["id"],
                    restaurant_id=spec["restaurant_id"],
                    title_en=spec["title_en"],
                    title_ar=spec["title_ar"],
                    offer_price_agorot=spec["offer_price_agorot"],
                    original_price_agorot=spec["original_price_agorot"],
                    items_json=json.dumps(spec["items"], ensure_ascii=False),
                    tags_json=json.dumps(spec["tags"], ensure_ascii=False),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                    is_deleted=False,
                    deleted_at=None,
                ),
            )
            created += 1
        db.flush()
        return created


def _item(iid: str, en: str, ar: str, item_type: str, agorot: int, **kw) -> dict:
    return {
        "id": iid,
        "name_en": en,
        "name_ar": ar,
        "item_type": item_type,
        "price_agorot": agorot,
        **kw,
    }


_RESTAURANT_SPECS: list[dict] = [
    {
        "id": "abuu-rest-vegetarian",
        "name_en": "Al-Akhdar Vegetarian",
        "name_ar": "مطعم الأخضر",
        "latitude": 31.3540,
        "longitude": 34.3080,
        "address_text": "Gaza — vegetarian kitchen",
        "phone": "+972501000001",
        "categories": [
            {
                "id": "abuu-cat-veg-mains",
                "name_en": "Mains",
                "name_ar": "أطباق رئيسية",
                "items": [
                    _item("abuu-item-veg-1", "Grilled vegetable plate", "طبق خضار مشوي", "food", 4500),
                    _item("abuu-item-veg-2", "Falafel wrap", "ساندwich فلافل", "food", 3800),
                    _item("abuu-item-veg-3", "Lentil stew", "يخنة عدس", "food", 4200),
                    _item("abuu-item-veg-4", "Stuffed vine leaves", "ورق عنب", "food", 4000),
                ],
            },
            {
                "id": "abuu-cat-veg-drinks",
                "name_en": "Drinks",
                "name_ar": "مشروبات",
                "items": [
                    _item("abuu-item-veg-d1", "Fresh lemonade", "ليموناضة طازجة", "drink", 1200),
                    _item("abuu-item-veg-d2", "Mint tea", "شاي بالنعناع", "drink", 1000),
                    _item("abuu-item-veg-d3", "Mineral water", "ماء معدني", "drink", 800),
                ],
            },
            {
                "id": "abuu-cat-veg-salads",
                "name_en": "Salads",
                "name_ar": "سلطات",
                "items": [
                    _item("abuu-item-veg-s1", "Tabbouleh", "تبولة", "salad", 2800),
                    _item("abuu-item-veg-s2", "Fattoush", "فتوش", "salad", 3000),
                    _item("abuu-item-veg-s3", "Green salad", "سلطة خضراء", "salad", 2500),
                ],
            },
            {
                "id": "abuu-cat-veg-addons",
                "name_en": "Add-ons",
                "name_ar": "إضافات",
                "items": [
                    _item("abuu-item-veg-a1", "Extra tahini", "طحينة إضافية", "addon", 500),
                    _item("abuu-item-veg-a2", "Pita bread", "خبز pita", "addon", 400),
                ],
            },
        ],
    },
    {
        "id": "abuu-rest-fish",
        "name_en": "Al-Bahr Seafood",
        "name_ar": "مطعم البحر",
        "latitude": 31.3560,
        "longitude": 34.3100,
        "address_text": "Gaza — seafood grill",
        "phone": "+972501000002",
        "categories": [
            {
                "id": "abuu-cat-fish-mains",
                "name_en": "Mains",
                "name_ar": "أطباق رئيسية",
                "items": [
                    _item("abuu-item-fish-1", "Grilled sea bream", "سمك دنيس مشوي", "food", 6800),
                    _item("abuu-item-fish-2", "Fish fillet plate", "طبق فيليه سمك", "food", 6200),
                    _item("abuu-item-fish-3", "Shrimp skewers", "أسياخ روبيان", "food", 7200),
                    _item("abuu-item-fish-4", "Seafood rice", "أرز بحري", "food", 5800),
                ],
            },
            {
                "id": "abuu-cat-fish-drinks",
                "name_en": "Drinks",
                "name_ar": "مشروبات",
                "items": [
                    _item("abuu-item-fish-d1", "Sparkling water", "ماء فوار", "drink", 900),
                    _item("abuu-item-fish-d2", "Fresh orange juice", "عصير برتقال", "drink", 1400),
                ],
            },
            {
                "id": "abuu-cat-fish-salads",
                "name_en": "Salads",
                "name_ar": "سلطات",
                "items": [
                    _item("abuu-item-fish-s1", "Citrus fish salad", "سلطة سمك بالحمضيات", "salad", 3500),
                    _item("abuu-item-fish-s2", "Coleslaw", "سلطة ملفوف", "salad", 2200),
                ],
            },
            {
                "id": "abuu-cat-fish-addons",
                "name_en": "Add-ons",
                "name_ar": "إضافات",
                "items": [
                    _item("abuu-item-fish-a1", "Garlic sauce", "صلصة ثوم", "addon", 600),
                    _item("abuu-item-fish-a2", "Lemon wedge pack", "شرائح ليمون", "addon", 300),
                ],
            },
        ],
    },
    {
        "id": "abuu-rest-chicken",
        "name_en": "Sham Chicken",
        "name_ar": "دجاج الشام",
        "latitude": 31.3520,
        "longitude": 34.3060,
        "address_text": "Gaza — chicken grill",
        "phone": "+972501000003",
        "categories": [
            {
                "id": "abuu-cat-chicken-mains",
                "name_en": "Mains",
                "name_ar": "أطباق رئيسية",
                "items": [
                    _item("abuu-item-chicken-1", "Charcoal chicken half", "نصف دجاج على الفحم", "food", 5500),
                    _item("abuu-item-chicken-2", "Chicken shawarma plate", "طبق شاورما دجاج", "food", 4800),
                    _item("abuu-item-chicken-3", "Grilled wings", "أجنحة مشوية", "food", 4200),
                    _item("abuu-item-chicken-4", "Chicken rice bowl", "وعاء أرز بالدجاج", "food", 4600),
                ],
            },
            {
                "id": "abuu-cat-chicken-drinks",
                "name_en": "Drinks",
                "name_ar": "مشروبات",
                "items": [
                    _item("abuu-item-chicken-d1", "Ayran", "عيران", "drink", 1100),
                    _item("abuu-item-chicken-d2", "Cola", "كولا", "drink", 1000),
                ],
            },
            {
                "id": "abuu-cat-chicken-salads",
                "name_en": "Salads",
                "name_ar": "سلطات",
                "items": [
                    _item("abuu-item-chicken-s1", "Arabic salad", "سلطة عربية", "salad", 2400),
                    _item("abuu-item-chicken-s2", "Pickles plate", "طبق مخللات", "salad", 1800),
                ],
            },
            {
                "id": "abuu-cat-chicken-addons",
                "name_en": "Add-ons",
                "name_ar": "إضافات",
                "items": [
                    _item("abuu-item-chicken-a1", "Extra garlic", "ثوم إضافي", "addon", 400),
                    _item("abuu-item-chicken-a2", "Spicy sauce", "صلصة حارة", "addon", 500),
                ],
            },
        ],
    },
    {
        "id": "abuu-rest-fastfood",
        "name_en": "Wajabat Sari'a Fast Food",
        "name_ar": "وجبات سريعة",
        "latitude": 31.3580,
        "longitude": 34.3120,
        "address_text": "Gaza — fast food counter",
        "phone": "+972501000004",
        "categories": [
            {
                "id": "abuu-cat-fast-mains",
                "name_en": "Mains",
                "name_ar": "أطباق رئيسية",
                "items": [
                    _item("abuu-item-fast-1", "Classic burger meal", "وجبة برجر كلاسيك", "food", 5200),
                    _item("abuu-item-fast-2", "Crispy chicken burger", "برجر دجاج مقرمش", "food", 4900),
                    _item("abuu-item-fast-3", "Loaded fries box", "صندوق بطاطا", "food", 3200),
                    _item("abuu-item-fast-4", "Hot dog combo", "وجبة هوت دوغ", "food", 3800),
                ],
            },
            {
                "id": "abuu-cat-fast-drinks",
                "name_en": "Drinks",
                "name_ar": "مشروبات",
                "items": [
                    _item("abuu-item-fast-d1", "Soft drink", "مشروب غازي", "drink", 900),
                    _item("abuu-item-fast-d2", "Milkshake", "ميلك شيك", "drink", 2200),
                ],
            },
            {
                "id": "abuu-cat-fast-salads",
                "name_en": "Salads",
                "name_ar": "سلطات",
                "items": [
                    _item("abuu-item-fast-s1", "Side salad", "سلطة جانبية", "salad", 2000),
                ],
            },
            {
                "id": "abuu-cat-fast-addons",
                "name_en": "Add-ons",
                "name_ar": "إضافات",
                "items": [
                    _item("abuu-item-fast-a1", "Cheese slice", "شريحة جبنة", "addon", 600),
                    _item("abuu-item-fast-a2", "Extra fries", "بطاطا إضافية", "addon", 1200),
                ],
            },
        ],
    },
]

_EXPANSION_NAMES = [
    ("Abu Hassan Grill", "مشاوي أبو حسن", "meat"),
    ("Salata Fresh", "سلطة فرش", "salad"),
    ("Juice Corner", "ركن العصائر", "drinks"),
    ("Side Bites", "إضافات جانبية", "sides"),
    ("Sweet House", "بيت الحلويات", "desserts"),
    ("Kebab Express", "كباب إكسبرس", "meat"),
    ("Garden Salad Bar", "بار السلطات", "salad"),
    ("Cold Drinks Hub", "محطة المشروبات", "drinks"),
    ("Crispy Sides", "مقرمشات", "sides"),
    ("Baklava Palace", "قصر البقلاوة", "desserts"),
    ("Mixed Grill House", "بيت المشاوي", "meat"),
]

_BASE_LAT, _BASE_LNG = 31.3540, 34.3080

_EXPANSION_RESTAURANT_SPECS: list[dict] = []
for idx, (name_en, name_ar, focus) in enumerate(_EXPANSION_NAMES, start=5):
    rid = f"abuu-rest-exp-{idx:02d}"
    lat = _BASE_LAT + (idx * 0.0015)
    lng = _BASE_LNG + (idx * 0.0012)
    _EXPANSION_RESTAURANT_SPECS.append(
        {
            "id": rid,
            "name_en": name_en,
            "name_ar": name_ar,
            "latitude": lat,
            "longitude": lng,
            "address_text": f"Gaza — {name_en}",
            "phone": f"+9725010000{idx:02d}",
            "categories": [
                {
                    "id": f"{rid}-cat-main",
                    "name_en": "Main",
                    "name_ar": "رئيسي",
                    "items": [
                        _item(f"{rid}-item-1", f"{name_en} Special", f"طبق {name_ar}", focus if focus != "drinks" else "meat", 4500 + idx * 100),
                        _item(f"{rid}-item-2", f"{name_en} Combo", f"وجبة {name_ar}", "sides", 3800),
                    ],
                },
                {
                    "id": f"{rid}-cat-drinks",
                    "name_en": "Drinks",
                    "name_ar": "مشروبات",
                    "items": [_item(f"{rid}-item-d1", "Water", "ماء", "drinks", 800)],
                },
            ],
        }
    )

_DRIVER_SPECS = [
    {"id": "abuu-driver-01", "name": "Driver One", "phone": "+972508000001", "vehicle_info": "Scooter A"},
    {"id": "abuu-driver-02", "name": "Driver Two", "phone": "+972508000002", "vehicle_info": "Scooter B"},
    {"id": "abuu-driver-03", "name": "Driver Three", "phone": "+972508000003", "vehicle_info": "Car C"},
    {"id": "abuu-driver-04", "name": "Driver Four", "phone": "+972508000004", "vehicle_info": "Car D"},
]
