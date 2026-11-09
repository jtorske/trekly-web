"""Adding hikes: every entry point goes through app/hike_service.add_hikes,
which evaluates the journal once and reports what the hikes earned."""

import uuid
from datetime import datetime, timedelta, timezone

import app.hike_service as hike_service
from app.models.preferences import ProfilePreferences
from tests.test_hike_history import PAST, alice, put, trails  # noqa: F401  (fixtures)


def rank_and_milestones(client, headers):
    rank = client.get("/api/me/rank", headers=headers).json()
    earned = {m["id"] for m in client.get("/api/me/milestones", headers=headers).json()["milestones"] if m["earned"]}
    return rank["points"], rank["rank"]["title"], earned


def test_onboarding_picks_stamp_trails_and_earn_milestones_and_points(client, auth_headers, alice, trails):
    headers = auth_headers(alice)
    response = client.post(PAST, json={"trail_ids": trails[:5]}, headers=headers)
    assert response.status_code == 201
    progress = response.json()["progress"]
    assert progress["stamps"] == 5 and progress["new_stamps"] == 5
    assert {m["id"] for m in progress["new_milestones"]} >= {"first-hike", "first-overnight"}
    assert progress["milestones_earned"] == len(progress["new_milestones"])
    assert progress["points"] == progress["points_gained"] > 0
    assert progress["ranked_up"] is True

    # What the rest of the app reads agrees with the summary.
    points, title, earned = rank_and_milestones(client, headers)
    assert points == progress["points"]
    assert title == progress["rank"]["title"]
    assert earned == {m["id"] for m in progress["new_milestones"]}
    assert len(client.get("/api/me/hike-logs", headers=headers).json()) == 5


def test_every_entry_point_gives_the_same_result(client, auth_headers, trails):
    one_by_one, in_bulk = auth_headers(uuid.uuid4()), auth_headers(uuid.uuid4())
    for trail_id in trails[:4]:
        saved = put(client, one_by_one, trail_id, None)
        assert saved.status_code == 201
        assert saved.json()["progress"]["new_stamps"] == 1
    client.post(PAST, json={"trail_ids": trails[:4]}, headers=in_bulk)
    assert rank_and_milestones(client, one_by_one) == rank_and_milestones(client, in_bulk)


def test_editing_a_hike_reports_no_progress(client, auth_headers, alice, trails):
    headers = auth_headers(alice)
    assert put(client, headers, trails[0], "2026-07-01").json()["progress"]["new_stamps"] == 1
    edited = put(client, headers, trails[0], "2026-07-02", note="Windy")
    assert edited.status_code == 200
    assert edited.json()["progress"] is None


def test_a_bulk_add_evaluates_the_journal_once(client, auth_headers, alice, trails, monkeypatch):
    calls = []
    real = hike_service.gather
    monkeypatch.setattr(hike_service, "gather", lambda db, user_id: calls.append(user_id) or real(db, user_id))
    response = client.post(PAST, json={"trail_ids": trails[:6]}, headers=auth_headers(alice))
    assert len(response.json()["added"]) == 6
    # Once before (what was already earned) and once after, not once per hike.
    assert len(calls) == 2


def test_nothing_new_skips_the_second_evaluation(client, auth_headers, alice, trails, monkeypatch):
    headers = auth_headers(alice)
    client.post(PAST, json={"trail_ids": trails[:2]}, headers=headers)
    calls = []
    real = hike_service.gather
    monkeypatch.setattr(hike_service, "gather", lambda db, user_id: calls.append(user_id) or real(db, user_id))
    again = client.post(PAST, json={"trail_ids": trails[:2]}, headers=headers).json()
    assert again["added"] == [] and again["progress"]["points_gained"] == 0
    assert len(calls) == 1


def test_milestones_from_onboarding_picks_say_earned_when_you_joined(client, auth_headers, alice, trails):
    headers = auth_headers(alice)
    client.post(PAST, json={"trail_ids": trails[:3]}, headers=headers)
    earned = [m for m in client.get("/api/me/milestones", headers=headers).json()["milestones"] if m["earned"]]
    assert earned and all(m["earned_with"] == "joining" for m in earned)


def test_past_hikes_added_after_onboarding_say_so(client, auth_headers, alice, trails, session_factory):
    session = session_factory()
    session.add(ProfilePreferences(user_id=alice, onboarding_status="completed",
                                   onboarding_finished_at=datetime.now(timezone.utc) - timedelta(days=3)))
    session.commit()
    session.close()
    headers = auth_headers(alice)
    client.post(PAST, json={"trail_ids": trails[:3]}, headers=headers)
    earned = [m for m in client.get("/api/me/milestones", headers=headers).json()["milestones"] if m["earned"]]
    assert earned and all(m["earned_with"] == "past_hikes" for m in earned)


def test_milestones_from_dated_hikes_have_no_past_hike_label(client, auth_headers, alice, trails):
    headers = auth_headers(alice)
    put(client, headers, trails[1], "2026-07-01")
    # An undated hike added later doesn't take credit for what the dated one earned.
    client.post(PAST, json={"trail_ids": [trails[2]]}, headers=headers)
    first = next(m for m in client.get("/api/me/milestones", headers=headers).json()["milestones"] if m["id"] == "first-hike")
    assert first["earned"] and first["earned_with"] is None
