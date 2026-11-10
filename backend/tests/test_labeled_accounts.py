"""The official @trekly account, demo hikers and "Trekly picks".

- The "Trekly team" and "Demo account" labels come back with every author:
  feed posts, who high-fived, public profiles, follow lists, admin users.
- Only the official account's announcements ever show; admins post them.
- Demo accounts never high-five or follow real users, are left out of
  "Hiked by", trending, admin stats, people search and the picks count,
  and stay out of search engines. Real users can still high-five them.
- Removing them deletes every row that names them, and nothing else.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select

from app.account_labels import may_interact, real_user
from app.demo_data import DemoHike, DemoHiker
from app.labeled_accounts import (
    OfficialDraft, create_demo, demo_ids, ensure_official, post_drafts, references, remove_demo,
)
from app.main import app
from app.models.account import Profile, SavedTrail
from app.models.account_label import AccountLabel
from app.models.activity import ActivityPost, ActivityReaction
from app.models.admin import AUTH_USERS, AdminAuditLog
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileReport
from app.models.social import Follow
from app.models.trail import Trail
from app.routers.admin_trail_photos import get_photo_storage
from app.routers.availability import get_today
from tests.test_activity import feed, log, person  # noqa: F401  (fixture)
from tests.test_availability import world  # noqa: F401  (fixture)

TODAY = date(2026, 10, 15)
ADMIN = uuid.UUID("aaaaaaaa-0000-4000-8000-00000000a0a0")


@pytest.fixture(autouse=True)
def fixed_today():
    app.dependency_overrides[get_today] = lambda: TODAY
    yield
    app.dependency_overrides.pop(get_today, None)


class FakeAuth:
    """Creates and deletes auth.users rows, as Supabase's admin API would.
    Uses the caller's session (SQLite here has one shared connection)."""

    def __init__(self):
        self.db = None
        self.created: list[uuid.UUID] = []
        self.deleted: list[uuid.UUID] = []

    def create_user(self, email, password, display_name):
        assert len(password) >= 32
        user_id = uuid.uuid4()
        self.db.execute(insert(AUTH_USERS).values(id=user_id, email=email, created_at=datetime.now(timezone.utc)))
        self.created.append(user_id)
        return user_id

    def delete_user(self, user_id):
        self.db.execute(AUTH_USERS.delete().where(AUTH_USERS.c.id == user_id))
        self.db.commit()
        self.deleted.append(user_id)


class FakeStore:
    def __init__(self):
        self.uploaded: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def upload(self, path, data):
        self.uploaded[path] = data

    def delete(self, paths):
        self.deleted += paths


@pytest.fixture
def catalogue(session_factory):
    """Four live trails, BC and AB, by popularity."""
    db = session_factory()
    names = [("Peak One", "BC"), ("Lake Two", "BC"), ("Ridge Three", "AB"), ("Falls Four", "AB")]
    ids = {}
    for rank, (name, province) in enumerate(names, start=1):
        trail = Trail(name=name, region=f"{province} park", country_code="CA", province_code=province,
                      terrain_difficulty="moderate", popularity_rank=rank)
        db.add(trail)
        db.flush()
        ids[name] = trail.id
    db.commit()
    db.close()
    return ids


HIKERS = (
    DemoHiker(
        username="demo_test", display_name="Dee Demo", bio="Made up.", province="BC", colours=("#000000", "#ffffff"),
        hikes=(
            DemoHike("Peak One", "BC", 30, "First one."),
            DemoHike("Lake Two", "BC", 3, "Shared one.", share=True),
            DemoHike("Nowhere Trail", "BC", 2, share=True),  # not in the catalogue: skipped
        ),
        saved=(("Ridge Three", "AB"),),
        plan=("Falls Four", "AB", 40, 1, "Next summer"),
    ),
    DemoHiker(
        username="demo_two", display_name="Dan Demo", bio="Made up.", province="AB", colours=("#000000", "#ffffff"),
        hikes=(DemoHike("Ridge Three", "AB", 2, "Shared too.", share=True),),
    ),
)


@pytest.fixture
def auth():
    return FakeAuth()


def using(auth, db):
    auth.db = db
    return db


