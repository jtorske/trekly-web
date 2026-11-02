"""Trail Journal milestones: every rule, its edge cases, the config, and what
the API sends (secret milestones stay hidden until earned)."""

import json
import re
import uuid
from datetime import date
from pathlib import Path

import jwt
import pytest

from app.milestones import (
    RULES, Facts, Hike, check, earned_ids, evaluate, gather, goal_of, milestone_out, setup_base_weight_kg,
)
from app.milestones_config import ACTIVE, BY_ID, CATEGORIES, CORE_SLOT_CATEGORIES, MILESTONES, TIER_POINTS
from app.models.catalog import CatalogCategory
from app.models.setup import GearSetup, GearSetupItem
from app.models.trail import Trail
from app.models.user_gear import UserGearItem
from tests.test_featured_badges import URL as FEATURED_URL
from tests.test_featured_badges import alice, hike, people, pick, trails  # noqa: F401  (fixtures)


def trail(name="t", region="Banff National Park, AB", province="AB", country="CA", terrain="easy", nights=0,
          km=None, gain=None, top=None, park=None, tags=None, id=None):  # noqa: A002
    return Trail(id=id or uuid.uuid4(), name=name, region=region, province_code=province, country_code=country,
                 terrain_difficulty=terrain, typical_duration_nights=nights, distance_km=km, elevation_gain_m=gain,
                 max_elevation_m=top, park_name=park, tags=tags)


def on(day: str, t: Trail | None = None, **hike) -> Hike:
    return Hike(t or trail(), date.fromisoformat(day), **hike)


def facts(*trails_or_hikes, **more) -> Facts:
    hikes = [h if isinstance(h, Hike) else Hike(h) for h in trails_or_hikes]
    return Facts(hikes=hikes, **more)


def earned(milestone_id: str, f: Facts) -> bool:
    return check(next(m for m in MILESTONES if m.id == milestone_id), f).earned


def progress(milestone_id: str, f: Facts) -> tuple:
    result = check(BY_ID[milestone_id], f)
    return result.current, result.goal


# ------------------------------------------------------------ the config


def test_config_is_well_formed():
    ids = [m.id for m in MILESTONES]
    assert len(ids) == len(set(ids))
    categories = {key for key, _ in CATEGORIES}
    for m in MILESTONES:
        assert m.category in categories, m.id
        assert m.tier in TIER_POINTS, m.id
        assert m.rule in RULES, m.id
        assert re.fullmatch(r"[a-z0-9-]{1,40}", m.id), m.id
        # "{goal}" is the only placeholder, and it always has a number behind it.
        assert set(re.findall(r"\{(\w+)\}", m.detail)) <= {"goal"}, m.id
        if "{goal}" in m.detail:
            assert goal_of(m) is not None, m.id
    assert all(m.secret for m in MILESTONES if m.category == "secret")


def test_the_original_four_keep_their_ids():
    # Featured picks on hosted refer to these.
    assert {"first-hike", "first-overnight", "five-parks", "hundred-km"} <= set(BY_ID)


def test_old_friend_waits_for_repeat_hikes():
    assert {m.id for m in MILESTONES if not m.enabled} == {"old-friend"}
    assert "old-friend" not in BY_ID
    # Even when its rule would pass, it's never earned or scored.
    same = trail()
    f = facts(same, same)
    assert earned("old-friend", f)
    assert "old-friend" not in earned_ids(f)


def test_every_icon_is_drawn_in_the_frontend():
    badge_ts = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "badge.ts"
    if not badge_ts.exists():
        pytest.skip("frontend not checked out next to the backend")
    drawn = set(re.findall(r'^\s*"?([a-z0-9-]+)"?:\s*"M', badge_ts.read_text(encoding="utf-8"), re.M))
    assert {m.icon for m in MILESTONES} | {"secret"} <= drawn


def test_nothing_done_earns_nothing():
    assert earned_ids(Facts()) == set()


# ------------------------------------------------------------ getting out there


