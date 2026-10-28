"""Featured badges: only earned ones, no duplicates, at most three; picks that
stop being earned disappear; visitors see them only with the Trail Journal."""

import uuid
from datetime import date

import pytest

from app.main import app
from app.models.trail import Trail
from app.routers.availability import get_today

TODAY = date(2026, 10, 28)
URL = "/api/me/featured-badges"


@pytest.fixture
def trails(session_factory, client):
    """Six trails in five regions; Skyline is the only overnight one."""
    db = session_factory()
    rows = {
        "skyline": Trail(name="Skyline Trail", region="Jasper National Park, AB", country_code="CA", province_code="AB",
                         terrain_difficulty="moderate", typical_duration_nights=2),
        "agnes": Trail(name="Lake Agnes", region="Banff National Park, AB", country_code="CA", province_code="AB",
                       terrain_difficulty="easy", typical_duration_nights=0),
        "sentinel": Trail(name="Sentinel Pass", region="Banff National Park, AB", country_code="CA", province_code="AB",
                          terrain_difficulty="difficult", typical_duration_nights=0),
        "garibaldi": Trail(name="Garibaldi Lake", region="Garibaldi Provincial Park, BC", country_code="CA",
                           province_code="BC", terrain_difficulty="moderate", typical_duration_nights=0),
        "wilcox": Trail(name="Wilcox Pass", region="Icefields Parkway, AB", country_code="CA", province_code="AB",
                        terrain_difficulty="easy", typical_duration_nights=0),
        "iceline": Trail(name="Iceline Trail", region="Yoho National Park, BC", country_code="CA", province_code="BC",
                         terrain_difficulty="moderate", typical_duration_nights=0),
    }
    db.add_all(rows.values())
    db.commit()
    ids = {key: str(row.id) for key, row in rows.items()}
    db.close()
    app.dependency_overrides[get_today] = lambda: TODAY
    return ids


@pytest.fixture
def people(make_token):
    def person():
        user_id = uuid.uuid4()
        return {"Authorization": f"Bearer {make_token(user_id)}"}

    return {"alice": person(), "bob": person()}


def hike(client, who, trail, day):
    assert client.put(f"/api/me/hike-logs/{trail}", json={"hiked_on": day}, headers=who).status_code == 201


def names(body):
    return [b["trail"]["name"] if b["kind"] == "trail" else b["milestone"] for b in body["badges"]]


def pick(client, who, *badges):
    return client.put(URL, json={"badges": list(badges)}, headers=who)


@pytest.fixture
def alice(client, trails, people):
    who = people["alice"]
    hike(client, who, trails["agnes"], "2026-06-10")
    hike(client, who, trails["skyline"], "2026-07-14")
    hike(client, who, trails["sentinel"], "2026-08-12")
    hike(client, who, trails["garibaldi"], "2026-09-01")
    return who


# ------------------------------------------------------------ defaults


def test_nothing_picked_shows_the_three_most_recent(client, alice):
    body = client.get(URL, headers=alice).json()
    assert body["picked"] is False
    assert names(body) == ["Garibaldi Lake", "Sentinel Pass", "Skyline Trail"]


def test_no_hikes_means_no_badges(client, trails, people):
    assert client.get(URL, headers=people["bob"]).json() == {"picked": False, "badges": []}


# ------------------------------------------------------------ picking


def test_pick_trail_and_milestone_badges_in_order(client, alice, trails):
    response = pick(client, alice, {"milestone": "first-overnight"}, {"trail_id": trails["agnes"]}, {"milestone": "first-hike"})
    assert response.status_code == 200, response.text
    assert response.json()["picked"] is True
    assert names(response.json()) == ["first-overnight", "Lake Agnes", "first-hike"]
    # Reordering is just saving a new order.
    assert names(pick(client, alice, {"trail_id": trails["agnes"]}, {"milestone": "first-overnight"}).json()) == [
        "Lake Agnes", "first-overnight"]
    assert names(client.get(URL, headers=alice).json()) == ["Lake Agnes", "first-overnight"]


def test_saving_none_goes_back_to_the_most_recent(client, alice, trails):
    pick(client, alice, {"trail_id": trails["agnes"]})
    body = pick(client, alice).json()
    assert body["picked"] is False and names(body) == ["Garibaldi Lake", "Sentinel Pass", "Skyline Trail"]


@pytest.mark.parametrize(
    "badges, message",
    [
        ([{"trail_id": "iceline"}], "earned"),  # never hiked
        ([{"trail_id": str(uuid.uuid4())}], "earned"),  # not a trail at all
        ([{"milestone": "five-parks"}], "earned"),  # 4 regions, needs 5
        ([{"milestone": "hundred-km"}], "earned"),  # no distances
        ([{"milestone": "summit-everest"}], "isn't a Trekly badge"),
        ([{"trail_id": "agnes"}, {"trail_id": "agnes"}], "once"),
        ([{"milestone": "first-hike"}, {"milestone": "first-hike"}], "once"),
        ([{"trail_id": "agnes"}, {"trail_id": "skyline"}, {"trail_id": "sentinel"}, {"trail_id": "garibaldi"}], "up to 3"),
        ([{"trail_id": "agnes", "milestone": "first-hike"}], "either"),
        ([{}], "either"),
    ],
)
def test_invalid_choices_are_refused_and_change_nothing(client, alice, trails, badges, message):
    pick(client, alice, {"milestone": "first-hike"})
    resolved = [{k: (trails.get(v, v) if k == "trail_id" else v) for k, v in badge.items()} for badge in badges]
    response = pick(client, alice, *resolved)
    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert names(client.get(URL, headers=alice).json()) == ["first-hike"]