@pytest.fixture
def demos(session_factory, catalogue, auth):
    db = using(auth, session_factory())
    store = FakeStore()
    made = create_demo(db, auth, store, TODAY, HIKERS)
    db.close()
    return {"ids": made, "store": store}


@pytest.fixture
def official(session_factory, auth):
    db = using(auth, session_factory())
    store = FakeStore()
    user_id, made = ensure_official(db, auth, store)
    assert made
    db.close()
    return {"id": user_id, "store": store}


@pytest.fixture
def admin_headers(monkeypatch, make_token):
    monkeypatch.setenv("ADMIN_USER_IDS", str(ADMIN))
    monkeypatch.delenv("PHOTO_ADMIN_USER_IDS", raising=False)
    return {"Authorization": f"Bearer {make_token(ADMIN)}"}


def demo_headers(make_token, user_id):
    return {"Authorization": f"Bearer {make_token(user_id)}"}


def posts_by(body, username):
    return [item for item in body["items"] if item["author"]["username"] == username]


# ------------------------------------------------------------ official account


def test_the_official_account_is_made_once(session_factory, official, auth):
    db = using(auth, session_factory())
    profile = db.get(Profile, official["id"])
    assert (profile.username, profile.display_name) == ("trekly", "Trekly")
    assert profile.avatar_path in official["store"].uploaded
    assert db.get(AccountLabel, official["id"]).label == "official"
    again, made = ensure_official(db, auth, FakeStore())
    assert again == official["id"] and made is False
    assert len(auth.created) == 1


def test_admins_post_as_trekly_and_it_shows_with_the_team_label(client, official, catalogue, admin_headers):
    response = client.post("/api/admin/official-posts", headers=admin_headers,
                           json={"body": "  New trails are in!  ", "trail_id": str(catalogue["Peak One"])})
    assert response.status_code == 201, response.text
    assert response.json()["body"] == "New trails are in!"

    [post] = posts_by(feed(client), "trekly")
    assert post["kind"] == "announcement"
    assert post["author"]["label"] == "official"
    assert post["author"]["display_name"] == "Trekly"
    assert post["announcement"]["body"] == "New trails are in!"
    assert post["announcement"]["trail"]["name"] == "Peak One"
    assert client.get("/api/profiles/trekly").json()["label"] == "official"

    listed = client.get("/api/admin/official-posts", headers=admin_headers).json()
    assert listed["account"]["username"] == "trekly" and len(listed["posts"]) == 1


def test_posting_is_audited_and_deleting_removes_the_post(client, official, admin_headers, session_factory):
    post_id = client.post("/api/admin/official-posts", headers=admin_headers, json={"body": "Hello"}).json()["id"]
    app.dependency_overrides[get_photo_storage] = lambda: FakeStore()
    try:
        assert client.delete(f"/api/admin/official-posts/{post_id}", headers=admin_headers).status_code == 204
    finally:
        app.dependency_overrides.pop(get_photo_storage, None)
    assert posts_by(feed(client), "trekly") == []
    db = session_factory()
    assert [row.action for row in db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at))] == [
        "official_post", "delete_official_post"]


def test_only_admins_post_and_only_once_the_account_exists(client, make_token, admin_headers, monkeypatch):
    assert client.post("/api/admin/official-posts", headers=admin_headers, json={"body": "Hi"}).status_code == 409
    someone = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    assert client.post("/api/admin/official-posts", headers=someone, json={"body": "Hi"}).status_code == 403
    assert client.get("/api/admin/official-posts", headers=someone).status_code == 403


def test_bad_post_input_is_refused(client, official, admin_headers):
    for body in ({"body": ""}, {"body": "x" * 501}, {"body": "Hi", "photo_path": "someone/else.webp"},
                 {"body": "Hi", "trail_id": str(uuid.uuid4())}, {"body": "Hi", "extra": 1}):
        assert client.post("/api/admin/official-posts", headers=admin_headers, json=body).status_code == 422, body


def test_nobody_elses_announcement_ever_shows(client, person, session_factory):
    alice = person("alice")
    db = session_factory()
    db.add(ActivityPost(user_id=alice["id"], kind="announcement", body="I'm Trekly, honest"))
    db.commit()
    assert posts_by(feed(client), "alice") == []


