"""Public profiles through the API: what visitors (guests and other signed-in
users) can and can't see, privacy settings, reports and admin hiding.

Private fields are filled with CANARY strings, and every GET route in the
app is swept as a guest and as another user to prove none of them leaks.
Row-level security for direct Supabase access is tested separately against
the local stack (test_profile_privacy_policies.py).
"""

import json
import re
import uuid
from datetime import date

import pytest

from app.main import app
from app.models.availability import AvailabilityAlert
from app.models.trip_plan import TripPlan
from app.notify import Email
from app.routers.public_profiles import get_email_sender
from tests.test_availability import TODAY, fetch, world  # noqa: F401  (fixtures)

ALICE_EMAIL = "alice-canary@example.com"
CANARIES = [
    ALICE_EMAIL,
    "CANARY-HOME-REGION",
    "CANARY-GEAR-NOTE",
    "CANARY-PLAN-NOTE",
    "canary-alert@example.com",
]
PUBLIC_DEFAULTS = {
    "is_private": False,
    "show_journal": True,
    "show_rank": True,
    "show_gear": True,
    "show_saved_trails": True,
    "show_trip_plans": False,
    "hide_hike_dates": False,
    "allow_search_indexing": False,
}


class Outbox:
    def __init__(self, fail=False):
        self.sent: list[Email] = []
        self.fail = fail

    def send(self, email: Email) -> None:
        if self.fail:
            raise RuntimeError("mail server down")
        self.sent.append(email)


@pytest.fixture
def outbox():
    box = Outbox()
    app.dependency_overrides[get_email_sender] = lambda: box
    return box


@pytest.fixture
def people(make_token):
    def person(email):
        user_id = uuid.uuid4()
        return user_id, {"Authorization": f"Bearer {make_token(user_id, email=email)}"}

    return {"alice": person(ALICE_EMAIL), "bob": person("bob@example.com")}


@pytest.fixture
def alice_profile(client, world, fetch, people, session_factory):  # noqa: F811
    """Alice with something in every section, and CANARY strings in every private field."""
    alice_id, alice = people["alice"]
    trail = str(world["trail"])
    assert client.patch(
        "/api/me/profile",
        json={"username": "alice", "display_name": "Alice A", "bio": "Hiker.", "home_region": "CANARY-HOME-REGION"},
        headers=alice,
    ).status_code == 200
    assert client.get("/api/me/privacy", headers=alice).json()["is_private"] is False  # new-user defaults

    photo = f"{alice_id}/{uuid.uuid4()}.webp"
    assert client.put(f"/api/me/hike-logs/{trail}", json={"hiked_on": "2026-08-14", "note": "Larches!", "photo_path": photo},
                      headers=alice).status_code == 201
    gear_photo = f"{alice_id}/{uuid.uuid4()}.webp"
    item = client.post("/api/me/gear", json={"custom_name": "Old stove", "category": "stoves", "notes": "CANARY-GEAR-NOTE",
                                             "image_path": gear_photo}, headers=alice).json()
    assert client.post("/api/me/setups", json={"name": "Skyline kit", "item_ids": [item["id"]]}, headers=alice).status_code == 201
    assert client.put(f"/api/me/saved-trails/{trail}", headers=alice).status_code == 201

    db = session_factory()
    plan = TripPlan(user_id=alice_id, trail_id=world["trail"], title="Skyline in fall", start_date=date(2026, 11, 2),
                    nights=2, party_size=3, notes="CANARY-PLAN-NOTE")
    db.add(plan)
    db.add(AvailabilityAlert(user_id=alice_id, email="canary-alert@example.com", site_id=world["shovel"],
                             start_date=date(2026, 11, 2), nights=1, party_size=2, status="active"))
    db.commit()
    ids = {"plan": str(plan.id), "item": item["id"], "trail": trail, "photo": photo, "gear_photo": gear_photo}
    db.close()
    return ids


def public(client, username="alice", headers=None):
    return client.get(f"/api/profiles/{username}", headers=headers or {})


