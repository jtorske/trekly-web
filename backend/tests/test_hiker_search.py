"""People search and "Hikers you might know" through the API: sign-in,
query rules, what each result shows, paging, the rate limit and the
"Let people find me in search" setting.

Matching, ranking and who may appear are database functions (Postgres
only), tested against the local stack in test_hiker_search_db.py. Here a
stand-in finder returns chosen hits, so the API's own part is checked.
"""

import uuid

import pytest

from app.hiker_search import SearchHit, SearchLimiter, Suggestion
from app.main import app
from app.routers.hiker_search import get_hiker_finder, get_search_limiter
from app.routers.signup_email import get_client_ip
from tests.test_activity import log, person, set_privacy, trails  # noqa: F401  (fixtures)
from tests.test_follows import approve, follow


class FakeFinder:
    def __init__(self):
        self.hits: list[SearchHit] = []
        self.suggestions: list[Suggestion] = []
        self.calls: list[tuple] = []

    def search(self, db, viewer_id, q, limit, offset):
        self.calls.append((viewer_id, q, limit, offset))
        return self.hits[offset:offset + limit]

    def suggest(self, db, viewer_id, limit):
        return self.suggestions[:limit]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def finder(client):
    fake = FakeFinder()
    app.dependency_overrides[get_hiker_finder] = lambda: fake
    yield fake


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def limiter(client, clock):
    fresh = SearchLimiter(per_user=60, per_ip=120, window=60, clock=clock)
    app.dependency_overrides[get_search_limiter] = lambda: fresh
    return fresh


@pytest.fixture
def ip(client):
    current = {"value": "203.0.113.5"}
    app.dependency_overrides[get_client_ip] = lambda: current["value"]
    return current


@pytest.fixture
def viewer(person):  # noqa: F811
    return person("viewer", province="AB")


def hit(who, tier=3, common_trails=0, opened=True):
    return SearchHit(who["id"], tier, common_trails, opened)


def search(client, who, q="hiker", expect=200, **params):
    response = client.get("/api/search/hikers", params={"q": q, **params}, headers=who["headers"] if who else {})
    assert response.status_code == expect, response.text
    return response.json() if expect == 200 else response


def only(body):
    assert len(body["items"]) == 1, body
    return body["items"][0]


# ------------------------------------------------------------------- access

def test_hiker_search_needs_sign_in(client, finder, limiter):
    assert client.get("/api/search/hikers", params={"q": "jordan"}).status_code == 401
    assert client.get("/api/me/suggested-hikers").status_code == 401
    assert finder.calls == []


def test_trail_search_stays_open_to_guests(client):
    assert client.post("/api/trails/search", json={"q": "lake"}).status_code == 200


@pytest.mark.parametrize("q", ["", "j", " j ", "@j", "@ "])
def test_two_characters_at_least(client, finder, limiter, viewer, q):
    search(client, viewer, q, expect=422)
    assert finder.calls == []


def test_queries_have_a_length_limit(client, finder, limiter, viewer):
    search(client, viewer, "a" * 61, expect=422)


def test_the_finder_gets_the_trimmed_query(client, finder, limiter, viewer):
    search(client, viewer, "  @Joëlle ")
    assert finder.calls == [(viewer["id"], "Joëlle", 21, 0)]


def test_results_arent_cached(client, finder, limiter, viewer):
    response = client.get("/api/search/hikers", params={"q": "jo"}, headers=viewer["headers"])
    assert response.headers["cache-control"] == "no-store"


# ---------------------------------------------------------- what rows show

def test_a_public_hiker_shows_rank_province_and_trails_in_common(client, finder, limiter, viewer, person):  # noqa: F811
    jordan = person("jordan", province="AB", show_home_province=True)
    finder.hits = [hit(jordan, tier=2, common_trails=3)]
    row = only(search(client, viewer))
    assert row == {
        "username": "jordan",
        "display_name": "Jordan",
        "avatar_path": None,
        "is_private": False,
        "follow": "none",
        "rank": {"level": 1, "title": row["rank"]["title"]},
        "home_province": "AB",
        "common_trails": 3,
        "same_province": False,
    }