@pytest.mark.parametrize("milestone_id, goal", [("first-hike", 1), ("trail-regular", 10), ("trail-devotee", 25),
                                                ("trailblazer", 50)])
def test_hike_counts(milestone_id, goal):
    assert not earned(milestone_id, facts(*[trail() for _ in range(goal - 1)]))
    assert earned(milestone_id, facts(*[trail() for _ in range(goal)]))
    if goal > 1:
        assert progress(milestone_id, facts(trail(), trail())) == (2, goal)


def test_old_friend_needs_the_same_trail_twice():
    a, b = trail(), trail()
    assert not earned("old-friend", facts(a, b))
    assert earned("old-friend", facts(a, b, a))


# ------------------------------------------------------------ nights out


def test_overnight_trips_by_length():
    assert not earned("first-overnight", facts(trail(nights=0)))
    assert earned("first-overnight", facts(trail(nights=1)))
    assert not earned("long-weekend", facts(trail(nights=2), trail(nights=2)))  # one trip, not a total
    assert earned("long-weekend", facts(trail(nights=3)))
    assert not earned("week-in-the-wild", facts(trail(nights=5)))
    assert earned("week-in-the-wild", facts(trail(nights=6)))


def test_missing_nights_count_as_day_hikes():
    assert not earned("first-overnight", facts(trail(nights=None)))


def test_backcountry_regular_totals_nights():
    assert progress("backcountry-regular", facts(trail(nights=3), trail(nights=4))) == (7, 10)
    assert earned("backcountry-regular", facts(trail(nights=3), trail(nights=4), trail(nights=3)))


# ------------------------------------------------------------ distance


@pytest.mark.parametrize("milestone_id, goal", [("hundred-km", 100), ("long-hauler", 250), ("thousand-km", 1000)])
def test_distance_goals(milestone_id, goal):
    assert not earned(milestone_id, facts(trail(km=goal - 0.1)))
    assert earned(milestone_id, facts(trail(km=goal / 2), trail(km=goal / 2)))


def test_trails_missing_a_distance_add_nothing():
    f = facts(trail(km=6), trail(km=None), trail(km=None))
    assert progress("hundred-km", f) == (6, 100)
    assert check(BY_ID["hundred-km"], f).unit == "km"
    assert not earned("hundred-km", facts(*[trail(km=None) for _ in range(50)]))


# ------------------------------------------------------------ elevation


def test_vertical_kilometre_is_one_hike():
    assert not earned("vertical-km", facts(trail(gain=600), trail(gain=600)))
    assert earned("vertical-km", facts(trail(gain=1000)))


def test_sky_high_needs_a_high_point_of_2500():
    assert not earned("sky-high", facts(trail(top=2499)))
    assert earned("sky-high", facts(trail(top=2500)))
    assert not earned("sky-high", facts(trail(top=None, gain=3000)))


def test_everest_club_totals_known_gain_only():
    f = facts(*[trail(gain=1000) for _ in range(8)], trail(gain=None))
    assert progress("everest-club", f) == (8000, 8849)
    assert check(BY_ID["everest-club"], f).unit == "m"
    assert earned("everest-club", facts(*[trail(gain=1000) for _ in range(8)], trail(gain=849)))


# ------------------------------------------------------------ exploration


def test_park_hopper_counts_regions():
    four = [trail(region=f"Park {i}") for i in range(4)]
    assert not earned("five-parks", facts(*four, trail(region="Park 0")))
    assert earned("five-parks", facts(*four, trail(region="Park 9")))


def test_grand_slam_needs_all_five_mountain_parks():
    parks = ["Banff National Park", "Jasper National Park", "Yoho National Park", "Kootenay National Park"]
    four = [trail(park=p) for p in parks]
    assert progress("grand-slam", facts(*four, trail(park="Kananaskis Country"))) == (4, 5)
    assert earned("grand-slam", facts(*four, trail(park="Waterton Lakes National Park")))