def set_privacy(client, headers, **changes):
    response = client.patch("/api/me/privacy", json=changes, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def assert_no_canaries(text, where):
    for canary in CANARIES:
        assert canary not in text, f"{canary} leaked from {where}"


# ------------------------------------------------------------ what shows


def test_new_users_get_the_public_defaults(client, people):
    _, alice = people["alice"]
    settings = client.get("/api/me/privacy", headers=alice).json()
    assert {key: settings[key] for key in PUBLIC_DEFAULTS} == PUBLIC_DEFAULTS
    assert settings["public_notice_pending"] is False


def test_public_profile_shows_the_default_sections_only(client, alice_profile):
    response = public(client)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["username"] == "alice" and body["display_name"] == "Alice A" and body["bio"] == "Hiker."
    assert body["is_private"] is False
    assert body["allow_indexing"] is False
    assert body["rank"] == {"level": 2, "title": "Day Tripper"}
    [entry] = body["journal"]["entries"]
    assert entry["hiked_on"] == "2026-08-14" and entry["note"] == "Larches!" and entry["photo_path"] == alice_profile["photo"]
    assert [item["display_name"] for item in body["gear"]["items"]] == ["Old stove"]
    assert [setup["name"] for setup in body["gear"]["setups"]] == ["Skyline kit"]
    assert [trail["name"] for trail in body["saved_trails"]] == ["Skyline Trail"]
    assert body["trip_plans"] is None  # private by default


def test_public_payload_has_only_declared_fields(client, alice_profile, people):
    _, alice = people["alice"]
    set_privacy(client, alice, show_trip_plans=True)
    body = public(client).json()
    assert set(body) == {"username", "display_name", "avatar_path", "is_private", "allow_indexing", "bio", "rank",
                         "journal", "featured_badges", "gear", "saved_trails", "trip_plans"}
    assert set(body["featured_badges"][0]) == {"kind", "trail", "milestone"}
    assert set(body["gear"]["items"][0]) == {"id", "kind", "display_name", "brand_name", "category", "product", "variant",
                                            "custom_brand", "custom_model", "quantity", "weight", "capacity"}
    assert set(body["trip_plans"][0]) == {"id", "trail", "title", "start_date", "nights"}
    assert_no_canaries(json.dumps(body), "the public profile")
    for forbidden in ("email", "home_region", "notes", "party_size", "alerts", "itinerary", "condition"):
        assert f'"{forbidden}"' not in json.dumps(body)


def test_gear_photos_stay_with_the_owner(client, alice_profile, people):
    """Users' own gear photos are never public, so they never need moderating."""
    _, alice = people["alice"]
    [own] = client.get("/api/me/gear", headers=alice).json()["items"]
    assert own["image_path"] == alice_profile["gear_photo"]
    for headers in ({}, people["bob"][1], alice):
        body = json.dumps(public(client, headers=headers).json())
        assert alice_profile["gear_photo"] not in body
        assert '"image_path"' not in body


def test_signed_in_visitors_see_exactly_what_guests_see(client, alice_profile, people):
    _, bob = people["bob"]
    assert public(client, headers=bob).json() == public(client).json()


def test_owner_gets_the_visitor_view_too(client, alice_profile, people):
    _, alice = people["alice"]
    assert public(client, headers=alice).json() == public(client).json()


@pytest.mark.parametrize(
    "setting, section",
    [("show_journal", "journal"), ("show_rank", "rank"), ("show_gear", "gear"), ("show_saved_trails", "saved_trails")],
)
def test_each_section_can_be_hidden(client, alice_profile, people, setting, section):
    _, alice = people["alice"]
    assert public(client).json()[section] is not None
    set_privacy(client, alice, **{setting: False})
    # Takes effect on the very next request.
    assert public(client).json()[section] is None
    set_privacy(client, alice, **{setting: True})
    assert public(client).json()[section] is not None


def test_trip_plans_show_only_when_switched_on(client, alice_profile, people):
    _, alice = people["alice"]
    set_privacy(client, alice, show_trip_plans=True)
    [plan] = public(client).json()["trip_plans"]
    assert plan == {"id": alice_profile["plan"], "trail": plan["trail"], "title": "Skyline in fall",
                    "start_date": "2026-11-02", "nights": 2}
    set_privacy(client, alice, show_trip_plans=False)
    assert public(client).json()["trip_plans"] is None


def test_private_profile_shows_only_name_and_photo(client, alice_profile, people):
    _, alice = people["alice"]
    set_privacy(client, alice, is_private=True, allow_search_indexing=True)
    body = public(client).json()
    assert body == {"username": "alice", "display_name": "Alice A", "avatar_path": None, "is_private": True,
                    "allow_indexing": False, "bio": None, "rank": None, "journal": None,
                    "featured_badges": None, "gear": None, "saved_trails": None, "trip_plans": None}
    set_privacy(client, alice, is_private=False)
    assert public(client).json()["bio"] == "Hiker."


def test_hidden_dates_are_removed_not_just_hidden(client, alice_profile, people):
    _, alice = people["alice"]
    set_privacy(client, alice, hide_hike_dates=True)
    journal = public(client).json()["journal"]
    assert journal["hide_dates"] is True
    assert journal["entries"][0]["hiked_on"] is None
    assert "2026-08-14" not in json.dumps(public(client).json())
    # The owner's own journal still has the date.
    assert client.get("/api/me/hike-logs", headers=alice).json()[0]["hiked_on"] == "2026-08-14"


def test_search_indexing_is_opt_in(client, alice_profile, people):
    _, alice = people["alice"]
    assert public(client).json()["allow_indexing"] is False
    set_privacy(client, alice, allow_search_indexing=True)
    assert public(client).json()["allow_indexing"] is True


def test_profiles_without_a_username_have_no_public_page(client, people):
    _, bob = people["bob"]
    client.get("/api/me/profile", headers=bob)
    assert client.get("/api/me/profile", headers=bob).json()["visibility"] == "private"
    assert public(client, "bob").status_code == 404


def test_usernames_are_case_insensitive_in_urls(client, alice_profile):
    assert public(client, "ALICE").status_code == 200
    assert public(client, "nobody_here").status_code == 404


def test_reserved_usernames_are_refused(client, people):
    _, bob = people["bob"]
    response = client.patch("/api/me/profile", json={"username": "admin"}, headers=bob)
    assert response.status_code == 422
    assert "reserved" in response.text


def test_owner_profile_reports_its_visibility(client, alice_profile, people):
    _, alice = people["alice"]
    assert client.get("/api/me/profile", headers=alice).json()["visibility"] == "public"
    set_privacy(client, alice, is_private=True)
    assert client.get("/api/me/profile", headers=alice).json()["visibility"] == "private"


def test_existing_users_notice_can_only_be_dismissed(client, alice_profile, people, session_factory):
    alice_id, alice = people["alice"]
    from app.models.privacy import ProfileSettings

    db = session_factory()
    db.get(ProfileSettings, alice_id).public_notice_pending = True
    db.commit()
    db.close()
    assert set_privacy(client, alice, public_notice_pending=False)["public_notice_pending"] is False
    db = session_factory()
    db.get(ProfileSettings, alice_id).public_notice_pending = True
    db.commit()
    db.close()
    # Changing any setting also counts as having seen it.
    assert set_privacy(client, alice, is_private=False)["public_notice_pending"] is False
    assert client.patch("/api/me/privacy", json={"public_notice_pending": True}, headers=alice).status_code == 422


def test_privacy_settings_are_only_your_own(client, alice_profile, people):
    _, bob = people["bob"]
    set_privacy(client, bob, is_private=True)
    assert public(client).json()["is_private"] is False
    assert client.patch("/api/me/privacy", json={"user_id": str(people["alice"][0])}, headers=bob).status_code == 422
    assert client.get("/api/me/privacy").status_code == 401


# ------------------------------------------- no leaks through any endpoint


def _route_paths():
    for route in app.routes:
        if "GET" in getattr(route, "methods", set()) and route.path.startswith("/api/"):
            yield route.path


def _fill(path, ids):
    values = {"username": "alice", "trail_id": ids["trail"], "plan_id": ids["plan"], "item_id": ids["item"]}
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), str(uuid.uuid4())), path)


