from datetime import datetime, timezone

import pytest

from app.models.trail import Trail
from app.trail_slugs import assign_slugs, slugify
from tests.test_trails import catalog, entry
from app.trail_catalog import sync_trails


def test_slugify_reads_like_the_name():
    assert slugify("Lake Agnes Tea House") == "lake-agnes-tea-house"
    assert slugify("Sentier de l'Acropole des Draveurs") == "sentier-de-lacropole-des-draveurs"
    assert slugify("Plain of Six Glaciers & Big Beehive") == "plain-of-six-glaciers-and-big-beehive"
    assert slugify("Cap-Trinité  (Les Caps)") == "cap-trinite-les-caps"
    assert slugify("") == ""


def test_namesakes_both_get_their_park():
    slugs = assign_slugs([
        (1, "Skyline Trail", "Jasper National Park", "AB", True),
        (2, "Skyline Trail", "Cape Breton Highlands National Park", "NS", True),
        (3, "Lake Agnes Tea House", "Banff National Park", "AB", True),
    ])
    assert slugs == {
        1: "skyline-trail-jasper-national-park",
        2: "skyline-trail-cape-breton-highlands-national-park",
        3: "lake-agnes-tea-house",
    }


def test_same_name_and_park_falls_back_to_province_then_a_number():
    slugs = assign_slugs([
        (1, "Ridge Trail", None, "AB", True),
        (2, "Ridge Trail", None, "AB", True),
        (3, "Ridge Trail", "Some Park", "BC", True),
    ])
    assert slugs[1] == "ridge-trail-ab"
    assert slugs[2] == "ridge-trail-ab-2"
    assert slugs[3] == "ridge-trail-some-park"
    assert len(set(slugs.values())) == 3


def test_a_retired_namesake_leaves_the_live_trail_its_short_slug():
    slugs = assign_slugs([
        (1, "Chilkoot Trail", "Chilkoot Trail National Historic Site", "BC", True),
        (2, "Chilkoot Trail", None, "AK", False),
    ])
    assert slugs == {1: "chilkoot-trail", 2: "chilkoot-trail-ak"}
    # Park names that repeat the trail's add only the rest.
    both_live = assign_slugs([
        (1, "Chilkoot Trail", "Chilkoot Trail National Historic Site", "BC", True),
        (2, "Chilkoot Trail", None, "AK", True),
    ])
    assert both_live[1] == "chilkoot-trail-national-historic-site"


def test_new_trails_get_a_slug_and_existing_ones_never_change(session_factory):
    db = session_factory()
    first = Trail(name="Skyline Trail", region="Jasper", country_code="CA", province_code="AB",
                  park_name="Jasper National Park", terrain_difficulty="moderate")
    db.add(first)
    db.commit()
    assert first.slug == "skyline-trail"

    second = Trail(name="Skyline Trail", region="Cape Breton", country_code="CA", province_code="NS",
                   park_name="Cape Breton Highlands National Park", terrain_difficulty="easy")
    db.add(second)
    db.commit()
    db.refresh(first)
    assert first.slug == "skyline-trail"
    assert second.slug == "skyline-trail-cape-breton-highlands-national-park"


@pytest.fixture
def lake_agnes(session_factory):
    db = session_factory()
    trail = Trail(name="Lake Agnes Tea House", region="Banff National Park, AB", country_code="CA",
                  province_code="AB", park_name="Banff National Park", park_type="national",
                  terrain_difficulty="easy", description="A classic climb to a tea house.",
                  popularity_rank=1, latitude=51.4167, longitude=-116.2167)
    db.add(trail)
    db.commit()
    return trail.id


def test_trail_by_slug(client, lake_agnes):
    response = client.get("/api/trails/by-slug/lake-agnes-tea-house")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(lake_agnes)
    assert body["slug"] == "lake-agnes-tea-house"
    assert body["description"] == "A classic climb to a tea house."
    # Old-style lookups still return the slug, so the page can redirect.
    assert client.get(f"/api/trails/{lake_agnes}").json()["slug"] == "lake-agnes-tea-house"
    assert client.get("/api/trails/by-slug/LAKE-AGNES-TEA-HOUSE").status_code == 200
    assert client.get("/api/trails/by-slug/no-such-trail").status_code == 404


def test_sitemap_lists_live_trails_only(client, session_factory, lake_agnes):
    db = session_factory()
    retired = Trail(name="Old Trail", region="AB", country_code="CA", province_code="AB",
                    terrain_difficulty="easy", retired_at=datetime.now(timezone.utc))
    db.add(retired)
    db.commit()
    rows = client.get("/api/trails/sitemap").json()
    assert [row["slug"] for row in rows] == ["lake-agnes-tea-house"]
    assert rows[0]["updated_at"] is not None


def test_catalogue_sync_gives_every_trail_a_unique_slug(session_factory):
    db = session_factory()
    sync_trails(db, catalog([entry(1, "Skyline Trail", province="AB"), entry(2, "Skyline Trail", province="NS"),
                             entry(3)]), countries=("CA",), limit=10)
    db.commit()
    slugs = [t.slug for t in db.query(Trail).order_by(Trail.popularity_rank)]
    assert slugs[0] == "skyline-trail" and slugs[1].startswith("skyline-trail-")
    assert len(set(slugs)) == 3