def test_drafts_post_once(session_factory, official, catalogue):
    db = session_factory()
    drafts = [OfficialDraft("Tip one"), OfficialDraft("Featured", trail=("Peak One", "BC"), days_ago=2)]
    assert len(post_drafts(db, drafts)) == 2
    assert post_drafts(db, drafts) == []
    with pytest.raises(RuntimeError):
        post_drafts(db, [OfficialDraft("Missing", trail=("No Such Trail", "BC"))])


# ------------------------------------------------------------ demo accounts


def test_demo_hikers_are_made_with_their_journal_posts_and_label(client, demos, session_factory):
    db = session_factory()
    assert len(demos["ids"]) == 2 and set(demo_ids(db)) == set(demos["ids"])
    db.close()
    profile = client.get("/api/profiles/demo_test").json()
    assert profile["label"] == "demo"
    assert profile["allow_indexing"] is False
    assert len(profile["journal"]["entries"]) == 2  # the unknown trail was skipped
    assert [t["name"] for t in profile["saved_trails"]] == ["Ridge Three"]
    assert profile["trip_plans"][0]["title"] == "Next summer"

    body = feed(client)
    mine = posts_by(body, "demo_test")
    assert [p["hike"]["trail"]["name"] for p in mine if p["kind"] == "hike"] == ["Lake Two"]
    assert all(p["author"]["label"] == "demo" for p in body["items"])
    # Demo hikers high-five each other.
    assert any(p["high_fives"] > 0 for p in body["items"])


def test_creating_twice_skips_existing_demo_hikers(session_factory, demos, auth):
    db = using(auth, session_factory())
    assert create_demo(db, auth, FakeStore(), TODAY, HIKERS) == []


def test_demo_accounts_never_interact_with_real_users(client, demos, person, catalogue, make_token):
    alice = person("alice")
    log(client, alice, catalogue["Peak One"], hiked_on="2026-10-10")
    real_post = posts_by(feed(client), "alice")[0]["id"]
    demo = demo_headers(make_token, demos["ids"][0])

    assert client.put(f"/api/activity/{real_post}/high-five", headers=demo).status_code == 403
    assert client.put("/api/profiles/alice/follow", headers=demo).status_code == 403

    # Real users may high-five and follow demo hikers, and demos may reach each other.
    demo_post = posts_by(feed(client), "demo_two")[0]["id"]
    assert client.put(f"/api/activity/{demo_post}/high-five", headers=alice["headers"]).status_code == 200
    assert client.put(f"/api/activity/{demo_post}/high-five", headers=demo).status_code == 200
    assert client.put("/api/profiles/demo_two/follow", headers=alice["headers"]).status_code == 200
    fivers = client.get(f"/api/activity/{demo_post}/high-fives").json()["hikers"]
    assert {(h["username"], h["label"]) for h in fivers} >= {("alice", None), ("demo_test", "demo")}


def test_may_interact_rule(session_factory, demos, official):
    db = session_factory()
    real = uuid.uuid4()
    demo, other_demo = demos["ids"]
    assert may_interact(db, real, demo) and may_interact(db, real, real) and may_interact(db, real, official["id"])
    assert may_interact(db, demo, other_demo)
    assert not may_interact(db, demo, real) and not may_interact(db, demo, official["id"])


def test_demo_hikers_stay_out_of_hiked_by_trending_and_stats(client, demos, catalogue, admin_headers, session_factory):
    hikers = client.get(f"/api/trails/{catalogue['Lake Two']}/hikers").json()
    assert hikers == {"hikers": [], "others": 0, "notes": []}

    # Demo logs are fresh (created this week by the script) but don't count.
    db = session_factory()
    db.execute(HikeLog.__table__.update().values(created_at=datetime.now(timezone.utc)))
    db.execute(SavedTrail.__table__.update().values(created_at=datetime.now(timezone.utc)))
    db.commit()
    trending = client.get("/api/activity/trending").json()["trails"]
    assert all(t["this_week"] is False for t in trending)

    overview = client.get("/api/admin/overview", headers=admin_headers).json()
    assert overview["users_total"] == 0 and overview["hikes_total"] == 0
    users = client.get("/api/admin/users", headers=admin_headers).json()["items"]
    assert {u["label"] for u in users} == {"demo"}  # still listed for admins, with their badge