def test_no_get_endpoint_leaks_private_data_to_visitors(client, alice_profile, people):
    _, bob = people["bob"]
    _, alice = people["alice"]
    set_privacy(client, alice, show_trip_plans=True)  # the most a visitor could ever see
    paths = sorted(set(_route_paths()))
    assert "/api/profiles/{username}" in paths and "/api/me/alerts" in paths
    for path in paths:
        url = _fill(path, alice_profile)
        for viewer, headers in (("guest", {}), ("bob", bob)):
            try:
                response = client.get(url, headers=headers)
            except Exception:  # noqa: BLE001  (a crash returns nothing, so nothing leaks)
                continue
            assert_no_canaries(response.text, f"GET {url} as {viewer}")
            if path.startswith("/api/me") and viewer == "bob" and response.status_code == 200:
                assert "Skyline in fall" not in response.text and "Old stove" not in response.text, url


def test_visitors_cant_reach_owner_only_endpoints(client, alice_profile, people):
    for path in ("/api/me/profile", "/api/me/alerts", "/api/me/plans", "/api/me/hike-logs", "/api/me/gear", "/api/me/privacy"):
        assert client.get(path).status_code == 401, path
    _, bob = people["bob"]
    assert client.get(f"/api/me/plans/{alice_profile['plan']}", headers=bob).status_code == 404
    assert client.get("/api/me/alerts", headers=bob).json() == []


