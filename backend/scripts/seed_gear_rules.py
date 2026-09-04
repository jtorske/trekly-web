"""Seeds the baseline 'essentials' gear category + rules, a couple of
region-gated example rules (bear spray, wind/rain-specific gear), and
backfills climate_zone on trails that don't have one set yet.

Idempotent: skips gear_items that already exist by name, and rules that
already exist for a given gear item (matched by gear_item_id + condition
fingerprint isn't tracked, so re-running skips purely by item existing).

Run from backend/: python scripts/seed_gear_rules.py
"""

import os
import sys
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import SessionLocal

# Baseline safety/utility items included on every trip regardless of
# temperature or terrain (condition_min_nights = 0 => always applies).
ESSENTIALS = [
    dict(name="Headlamp", is_shareable=False, weight_g=85),
    dict(name="First aid kit", is_shareable=True, weight_g=250),
    dict(name="Map & compass", is_shareable=True, weight_g=100),
    dict(name="Emergency shelter", is_shareable=False, weight_g=150),
    dict(name="Fire starter", is_shareable=True, weight_g=30),
    dict(name="Repair kit", is_shareable=True, weight_g=60),
    dict(name="Sunscreen", is_shareable=True, weight_g=100),
    dict(name="Lip balm", is_shareable=False, weight_g=15),
    dict(name="Toilet paper", is_shareable=False, weight_g=50),
    dict(name="Hand sanitizer", is_shareable=False, weight_g=30),
    dict(name="Trash bags", is_shareable=False, weight_g=20),
    dict(name="Power bank & charging cable", is_shareable=False, weight_g=200),
]

# Region/condition-specific items — NOT included everywhere. Each is gated
# so it only shows up where it's actually applicable.
REGION_SPECIFIC = [
    dict(
        item=dict(name="Bear spray", category="safety", is_shareable=True, weight_g=350),
        rule=dict(condition_climate_zone="alpine", quantity_per_person=0.5),
    ),
    dict(
        item=dict(name="Reinforced tent stakes", category="shelter", is_shareable=True, weight_g=120),
        rule=dict(condition_requires_high_wind=True, quantity_per_person=1),
    ),
    dict(
        item=dict(name="Waterproof pack liner", category="clothing", is_shareable=False, weight_g=40),
        rule=dict(condition_requires_high_precip=True, quantity_per_person=1),
    ),
]

# Trails seeded earlier without a climate_zone — inferred from their real
# geography so the new climate-aware fallback has something to branch on.
CLIMATE_ZONE_BACKFILL = {
    "Enchantments Traverse": "alpine",
    "Wonderland Trail": "alpine",
    "Zion Narrows": "desert",
    "Angels Landing": "desert",
    "Old Rag": "temperate",
    "Presidential Traverse": "alpine",
    "Long Trail": "temperate",
    "John Muir Trail (Whitney Section)": "alpine",
    "Tonto Trail": "desert",
    "Lost Coast Trail": "coastal_temperate",
    "Timberline Trail": "alpine",
    "West Coast Trail": "coastal_temperate",
    "Chilkoot Trail": "alpine",
    "Rae Lakes Loop": "alpine",
    "Half Dome via Yosemite Valley": "alpine",
    "Ozark Highlands Trail (Buffalo District)": "temperate",
    "Assateague Island Backcountry": "coastal_temperate",
}


def seed():
    db = SessionLocal()
    try:
        existing_names = {
            row[0] for row in db.execute(text("select name from gear_items")).fetchall()
        }

        essentials_added = 0
        for item in ESSENTIALS:
            if item["name"] in existing_names:
                continue
            item_id = str(uuid.uuid4())
            db.execute(
                text(
                    "insert into gear_items (id, name, category, is_shareable, weight_g) "
                    "values (:id, :name, 'essentials', :is_shareable, :weight_g)"
                ),
                {"id": item_id, **item},
            )
            db.execute(
                text(
                    "insert into gear_rules (id, gear_item_id, condition_min_nights, quantity_per_person) "
                    "values (:id, :gear_item_id, 0, 1)"
                ),
                {"id": str(uuid.uuid4()), "gear_item_id": item_id},
            )
            existing_names.add(item["name"])
            essentials_added += 1

        region_added = 0
        for entry in REGION_SPECIFIC:
            item = entry["item"]
            if item["name"] in existing_names:
                continue
            item_id = str(uuid.uuid4())
            db.execute(
                text(
                    "insert into gear_items (id, name, category, is_shareable, weight_g) "
                    "values (:id, :name, :category, :is_shareable, :weight_g)"
                ),
                {"id": item_id, **item},
            )
            rule = entry["rule"]
            db.execute(
                text(
                    "insert into gear_rules "
                    "(id, gear_item_id, condition_min_nights, quantity_per_person, "
                    "condition_climate_zone, condition_requires_high_wind, condition_requires_high_precip) "
                    "values (:id, :gear_item_id, 0, :quantity_per_person, "
                    ":condition_climate_zone, :condition_requires_high_wind, :condition_requires_high_precip)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "gear_item_id": item_id,
                    "quantity_per_person": rule.get("quantity_per_person", 1),
                    "condition_climate_zone": rule.get("condition_climate_zone"),
                    "condition_requires_high_wind": rule.get("condition_requires_high_wind"),
                    "condition_requires_high_precip": rule.get("condition_requires_high_precip"),
                },
            )
            existing_names.add(item["name"])
            region_added += 1

        zone_updates = 0
        for name, zone in CLIMATE_ZONE_BACKFILL.items():
            result = db.execute(
                text(
                    "update trails set climate_zone = :zone "
                    "where name = :name and climate_zone is null"
                ),
                {"zone": zone, "name": name},
            )
            zone_updates += result.rowcount

        db.commit()
        print(f"Essentials added: {essentials_added}")
        print(f"Region-specific items added: {region_added}")
        print(f"Trail climate_zone backfilled: {zone_updates}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