def test_provincial_passport_counts_canadian_provinces_and_territories():
    codes = ["BC", "AB", "ON", "YT"]
    four = [trail(province=c) for c in codes]
    assert not earned("provincial-passport", facts(*four, trail(country="US", province="WA")))
    assert not earned("provincial-passport", facts(*four, trail(province=None)))
    assert earned("provincial-passport", facts(*four, trail(province="NS")))


def test_true_north_is_any_territory():
    assert not earned("true-north", facts(trail(province="BC"), trail(province="AB")))
    for code in ("YT", "NT", "NU"):
        assert earned("true-north", facts(trail(province=code)))


def test_coast_to_coast_needs_bc_and_an_atlantic_province():
    assert not earned("coast-to-coast", facts(trail(province="BC"), trail(province="QC")))
    assert progress("coast-to-coast", facts(trail(province="NL"))) == (1, 2)
    for atlantic in ("NB", "NS", "PE", "NL"):
        assert earned("coast-to-coast", facts(trail(province="BC"), trail(province=atlantic)))


def test_park_completionist_needs_every_active_trail_in_a_park_of_three_or_more():
    banff = [trail(region="Banff") for _ in range(3)]
    tiny = trail(region="Tiny")
    regions = {"Banff": {t.id for t in banff}, "Tiny": {tiny.id}}
    # A one-trail region doesn't count.
    assert not earned("park-completionist", facts(tiny, region_trails=regions))
    partial = check(BY_ID["park-completionist"], facts(*banff[:2], tiny, region_trails=regions))
    assert (partial.earned, partial.current, partial.goal, partial.near) == (False, 2, 3, "Banff")
    assert earned("park-completionist", facts(*banff, region_trails=regions))
    # A retired trail is no longer in the park's set, so it isn't needed.
    retired = trail(region="Banff")
    assert earned("park-completionist", facts(*banff, region_trails=regions))
    assert retired.id not in regions["Banff"]


# ------------------------------------------------------------ difficulty


def test_full_spectrum_needs_one_of_each():
    three = [trail(terrain=t) for t in ("easy", "moderate", "difficult")]
    assert progress("full-spectrum", facts(*three, trail(terrain="easy"))) == (3, 4)
    assert earned("full-spectrum", facts(*three, trail(terrain="extreme")))


def test_grinder_and_extreme():
    assert progress("grinder", facts(*[trail(terrain="difficult") for _ in range(4)])) == (4, 5)
    assert earned("grinder", facts(*[trail(terrain="difficult") for _ in range(5)]))
    assert not earned("grinder", facts(*[trail(terrain="extreme") for _ in range(5)]))
    assert not earned("extreme", facts(trail(terrain="difficult")))
    assert earned("extreme", facts(trail(terrain="extreme")))


# ------------------------------------------------------------ seasons


def test_larch_madness_window_and_tag():
    larch = trail(tags=["larch"])
    assert earned("larch-madness", facts(on("2026-09-15", larch)))
    assert earned("larch-madness", facts(on("2025-10-10", larch)))
    assert not earned("larch-madness", facts(on("2026-09-14", larch)))
    assert not earned("larch-madness", facts(on("2026-10-11", larch)))
    # The right dates on an untagged trail, or no tags at all.
    assert not earned("larch-madness", facts(on("2026-09-20", trail(tags=["lakes"]))))
    assert not earned("larch-madness", facts(on("2026-09-20", trail(tags=None))))


def test_larch_trip_that_runs_into_the_window():
    larch_trip = trail(tags=["larch"], nights=2)
    assert earned("larch-madness", facts(on("2026-09-13", larch_trip)))
    assert not earned("larch-madness", facts(on("2026-09-12", larch_trip)))


def test_winter_warrior_december_to_february():
    assert earned("winter-warrior", facts(on("2026-12-01")))
    assert earned("winter-warrior", facts(on("2027-02-28")))
    assert not earned("winter-warrior", facts(on("2026-03-01")))
    assert not earned("winter-warrior", facts(on("2026-11-30")))


