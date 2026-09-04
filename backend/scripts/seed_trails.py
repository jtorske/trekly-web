"""Seed the trails table with sample data for local development.

Idempotent: skips any trail whose (name, region) pair already exists.
Run from backend/: python scripts/seed_trails.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.trail import Trail

TRAILS = [
    dict(name="Enchantments Traverse", region="Washington", terrain_difficulty="difficult", typical_duration_nights=2),
    dict(name="Wonderland Trail", region="Washington", terrain_difficulty="extreme", typical_duration_nights=8),
    dict(name="Zion Narrows", region="Utah", terrain_difficulty="moderate", typical_duration_nights=1),
    dict(name="Angels Landing", region="Utah", terrain_difficulty="difficult", typical_duration_nights=1),
    dict(name="Old Rag", region="Virginia", terrain_difficulty="moderate", typical_duration_nights=1),
    dict(name="Presidential Traverse", region="New Hampshire", terrain_difficulty="extreme", typical_duration_nights=1),
    dict(name="Long Trail", region="Vermont", terrain_difficulty="difficult", typical_duration_nights=14),
    dict(name="John Muir Trail (Whitney Section)", region="California", terrain_difficulty="extreme", typical_duration_nights=10),
    dict(name="Tonto Trail", region="Arizona", terrain_difficulty="difficult", typical_duration_nights=3),
    dict(name="Lost Coast Trail", region="California", terrain_difficulty="moderate", typical_duration_nights=3),
    dict(name="Timberline Trail", region="Oregon", terrain_difficulty="difficult", typical_duration_nights=3),
    dict(name="West Coast Trail", region="British Columbia", terrain_difficulty="extreme", typical_duration_nights=5),
    dict(name="Chilkoot Trail", region="Alaska", terrain_difficulty="difficult", typical_duration_nights=3),
    dict(name="Rae Lakes Loop", region="California", terrain_difficulty="moderate", typical_duration_nights=3),
    dict(name="Half Dome via Yosemite Valley", region="California", terrain_difficulty="difficult", typical_duration_nights=1),
    dict(name="Ozark Highlands Trail (Buffalo District)", region="Arkansas", terrain_difficulty="easy", typical_duration_nights=2),
    dict(name="Assateague Island Backcountry", region="Maryland", terrain_difficulty="easy", typical_duration_nights=2),
]


def seed():
    db = SessionLocal()
    try:
        existing = {(t.name, t.region) for t in db.query(Trail.name, Trail.region).all()}
        new_rows = [Trail(**row) for row in TRAILS if (row["name"], row["region"]) not in existing]
        if not new_rows:
            print("No new trails to seed; all sample trails already present.")
            return
        db.add_all(new_rows)
        db.commit()
        print(f"Seeded {len(new_rows)} trail(s).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
