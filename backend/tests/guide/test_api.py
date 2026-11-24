"""Trekly Guide's HTTP API: profile, recommend, readiness, settings, time on trail."""

import uuid
from datetime import date

import pytest

from app.main import app
from app.models.hike_log import HikeLog
from app.models.preferences import ProfilePreferences
from app.models.trail import Trail
from app.routers.availability import get_today
from tests.guide.conftest import seed_catalogue

TODAY = date(2027, 7, 6)  # a Tuesday; this weekend is 2027-07-10


@pytest.fixture
def world(client, session_factory):
    app.dependency_overrides[get_today] = lambda: TODAY
    db = session_factory()
    seed_catalogue(db)
    trails = {t.slug: t for t in db.query(Trail).all()}
    db.commit()  # one shared SQLite connection: don't hold a transaction open
    yield db, trails
    db.close()


@pytest.fixture
def alice(auth_headers):
    user_id = uuid.uuid4()
    return user_id, auth_headers(user_id)


def log(db, user_id, trail, on=None, minutes=None):
    db.add(HikeLog(user_id=user_id, trail_id=trail.id, hiked_on=on, duration_minutes=minutes))
    db.commit()
    db.close()


def test_guest_recommendations_default_to_this_weekend(client, world):
    response = client.post("/api/guide/recommend", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date"] == "2027-07-10" and body["winter"] is False and body["basis"] == "stated"
    assert len(body["results"]) == 3
    first = body["results"][0]
    assert first["trail"]["slug"] and first["reasons"] and first["est_label"]


def test_recommend_uses_history_and_excludes_hiked(client, world, alice):
    db, trails = world
    user_id, headers = alice
    for slug in ("ha-ling-peak", "prairie-mountain", "sulphur-skyline"):
        log(db, user_id, trails[slug], date(2026, 7, 1), 200)
    body = client.post("/api/guide/recommend", json={"difficulty": "push"}, headers=headers).json()
    assert body["basis"] == "history"
    slugs = {r["trail"]["slug"] for r in body["results"]}
    assert slugs and not slugs & {"ha-ling-peak", "prairie-mountain", "sulphur-skyline"}


def test_dog_notes(client, world):
    body = client.post("/api/guide/recommend", json={"dog": True, "limit": 6}).json()
    assert body["results"] and all(r["dog_policy"] != "not_allowed" and r["dog_note"] for r in body["results"])
    assert all(r["dog_note"] is None for r in client.post("/api/guide/recommend", json={}).json()["results"])


def test_show_me_more(client, world):
    first = client.post("/api/guide/recommend", json={}).json()["results"]
    ids = [r["trail"]["id"] for r in first]
    more = client.post("/api/guide/recommend", json={"exclude_ids": ids}).json()["results"]
    assert more and not {r["trail"]["id"] for r in more} & set(ids)


def test_winter_snowshoe_avoid_defaults_on(client, world):
    body = client.post("/api/guide/recommend", json={"date": "2028-01-15", "activity": "snowshoe"}).json()
    assert body["winter"] is True and body["avoid_avalanche"] is True
    assert body["results"]
    assert all(r["avalanche_exposure"] in ("none", "simple") for r in body["results"])
    assert all(any("https://avalanche.ca" in reason for reason in r["reasons"]) for r in body["results"])


@pytest.mark.parametrize("payload", [
    {"difficulty": "extreme"}, {"province": "XX"}, {"regions": ["atlantis"]}, {"date": "tomorrow"},
    {"date": "2020-01-01"}, {"limit": 50}, {"surprise": True}, {"activity": "ski_touring"},
])
def test_recommend_validates(client, world, payload):
    assert client.post("/api/guide/recommend", json=payload).status_code == 422


def test_readiness_needs_sign_in(client, world):
    assert client.get("/api/guide/readiness/ha-ling-peak").status_code == 401


def test_readiness_verdicts(client, world, alice):
    db, trails = world
    user_id, headers = alice
    for slug in ("grassi-lakes", "tunnel-mountain", "lake-agnes-tea-house"):
        log(db, user_id, trails[slug], date(2026, 6, 1), 120)
    ready = client.get("/api/guide/readiness/grassi-lakes", headers=headers).json()
    assert ready["verdict"] == "ready" and ready["label"] == "Ready" and ready["build_up"] == []
    far = client.get("/api/guide/readiness/sentinel-pass-via-larch-valley", headers=headers).json()
    assert far["verdict"] == "not_yet" and far["label"] == "Not yet"
    assert far["est_label"] and 1 <= len(far["build_up"]) <= 2
    assert all(b["slug"] not in ("grassi-lakes", "tunnel-mountain", "lake-agnes-tea-house") for b in far["build_up"])
    winter = client.get("/api/guide/readiness/wilcox-pass?date=2028-01-15", headers=headers).json()
    assert winter["verdict"] == "not_yet" and winter["avalanche_link"] == "https://avalanche.ca"


def test_readiness_gentle_without_history(client, world, alice):
    _, headers = alice
    body = client.get("/api/guide/readiness/panorama-ridge", headers=headers).json()
    assert body["gentle"] is True
    assert any("Log a few past hikes" in r["text"] for r in body["reasons"])


def test_readiness_unknown_trail(client, world, alice):
    assert client.get("/api/guide/readiness/nowhere", headers=alice[1]).status_code == 404


def test_profile_is_owner_only_and_reports_pace(client, world, alice):
    db, trails = world
    user_id, headers = alice
    assert client.get("/api/guide/profile").status_code == 401
    for slug in ("ha-ling-peak", "prairie-mountain", "sulphur-skyline"):
        log(db, user_id, trails[slug], date(2026, 7, 1), 250)
    body = client.get("/api/guide/profile", headers=headers).json()
    assert body["experience"]["hike_count"] == 3 and body["experience"]["basis"] == "history"
    assert body["pace"]["confidence"] == "medium" and body["pace"]["factor"] > 1
    assert len(body["hiked_trail_ids"]) == 3 and body["preferences"]["use_history"] is True


def test_settings_toggle_turns_history_off(client, world, alice):
    db, trails = world
    user_id, headers = alice
    assert client.get("/api/me/guide-settings", headers=headers).json() == {
        "use_history": True, "hikes_with_dog": False, "scenery": []}
    for slug in ("ha-ling-peak", "prairie-mountain"):
        log(db, user_id, trails[slug], date(2026, 7, 1))
    response = client.patch("/api/me/guide-settings", json={"use_history": False, "scenery": ["lakes", "lakes"]},
                            headers=headers)
    assert response.status_code == 200 and response.json()["scenery"] == ["lakes"]
    profile = client.get("/api/guide/profile", headers=headers).json()
    assert profile["experience"]["basis"] == "stated" and profile["hiked_trail_ids"] == []
    # Hiked trails are no longer filtered out: history is ignored.
    body = client.post("/api/guide/recommend", json={"include_hiked": False, "limit": 6}, headers=headers).json()
    assert body["basis"] == "stated"
    readiness = client.get("/api/guide/readiness/ha-ling-peak", headers=headers).json()
    assert readiness["gentle"] is True
    assert any("Use my history" in r["text"] for r in readiness["reasons"])


def test_settings_validate(client, world, alice):
    for payload in ({"scenery": ["volcanoes"]}, {"use_history": "maybe"}, {"other": 1}):
        assert client.patch("/api/me/guide-settings", json=payload, headers=alice[1]).status_code == 422


def test_settings_creates_preferences_row(client, world, alice, session_factory):
    user_id, headers = alice
    client.patch("/api/me/guide-settings", json={"hikes_with_dog": True}, headers=headers)
    with session_factory() as db:
        row = db.get(ProfilePreferences, user_id)
        assert row.hikes_with_dog is True and row.guide_use_history is True


def test_planner_experience_answer_counts_without_history(client, world, alice):
    _, headers = alice
    new = client.post("/api/guide/recommend", json={"experience": "new", "limit": 6}, headers=headers).json()
    assert all(r["trail"]["terrain"] in ("easy", "moderate") for r in new["results"])


def test_time_on_trail_is_saved_and_owner_only(client, world, alice):
    db, trails = world
    user_id, headers = alice
    trail = trails["ha-ling-peak"]
    response = client.put(f"/api/me/hike-logs/{trail.id}",
                          json={"hiked_on": "2027-07-01", "duration_minutes": 215}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["duration_minutes"] == 215
    listed = client.get("/api/me/hike-logs", headers=headers).json()
    assert listed[0]["duration_minutes"] == 215
    # An edit that leaves it out (e.g. from the Activity composer) keeps it; null clears it.
    edited = client.put(f"/api/me/hike-logs/{trail.id}", json={"hiked_on": "2027-07-01", "note": "Windy"},
                        headers=headers)
    assert edited.json()["duration_minutes"] == 215
    cleared = client.put(f"/api/me/hike-logs/{trail.id}", json={"hiked_on": "2027-07-01", "duration_minutes": None},
                         headers=headers)
    assert cleared.json()["duration_minutes"] is None
    for bad in (5, 30000):
        assert client.put(f"/api/me/hike-logs/{trail.id}", json={"hiked_on": "2027-07-01", "duration_minutes": bad},
                          headers=headers).status_code == 422