def test_a_trip_crossing_into_winter_counts():
    two_nights = trail(nights=2)
    assert earned("winter-warrior", facts(on("2026-11-29", two_nights)))
    assert not earned("winter-warrior", facts(on("2026-11-28", two_nights)))


def test_four_seasons():
    three = facts(on("2026-01-10"), on("2026-04-10"), on("2026-07-10"))
    assert progress("four-seasons", three) == (3, 4)
    assert earned("four-seasons", facts(on("2026-01-10"), on("2026-04-10"), on("2026-07-10"), on("2026-10-10")))


def test_a_trip_across_a_season_change_counts_for_both():
    # Feb 27 + 3 nights reaches March 2: winter and spring.
    f = facts(on("2026-02-27", trail(nights=3)), on("2026-07-10"), on("2026-10-10"))
    assert earned("four-seasons", f)


def test_monthly_regular_needs_three_months_in_a_row():
    assert progress("monthly-regular", facts(on("2026-05-01"), on("2026-06-30"), on("2026-08-01"))) == (2, 3)
    assert earned("monthly-regular", facts(on("2026-05-01"), on("2026-06-30"), on("2026-07-01")))
    # Across the new year.
    assert earned("monthly-regular", facts(on("2025-11-20"), on("2025-12-20"), on("2026-01-20")))
    # The same month in different years is not a run.
    assert not earned("monthly-regular", facts(on("2025-06-01"), on("2026-07-01"), on("2027-08-01")))
    # A trip from late June into July fills two of them.
    assert earned("monthly-regular", facts(on("2026-06-29", trail(nights=3)), on("2026-08-05")))


def test_undated_hikes_earn_no_seasons():
    assert not earned("winter-warrior", facts(trail(tags=["larch"])))
    assert not earned("monthly-regular", facts(trail(), trail(), trail()))


# ------------------------------------------------------------ journal


def test_storyteller_and_shutterbug():
    notes = [Hike(trail(), note=True) for _ in range(4)]
    assert progress("storyteller", facts(*notes, Hike(trail(), photo=True))) == (4, 5)
    assert earned("storyteller", facts(*notes, Hike(trail(), note=True)))
    photos = [Hike(trail(), photo=True) for _ in range(5)]
    assert earned("shutterbug", facts(*photos))
    assert not earned("shutterbug", facts(*photos[:4], *notes))


# ------------------------------------------------------------ planning and gear


def test_planning_milestones():
    assert not earned("planner", Facts()) and earned("planner", Facts(plans=1))
    assert not earned("permit-hunter", Facts()) and earned("permit-hunter", Facts(alerts=1))
    assert not earned("lucky-break", Facts(alerts=3)) and earned("lucky-break", Facts(alert_notified=True))


def test_packed_and_ready_needs_all_seven_core_slots_in_one_setup():
    every = {categories[-1] for categories in CORE_SLOT_CATEGORIES.values()}
    assert earned("packed-and-ready", Facts(setups=[every]))
    six = every - {"stoves"}
    assert progress("packed-and-ready", Facts(setups=[six, {"stoves"}])) == (6, 7)
    assert not earned("packed-and-ready", Facts(setups=[six | {"cookware", "pillows"}]))
    assert progress("packed-and-ready", Facts(setups=[set()])) == (0, 7)


def test_ultralight_rule():
    assert not earned("ultralight", Facts(base_weights_kg=[9.0, 12]))
    assert earned("ultralight", Facts(base_weights_kg=[8.9]))
    assert "ultralight" in earned_ids(Facts(base_weights_kg=[8.9]))


def gear(slug, grams=None, quantity=1, carry=None):
    return UserGearItem(custom_name=slug, category=CatalogCategory(slug=slug), weight_override_g=grams,
                        quantity=quantity, carry=carry)