# ----------------------------------------------------------------- reports


def test_signed_in_visitor_can_report_a_profile(client, alice_profile, people, outbox):
    bob_id, bob = people["bob"]
    response = client.post("/api/profiles/alice/report", json={"reason": "spam", "details": " Selling boots "}, headers=bob)
    assert response.status_code == 202
    [email] = outbox.sent
    assert email.to == "treklyusersupport@gmail.com"
    assert "@alice" in email.subject and "spam" in email.subject
    assert "/u/alice" in email.text and "Selling boots" in email.text and str(bob_id) in email.text
    assert "bob@example.com" not in email.text  # the reporter's account, never their email
    # Support learns who reported, but the report never exposes Alice's private data.
    assert_no_canaries(email.text, "the report email")


def test_guests_cant_report(client, alice_profile, outbox):
    assert client.post("/api/profiles/alice/report", json={"reason": "spam"}).status_code == 401
    assert outbox.sent == []


def test_reports_are_rate_limited(client, alice_profile, people, outbox, make_token, session_factory):
    _, bob = people["bob"]
    assert client.post("/api/profiles/alice/report", json={"reason": "spam"}, headers=bob).status_code == 202
    again = client.post("/api/profiles/alice/report", json={"reason": "other"}, headers=bob)
    assert again.status_code == 429 and "already reported" in again.text

    # Five different profiles a day at most.
    for n in range(4):
        other_id = uuid.uuid4()
        headers = {"Authorization": f"Bearer {make_token(other_id)}"}
        assert client.patch("/api/me/profile", json={"username": f"other_{n}"}, headers=headers).status_code == 200
        assert client.post(f"/api/profiles/other_{n}/report", json={"reason": "spam"}, headers=bob).status_code == 202
    other_id = uuid.uuid4()
    headers = {"Authorization": f"Bearer {make_token(other_id)}"}
    client.patch("/api/me/profile", json={"username": "other_last"}, headers=headers)
    limited = client.post("/api/profiles/other_last/report", json={"reason": "spam"}, headers=bob)
    assert limited.status_code == 429 and "several reports" in limited.text
    assert len(outbox.sent) == 5


def test_reports_need_a_known_reason_and_not_yourself(client, alice_profile, people, outbox):
    _, alice = people["alice"]
    _, bob = people["bob"]
    assert client.post("/api/profiles/alice/report", json={"reason": "boring"}, headers=bob).status_code == 422
    assert client.post("/api/profiles/alice/report", json={"reason": "spam"}, headers=alice).status_code == 422
    assert client.post("/api/profiles/nobody/report", json={"reason": "spam"}, headers=bob).status_code == 404


def test_a_failed_email_doesnt_count_against_the_limit(client, alice_profile, people):
    _, bob = people["bob"]
    app.dependency_overrides[get_email_sender] = lambda: Outbox(fail=True)
    assert client.post("/api/profiles/alice/report", json={"reason": "spam"}, headers=bob).status_code == 503
    box = Outbox()
    app.dependency_overrides[get_email_sender] = lambda: box
    assert client.post("/api/profiles/alice/report", json={"reason": "spam"}, headers=bob).status_code == 202