def test_you_cant_feature_someone_elses_hike(client, alice, trails, people):
    bob = people["bob"]
    hike(client, bob, trails["wilcox"], "2026-08-01")
    assert pick(client, bob, {"trail_id": trails["agnes"]}).status_code == 422
    # And Bob's picks never touch Alice's.
    assert pick(client, bob, {"trail_id": trails["wilcox"]}).status_code == 200
    assert client.get(URL, headers=alice).json()["picked"] is False


def test_unknown_fields_are_refused(client, alice, trails):
    response = client.put(URL, json={"badges": [{"trail_id": trails["agnes"], "position": 9}]}, headers=alice)
    assert response.status_code == 422


# ------------------------------------------------------------ deleting a hike


def test_deleting_a_hike_removes_its_badge_and_any_milestone_it_earned(client, alice, trails):
    pick(client, alice, {"trail_id": trails["skyline"]}, {"milestone": "first-overnight"}, {"trail_id": trails["agnes"]})
    # Skyline was the only overnight trip, so both its badge and "Under the stars" go.
    assert client.delete(f"/api/me/hike-logs/{trails['skyline']}", headers=alice).status_code == 204
    body = client.get(URL, headers=alice).json()
    assert body["picked"] is True and names(body) == ["Lake Agnes"]
    # Logging it again doesn't bring the picks back by itself.
    hike(client, alice, trails["skyline"], "2026-07-14")
    assert names(client.get(URL, headers=alice).json()) == ["Lake Agnes"]


def test_deleting_every_picked_badge_falls_back_to_the_most_recent(client, alice, trails):
    pick(client, alice, {"trail_id": trails["agnes"]})
    client.delete(f"/api/me/hike-logs/{trails['agnes']}", headers=alice)
    body = client.get(URL, headers=alice).json()
    assert body["picked"] is False and names(body) == ["Garibaldi Lake", "Sentinel Pass", "Skyline Trail"]


# ------------------------------------------------------------ visitors


@pytest.fixture
def alice_public(client, alice):
    assert client.patch("/api/me/profile", json={"username": "alice"}, headers=alice).status_code == 200
    # Reading settings creates them with the new-user defaults (a public profile).
    assert client.get("/api/me/privacy", headers=alice).json()["show_journal"] is True
    return alice


def set_privacy(client, who, **changes):
    assert client.patch("/api/me/privacy", json=changes, headers=who).status_code == 200


def test_visitors_see_featured_badges_with_the_trail_journal(client, alice_public, trails):
    pick(client, alice_public, {"milestone": "first-overnight"}, {"trail_id": trails["agnes"]})
    body = client.get("/api/profiles/alice").json()
    assert [b.get("milestone") or b["trail"]["name"] for b in body["featured_badges"]] == ["first-overnight", "Lake Agnes"]

    set_privacy(client, alice_public, show_journal=False)
    body = client.get("/api/profiles/alice").json()
    assert body["featured_badges"] is None and body["journal"] is None

    set_privacy(client, alice_public, show_journal=True, is_private=True)
    assert client.get("/api/profiles/alice").json()["featured_badges"] is None


def test_visitor_stand_ins_dont_hint_at_dates_when_dates_are_hidden(client, alice_public):
    body = client.get("/api/profiles/alice").json()
    assert [b["trail"]["name"] for b in body["featured_badges"]] == ["Garibaldi Lake", "Sentinel Pass", "Skyline Trail"]
    set_privacy(client, alice_public, hide_hike_dates=True)
    body = client.get("/api/profiles/alice").json()
    # Alphabetical, not most recent.
    assert [b["trail"]["name"] for b in body["featured_badges"]] == ["Garibaldi Lake", "Lake Agnes", "Sentinel Pass"]


def test_visitors_never_see_a_pick_that_isnt_earned_any_more(client, alice_public, trails, session_factory):
    """Even if a stale row slipped in (say, written directly through Supabase)."""
    from app.models.featured_badge import FeaturedBadge

    pick(client, alice_public, {"trail_id": trails["agnes"]})
    db = session_factory()
    user_id = db.query(FeaturedBadge).one().user_id
    db.add(FeaturedBadge(user_id=user_id, position=1, milestone="five-parks"))
    db.commit()
    db.close()
    badges = client.get("/api/profiles/alice").json()["featured_badges"]
    assert [b.get("milestone") or b["trail"]["name"] for b in badges] == ["Lake Agnes"]