def test_base_weight_counts_packed_items_like_the_gear_page():
    # Boots are worn by default; fuel marked consumable; the rest packed, times quantity.
    items = [gear("backpacks", 1000), gear("tents", 1200), gear("stakes-guylines", 15, quantity=8),
             gear("hiking-boots", 1400), gear("fuel-accessories", 230, carry="consumable")]
    assert setup_base_weight_kg(items) == pytest.approx(2.32)
    # Boots the owner packs (camp shoes, say) do count.
    assert setup_base_weight_kg([*items[:1], gear("trail-runners", 600, carry="packed")]) == pytest.approx(1.6)
    # A packed item with no weight leaves the base weight unknown; a worn one doesn't matter.
    assert setup_base_weight_kg([*items, gear("pillows")]) is None
    assert setup_base_weight_kg([*items, gear("rainwear", carry="worn")]) == pytest.approx(2.32)


def test_ultralight_needs_a_full_setup(session_factory):
    db = session_factory()
    user = uuid.uuid4()
    core = {key: categories[0] for key, categories in CORE_SLOT_CATEGORIES.items()}

    def setup(name, slugs, grams):
        kit = GearSetup(user_id=user, name=name)
        for position, slug in enumerate(slugs):
            category = db.query(CatalogCategory).filter_by(slug=slug).one_or_none() or CatalogCategory(
                slug=slug, name=slug, icon_key="generic")
            item = UserGearItem(user_id=user, custom_name=slug, category=category, weight_override_g=grams, quantity=1)
            kit.entries.append(GearSetupItem(gear_item=item, position=position))
        db.add(kit)
        db.commit()

    # Two items weighing almost nothing: not a full setup, so no Ultralight.
    setup("Day pack", ["backpacks", "stoves"], 100)
    f = gather(db, user)
    assert f.base_weights_kg == [] and not check(BY_ID["ultralight"], f).earned
    # All 7 main slots at 1 kg each, boots worn: 6 kg base.
    setup("Full kit", list(core.values()), 1000)
    f = gather(db, user)
    assert f.base_weights_kg == [pytest.approx(6.0)]
    assert check(BY_ID["ultralight"], f).earned and check(BY_ID["packed-and-ready"], f).earned
    db.close()


# ------------------------------------------------------------ secret


def test_secret_trails_by_name_and_province():
    assert earned("stairmaster", facts(trail(name="Grouse Grind", province="BC")))
    assert earned("coastal-legend", facts(trail(name="West Coast Trail", province="BC")))
    assert earned("skyline", facts(trail(name="Skyline Trail", province="AB")))
    # Cape Breton's Skyline Trail is a different trail.
    assert not earned("skyline", facts(trail(name="Skyline Trail", province="NS")))


def test_an_unearned_secret_sends_only_its_hint():
    [(secret, result)] = [(m, r) for m, r in evaluate(Facts()) if m.id == "coastal-legend"]
    out = milestone_out(secret, result).model_dump()
    assert out == {"id": None, "category": "secret", "title": "???", "detail": secret.hint, "goal": None,
                   "unit": None, "tier": None, "icon": "secret", "secret": True, "earned": False, "progress": None}


# ------------------------------------------------------------ the API


def test_my_milestones(client, alice):  # noqa: F811
    body = client.get("/api/me/milestones", headers=alice).json()
    assert [c["id"] for c in body["categories"]] == [key for key, _ in CATEGORIES]
    assert body["tier_points"] == TIER_POINTS
    assert len(body["milestones"]) == len(ACTIVE)
    by_id = {m["id"]: m for m in body["milestones"] if m["id"]}
    assert by_id["first-hike"]["earned"] and by_id["first-hike"]["progress"] is None
    assert by_id["trail-regular"]["progress"] == {"current": 4, "goal": 10, "unit": None, "near": None}
    # Zero progress shows no arc.
    assert by_id["hundred-km"]["progress"] is None and by_id["hundred-km"]["unit"] == "km"
    assert by_id["hundred-km"]["goal"] == 100 and by_id["hundred-km"]["detail"] == "Hike {goal} in total"
    # Alice hiked Jasper's Skyline Trail: that secret is revealed, the others aren't.
    assert by_id["skyline"]["earned"] and by_id["skyline"]["title"] == "Skyline"
    hidden = [m for m in body["milestones"] if m["category"] == "secret" and not m["earned"]]
    assert len(hidden) == 2 and all(m["id"] is None and m["title"] == "???" for m in hidden)
    text = json.dumps(body)
    for leak in ("stairmaster", "Stairmaster", "Grouse Grind", "coastal-legend", "Coastal legend", "West Coast"):
        assert leak not in text