def test_demo_hikers_are_not_found_in_people_lists_meant_for_discovery(session_factory, demos):
    """Search and suggestions must filter with real_user; this pins the rule."""
    db = session_factory()
    found = db.scalars(select(Profile.username).where(real_user(Profile.id))).all()
    assert not [name for name in found if name and name.startswith("demo_")]


def test_the_demo_data_fits_the_database_rules():
    """Postgres checks these (SQLite here doesn't model every one)."""
    from app.demo_data import DEMO_HIKERS, FEATURED_DEMO
    from app.models.trip_plan import MAX_PLAN_NIGHTS

    assert FEATURED_DEMO in {h.username for h in DEMO_HIKERS}
    for hiker in DEMO_HIKERS:
        assert hiker.username.startswith("demo_") and 3 <= len(hiker.username) <= 30
        assert hiker.experience in ("new", "few_seasons", "seasoned")
        assert hiker.style in ("day", "overnight", "both")
        assert len(hiker.bio) <= 280 and "Demo account" in hiker.bio
        if hiker.plan:
            assert 1 <= hiker.plan[3] <= MAX_PLAN_NIGHTS and hiker.plan[2] > 0
        assert all(h.days_ago >= 0 for h in hiker.hikes)


# ------------------------------------------------------------ removal


def test_removal_deletes_everything_naming_demo_accounts(client, demos, person, catalogue, session_factory, auth,
                                                          make_token):
    alice = person("alice")
    log(client, alice, catalogue["Peak One"], hiked_on="2026-10-10")
    demo_post = posts_by(feed(client), "demo_two")[0]["id"]
    client.put(f"/api/activity/{demo_post}/high-five", headers=alice["headers"])
    client.put("/api/profiles/demo_two/follow", headers=alice["headers"])
    client.post("/api/profiles/demo_test/report", headers=alice["headers"], json={"reason": "spam"})

    db = using(auth, session_factory())
    ids = demo_ids(db)
    assert references(db, ids)  # there's plenty to clean up
    avatars = [p for p in db.scalars(select(Profile.avatar_path).where(Profile.id.in_(ids)))]
    store = FakeStore()
    removed = remove_demo(db, auth, store)

    assert set(removed) == set(ids)
    assert references(db, ids) == {}
    assert set(auth.deleted) == set(ids)
    assert sorted(store.deleted) == sorted(avatars)
    assert db.scalar(select(AUTH_USERS.c.id).where(AUTH_USERS.c.id.in_(ids))) is None
    assert db.scalars(select(Follow)).all() == []
    assert db.scalars(select(ProfileReport)).all() == []
    assert db.scalars(select(ActivityReaction)).all() == []
    db.commit()
    # Alice keeps everything of her own.
    assert [p["kind"] for p in posts_by(feed(client), "alice")][:1] == ["hike"]
    assert client.get("/api/profiles/demo_test").status_code == 404
    assert remove_demo(db, auth, store) == []
    db.close()


# ------------------------------------------------------------ Trekly picks


def test_picks_show_while_real_activity_is_quiet(client, catalogue, demos, official, person, session_factory):
    body = client.get("/api/activity/picks").json()
    assert body["sparse"] is True
    kinds = [p["kind"] for p in body["picks"]]
    assert kinds[0] == "trending"
    assert len({p["trail"]["id"] for p in body["picks"]}) == len(body["picks"])

    # Ten real posts this week end the picks; demo and official posts never counted.
    db = session_factory()
    now = datetime.now(timezone.utc)
    alice = person("alice")
    for n in range(9):
        db.add(ActivityPost(user_id=alice["id"], kind="rank", rank_level=n + 2, created_at=now - timedelta(hours=n)))
    db.commit()
    assert client.get("/api/activity/picks").json()["sparse"] is True
    db.add(ActivityPost(user_id=alice["id"], kind="milestone", milestone="first-hike", created_at=now))
    db.commit()
    assert client.get("/api/activity/picks").json() == {"sparse": False, "picks": []}