def test_hidden_sections_stay_hidden(client, finder, limiter, viewer, person):  # noqa: F811
    jordan = person("jordan", province="AB", show_home_province=False, show_rank=False, show_journal=False)
    # Even if the finder said otherwise, the row shows only what's switched on.
    finder.hits = [hit(jordan, common_trails=3)]
    row = only(search(client, viewer))
    assert (row["rank"], row["home_province"], row["common_trails"]) == (None, None, None)


def test_a_private_profile_shows_only_name_username_and_photo(client, finder, limiter, viewer, person):  # noqa: F811
    ben = person("ben", province="AB", is_private=True, findable_in_search=True, show_home_province=True)
    finder.hits = [hit(ben, common_trails=None, opened=False)]
    row = only(search(client, viewer))
    assert row["is_private"] is True and row["follow"] == "none"
    assert (row["rank"], row["home_province"], row["common_trails"]) == (None, None, None)
    assert (row["username"], row["display_name"]) == ("ben", "Ben")


def test_an_approved_follower_sees_what_a_private_profile_shows(client, finder, limiter, viewer, person):  # noqa: F811
    ben = person("ben", province="AB", is_private=True, findable_in_search=True, show_home_province=True)
    follow(client, viewer, ben)
    approve(client, ben, viewer)
    finder.hits = [hit(ben, tier=1, common_trails=2, opened=True)]
    row = only(search(client, viewer))
    assert row["follow"] == "following"
    assert row["rank"] is not None and row["home_province"] == "AB" and row["common_trails"] == 2


def test_follow_states(client, finder, limiter, viewer, person):  # noqa: F811
    ana = person("ana")
    ben = person("ben", is_private=True, findable_in_search=True)
    cam = person("cam")
    follow(client, viewer, ana)
    follow(client, viewer, ben)
    finder.hits = [hit(ana, tier=1), hit(ben, opened=False, common_trails=None), hit(cam)]
    assert [(r["username"], r["follow"]) for r in search(client, viewer)["items"]] == [
        ("ana", "following"), ("ben", "requested"), ("cam", "none"),
    ]


def test_order_is_the_finders(client, finder, limiter, viewer, person):  # noqa: F811
    people = [person(name) for name in ("dee", "ana", "cam")]
    finder.hits = [hit(p) for p in people]
    assert [r["username"] for r in search(client, viewer)["items"]] == ["dee", "ana", "cam"]


def test_someone_gone_since_the_search_is_skipped(client, finder, limiter, viewer, person):  # noqa: F811
    ana = person("ana")
    finder.hits = [SearchHit(uuid.uuid4(), 3, 0, True), hit(ana)]
    assert [r["username"] for r in search(client, viewer)["items"]] == ["ana"]


def test_pages(client, finder, limiter, viewer, person):  # noqa: F811
    finder.hits = [hit(person(f"hiker{n}")) for n in range(5)]
    first = search(client, viewer, limit=2)
    assert [r["username"] for r in first["items"]] == ["hiker0", "hiker1"] and first["next_offset"] == 2
    last = search(client, viewer, limit=2, offset=4)
    assert [r["username"] for r in last["items"]] == ["hiker4"] and last["next_offset"] is None
    search(client, viewer, limit=51, expect=422)


# --------------------------------------------------------------- rate limit

def test_search_is_rate_limited_per_user(client, finder, limiter, viewer, person, clock, ip):  # noqa: F811
    limiter.per_user = 3
    for _ in range(3):
        search(client, viewer)
    refused = search(client, viewer, expect=429)
    assert int(refused.headers["retry-after"]) >= 1
    # Someone else, from another address, isn't affected.
    ip["value"] = "198.51.100.7"
    search(client, person("other"))
    # The window moves on.
    clock.now += 61
    search(client, viewer)


def test_search_is_rate_limited_per_ip(client, finder, limiter, person, ip):  # noqa: F811
    limiter.per_ip = 3
    for n in range(3):
        search(client, person(f"user{n}"))
    search(client, person("user3"), expect=429)
    ip["value"] = "198.51.100.7"
    search(client, person("user4"))


def test_refused_requests_dont_count(clock):
    limiter = SearchLimiter(per_user=2, per_ip=100, window=60, clock=clock)
    user = uuid.uuid4()
    assert limiter.check(user, "a") is None
    clock.now += 30
    assert limiter.check(user, "a") is None
    for _ in range(5):
        clock.now += 1
        assert limiter.check(user, "a") is not None
    # 60 s after the first request one slot opens, despite the refusals.
    clock.now = 1000.0 + 60
    assert limiter.check(user, "a") is None