def test_milestones_need_signing_in(client):
    assert client.get("/api/me/milestones").status_code == 401


def test_a_trip_plan_earns_planner(client, session_factory, people, trails):  # noqa: F811
    from app.models.trip_plan import TripPlan

    bob = people["bob"]
    token = bob["Authorization"].split()[1]
    bob_id = uuid.UUID(jwt.decode(token, options={"verify_signature": False})["sub"])
    db = session_factory()
    db.add(TripPlan(user_id=bob_id, trail_id=uuid.UUID(trails["skyline"]), start_date=date(2027, 7, 1), nights=2,
                    party_size=2))
    db.commit()
    db.close()
    by_id = {m["id"]: m for m in client.get("/api/me/milestones", headers=bob).json()["milestones"] if m["id"]}
    assert by_id["planner"]["earned"] and not by_id["permit-hunter"]["earned"]
    assert client.get("/api/me/rank", headers=bob).json()["breakdown"]["milestones"] == 10


def test_any_earned_milestone_can_be_featured(client, alice):  # noqa: F811
    assert pick(client, alice, {"milestone": "skyline"}, {"milestone": "monthly-regular"}).status_code == 200
    body = client.get(FEATURED_URL, headers=alice).json()
    assert [b["milestone"] for b in body["badges"]] == ["skyline", "monthly-regular"]
    assert body["badges"][0]["badge"] == {"id": "skyline", "category": "secret", "title": "Skyline",
                                          "tier": "silver", "icon": "ridge"}


@pytest.mark.parametrize("milestone, message", [
    ("stairmaster", "earned"),
    ("old-friend", "isn't a Trekly badge"),
    ("no-such-badge", "isn't a Trekly badge"),
])
def test_unearned_disabled_and_unknown_milestones_cant_be_featured(client, alice, milestone, message):  # noqa: F811
    response = pick(client, alice, {"milestone": milestone})
    assert response.status_code == 422 and message in response.json()["detail"]


# ------------------------------------------------------------ visitors


@pytest.fixture
def alice_public(client, alice):  # noqa: F811
    assert client.patch("/api/me/profile", json={"username": "alice"}, headers=alice).status_code == 200
    assert client.get("/api/me/privacy", headers=alice).status_code == 200
    return alice


def test_visitors_see_earned_milestones_with_the_journal(client, alice_public):
    milestones = client.get("/api/profiles/alice").json()["journal"]["milestones"]
    assert [m["id"] for m in milestones] == ["first-hike", "first-overnight", "monthly-regular", "skyline"]
    assert milestones[0] == {"id": "first-hike", "category": "getting-out", "title": "First steps",
                             "tier": "bronze", "icon": "first-hike"}


def test_hidden_dates_hide_seasonal_milestones(client, alice_public):
    assert client.patch("/api/me/privacy", json={"hide_hike_dates": True}, headers=alice_public).status_code == 200
    milestones = client.get("/api/profiles/alice").json()["journal"]["milestones"]
    assert "monthly-regular" not in [m["id"] for m in milestones]


def test_a_hidden_journal_sends_no_milestones(client, alice_public):
    assert client.patch("/api/me/privacy", json={"show_journal": False}, headers=alice_public).status_code == 200
    body = client.get("/api/profiles/alice").json()
    assert body["journal"] is None
    assert "First steps" not in json.dumps(body)