# ------------------------------------------------------------- moderation


@pytest.fixture
def admin(make_token, monkeypatch):
    admin_id = uuid.uuid4()
    monkeypatch.setenv("ADMIN_USER_IDS", str(admin_id))
    monkeypatch.delenv("PHOTO_ADMIN_USER_IDS", raising=False)
    return {"Authorization": f"Bearer {make_token(admin_id)}"}


def test_admin_can_hide_and_unhide_a_profile(client, alice_profile, people, admin, outbox):
    _, alice = people["alice"]
    _, bob = people["bob"]
    hidden = client.put("/api/admin/profiles/alice/hidden", json={"reason": "Spam"}, headers=admin)
    assert hidden.status_code == 200 and hidden.json()["username"] == "alice"
    assert public(client).status_code == 404
    assert public(client, headers=alice).status_code == 404
    assert client.post("/api/profiles/alice/report", json={"reason": "spam"}, headers=bob).status_code == 404
    assert client.get("/api/me/privacy", headers=alice).json()["hidden_by_moderators"] is True
    # The owner can't undo it through their settings.
    set_privacy(client, alice, is_private=False)
    assert public(client).status_code == 404
    assert [row["username"] for row in client.get("/api/admin/profiles/hidden", headers=admin).json()] == ["alice"]

    assert client.delete("/api/admin/profiles/alice/hidden", headers=admin).status_code == 204
    assert public(client).status_code == 200


def test_photo_admins_count_as_admins(client, alice_profile, make_token, monkeypatch):
    photo_admin = uuid.uuid4()
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    monkeypatch.setenv("PHOTO_ADMIN_USER_IDS", str(photo_admin))
    headers = {"Authorization": f"Bearer {make_token(photo_admin)}"}
    assert client.get("/api/admin/profiles/hidden", headers=headers).status_code == 200


def test_only_admins_can_moderate(client, alice_profile, people, admin):
    _, alice = people["alice"]
    _, bob = people["bob"]
    for headers in (bob, alice):
        assert client.put("/api/admin/profiles/alice/hidden", json={}, headers=headers).status_code == 403
        assert client.delete("/api/admin/profiles/alice/hidden", headers=headers).status_code == 403
        assert client.get("/api/admin/profiles/hidden", headers=headers).status_code == 403
    assert client.get("/api/admin/profiles/hidden").status_code == 401
    assert public(client).status_code == 200


# ------------------------------------------------------------------- rank


@pytest.mark.parametrize("hikes, level, title", [(0, 1, "Trailhead"), (1, 2, "Day Tripper"), (3, 3, "Trail Regular"),
                                                  (10, 4, "Pathfinder"), (25, 5, "Backcountry Veteran"), (80, 6, "Trail Legend")])
def test_rank_tiers(hikes, level, title):
    from app.privacy import rank_for

    assert rank_for(hikes) == (level, title)


def test_account_deletion_removes_privacy_rows(client, alice_profile, people, session_factory, admin, outbox):
    alice_id, alice = people["alice"]
    _, bob = people["bob"]
    from app.models.privacy import ProfileModeration, ProfileReport, ProfileSettings

    client.post("/api/profiles/alice/report", json={"reason": "spam"}, headers=bob)
    client.put("/api/admin/profiles/alice/hidden", json={}, headers=admin)
    db = session_factory()
    # SQLite has no FK from these to auth users, so remove the rows that block the delete.
    db.query(AvailabilityAlert).filter_by(user_id=alice_id).delete()
    db.query(TripPlan).filter_by(user_id=alice_id).delete()
    db.commit()
    assert client.request("DELETE", "/api/me", json={"confirm": "delete my account"}, headers=alice).status_code == 204
    assert db.get(ProfileSettings, alice_id) is None
    assert db.get(ProfileModeration, alice_id) is None
    assert db.query(ProfileReport).filter_by(profile_id=alice_id).count() == 0
    db.close()