def test_invalid_queries_dont_use_up_the_limit(client, finder, limiter, viewer):
    limiter.per_user = 1
    search(client, viewer, "j", expect=422)
    search(client, viewer)


# -------------------------------------------------------------- suggestions

def test_suggestions(client, finder, viewer, person):  # noqa: F811
    ana = person("ana", province="AB", show_home_province=True)
    cam = person("cam")
    finder.suggestions = [Suggestion(cam["id"], 4, False), Suggestion(ana["id"], 0, True)]
    response = client.get("/api/me/suggested-hikers", headers=viewer["headers"])
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    rows = response.json()["items"]
    assert [(r["username"], r["common_trails"], r["same_province"], r["home_province"]) for r in rows] == [
        ("cam", 4, False, None), ("ana", 0, True, "AB"),
    ]
    assert all(r["follow"] == "none" for r in rows)


# ----------------------------------------------------------------- setting

def test_findable_is_off_by_default_and_can_be_turned_on(client, viewer):
    headers = viewer["headers"]
    assert client.get("/api/me/privacy", headers=headers).json()["findable_in_search"] is False
    set_privacy(client, viewer, findable_in_search=True)
    assert client.get("/api/me/privacy", headers=headers).json()["findable_in_search"] is True


# ------------------------------------- same_province is always a real boolean
#
# Production 500 (2026-11-21): suggest_hikers() compares provinces in SQL, so
# a viewer or hiker without one gave NULL, and HikerOut refused None. The
# flag is now worked out in Python; these cover every way it can be missing.

PROVINCE_CASES = [
    # viewer province, their province, they show it, what SQL said, expected
    pytest.param(None, None, False, None, False, id="neither-has-one"),
    pytest.param(None, "AB", True, None, False, id="viewer-has-none"),
    pytest.param("AB", None, False, None, False, id="hiker-has-none"),
    pytest.param("AB", "AB", False, None, False, id="hiker-hides-it"),
    pytest.param("outside", "outside", True, True, False, id="both-outside-canada"),
    pytest.param("AB", "outside", True, None, False, id="hiker-outside-canada"),
    pytest.param("AB", "BC", True, False, False, id="different-provinces"),
    pytest.param("AB", "AB", True, False, True, id="same-province-shown"),
]


def province_pair(person, mine, theirs, shown):  # noqa: F811
    viewer = person("viewer", province=mine)
    them = person("them", province=theirs, show_home_province=shown)
    return viewer, them


@pytest.mark.parametrize("mine, theirs, shown, from_sql, expected", PROVINCE_CASES)
def test_suggested_hikers_same_province_never_null(client, finder, person, mine, theirs, shown, from_sql, expected):  # noqa: F811
    viewer, them = province_pair(person, mine, theirs, shown)
    finder.suggestions = [Suggestion(them["id"], 1, from_sql)]
    response = client.get("/api/me/suggested-hikers", headers=viewer["headers"])
    assert response.status_code == 200, response.text
    assert only(response.json())["same_province"] is expected


@pytest.mark.parametrize("mine, theirs, shown, from_sql, expected", PROVINCE_CASES)
def test_activity_feed_suggested_hikers_same_province_never_null(
    client, person, mine, theirs, shown, from_sql, expected,  # noqa: F811
):
    from app.routers.activity import get_feed_finder

    viewer, them = province_pair(person, mine, theirs, shown)

    class One:
        def suggest(self, db, viewer_id, limit):
            return [Suggestion(them["id"], 1, from_sql)]

    app.dependency_overrides[get_feed_finder] = lambda: One()
    try:
        response = client.get("/api/activity", headers=viewer["headers"])
    finally:
        app.dependency_overrides.pop(get_feed_finder, None)
    assert response.status_code == 200, response.text
    hikers = response.json()["suggested_hikers"]
    assert [h["username"] for h in hikers] == ["them"]
    assert hikers[0]["same_province"] is expected


def test_search_rows_never_claim_same_province(client, finder, limiter, viewer, person):  # noqa: F811
    jordan = person("jordan", province="AB", show_home_province=True)
    finder.hits = [hit(jordan)]
    assert only(search(client, viewer))["same_province"] is False
