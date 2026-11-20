"""The blended Activity feed (app/feed.py, GET /api/activity).

The arrangement rules are checked on app.feed.arrange directly (ordering,
the caught-up divider, mixing limits, @trekly spacing, demo accounts last,
picks); the rest go through the API: a full first page however many people
you follow, no repeats across pages, and every visibility rule.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app import feed as blend
from app.main import app
from app.models.account_label import AccountLabel
from app.models.activity import ActivityPost
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileModeration
from app.models.social import Block, Follow
from app.models.trail import Trail
from app.routers.activity import get_feed_finder
from app.routers.availability import get_today

TODAY = date(2026, 10, 15)
NOW = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_today():
    app.dependency_overrides[get_today] = lambda: TODAY
    yield
    app.dependency_overrides.pop(get_today, None)


class NoSuggestions:
    def suggest(self, db, viewer_id, limit):
        return []


@pytest.fixture(autouse=True)
def no_finder():
    app.dependency_overrides[get_feed_finder] = lambda: NoSuggestions()
    yield
    app.dependency_overrides.pop(get_feed_finder, None)


# ------------------------------------------------------------ arrange, by itself


def cand(author, reason, hours_ago, *, trail=None, high_fives=0):
    return blend.Candidate(
        id=uuid.uuid4(), user_id=author, created_at=NOW - timedelta(hours=hours_ago), reason=reason,
        trail_id=trail, high_fives=high_fives,
    )


def people(n):
    return [uuid.uuid4() for _ in range(n)]


def posts(entries):
    return [e.post for e in entries if e.type == "post"]


def test_followed_posts_come_first_newest_first_then_the_divider():
    friends, strangers = people(3), people(3)
    followed = [cand(friends[n % 3], "following", hours_ago=n * 5) for n in range(6)]
    suggested = [cand(strangers[n % 3], "suggested", hours_ago=n) for n in range(6)]
    entries = blend.arrange([*suggested, *followed], blend.Reader(id=uuid.uuid4()), NOW)

    divider = [e.type for e in entries].index("caught_up")
    before = [e.post for e in entries[:divider]]
    lead = [p for p in before if p.reason == "following"]
    assert [p.id for p in lead] == [p.id for p in followed]  # all six, newest first
    # Suggestions are mixed in, never more than two in a row, one per three followed posts.
    assert sum(p.reason == "suggested" for p in before) == 1
    after = [e.post for e in entries[divider + 1:]]
    assert after and all(p.reason == "suggested" for p in after)
    assert len(posts(entries)) == 12


def test_no_divider_without_followed_posts():
    me = uuid.uuid4()
    entries = blend.arrange(
        [cand(me, "own", 1), *(cand(uuid.uuid4(), "suggested", n) for n in range(4))], blend.Reader(id=me), NOW)
    assert "caught_up" not in [e.type for e in entries]
    # Your own recent post still leads.
    assert entries[0].post.reason == "own"


def test_old_followed_posts_join_the_ranking_after_the_divider():
    friend = uuid.uuid4()
    fresh = cand(friend, "following", 2)
    old = cand(friend, "following", 24 * 30)
    entries = blend.arrange([fresh, old, cand(uuid.uuid4(), "suggested", 1)], blend.Reader(id=uuid.uuid4()), NOW)
    types = [e.type for e in entries]
    assert entries[0].post is fresh
    assert types.index("caught_up") < [e.post for e in entries].index(old)


def test_never_more_than_two_non_followed_posts_in_a_row_while_followed_remain():
    friends = people(2)
    followed = [cand(friends[0], "following", n) for n in range(5)]  # one author: needs breaking up
    others = [cand(uuid.uuid4(), "suggested", n) for n in range(20)]
    trekly = uuid.uuid4()
    official = [cand(trekly, "trekly", n) for n in range(5)]
    entries = blend.arrange([*followed, *others, *official], blend.Reader(id=uuid.uuid4()), NOW)
    lead = entries[:[e.type for e in entries].index("caught_up")]
    run = 0
    for entry in lead:
        run = 0 if entry.post.reason == "following" else run + 1
        assert run <= blend.MAX_NON_FOLLOWED_RUN


def test_no_author_twice_in_a_row_when_someone_else_is_available():
    a, b, c = people(3)
    pool = [cand(a, "suggested", n, high_fives=50) for n in range(6)]
    pool += [cand(b, "suggested", n + 0.5) for n in range(4)] + [cand(c, "suggested", n + 0.2) for n in range(3)]
    entries = posts(blend.arrange(pool, blend.Reader(), NOW))
    authors = [p.user_id for p in entries]
    assert len(authors) == 13
    # A's posts rank highest, yet never two together; a repeat only happens
    # once everything left is by one author.
    for n, (x, y) in enumerate(zip(authors, authors[1:])):
        if x == y:
            assert set(authors[n:]) == {x}
    assert all(not (x == y == a) for x, y in zip(authors, authors[1:]))


def test_trekly_posts_at_most_one_in_every_eight():
    trekly = uuid.uuid4()
    pool = [cand(uuid.uuid4(), "suggested", n) for n in range(30)]
    pool += [cand(trekly, "trekly", n) for n in range(10)]
    entries = posts(blend.arrange(pool, blend.Reader(), NOW))
    spots = [i for i, p in enumerate(entries) if p.reason == "trekly"]
    assert spots and spots[0] < blend.TREKLY_GAP
    assert all(later - earlier >= blend.TREKLY_GAP for earlier, later in zip(spots, spots[1:]))


def test_a_lone_trekly_post_still_shows():
    entries = posts(blend.arrange([cand(uuid.uuid4(), "trekly", 1)], blend.Reader(), NOW))
    assert [p.reason for p in entries] == ["trekly"]


def test_demo_posts_never_come_ahead_of_real_hikers():
    demo = [cand(uuid.uuid4(), "demo", 0.1, high_fives=100) for _ in range(3)]
    real = [cand(uuid.uuid4(), "suggested", 24 * 40) for _ in range(4)]
    me = uuid.uuid4()
    entries = posts(blend.arrange([*demo, *real, cand(me, "own", 24 * 50)], blend.Reader(id=me), NOW))
    reasons = [p.reason for p in entries]
    assert reasons.index("demo") > max(i for i, r in enumerate(reasons) if r != "demo")


def test_relevance_prefers_your_trails_parks_and_province():
    hiked, saved, nearby, plain = (uuid.uuid4() for _ in range(4))
    reader = blend.Reader(id=uuid.uuid4(), hiked={hiked}, saved={saved}, parks={"Banff National Park"},
                          province="AB")
    on_hiked = cand(uuid.uuid4(), "suggested", 30, trail=hiked)
    on_saved = cand(uuid.uuid4(), "suggested", 30, trail=saved)
    in_park = cand(uuid.uuid4(), "suggested", 30, trail=nearby)
    in_park.park_name = "Banff National Park"
    in_province = cand(uuid.uuid4(), "suggested", 30, trail=plain)
    in_province.author_province = "AB"
    nothing = cand(uuid.uuid4(), "suggested", 30, trail=uuid.uuid4())
    order = posts(blend.arrange([nothing, in_province, in_park, on_saved, on_hiked], reader, NOW))
    assert order == [on_hiked, on_saved, in_park, in_province, nothing]


def test_your_own_older_posts_dont_crowd_out_suggestions():
    me = uuid.uuid4()
    trail = uuid.uuid4()
    reader = blend.Reader(id=me, hiked={trail})
    mine = cand(me, "own", 24 * 10, trail=trail)
    # A bit older, but on a trail you've hiked too: the match counts for theirs only.
    theirs = cand(uuid.uuid4(), "suggested", 24 * 12, trail=trail)
    assert posts(blend.arrange([mine, theirs], reader, NOW)) == [theirs, mine]


def test_popular_and_recent_posts_rank_higher():
    old_quiet = cand(uuid.uuid4(), "suggested", 24 * 10)
    old_loved = cand(uuid.uuid4(), "suggested", 24 * 10, high_fives=20)
    new_quiet = cand(uuid.uuid4(), "suggested", 1)
    order = posts(blend.arrange([old_quiet, old_loved, new_quiet], blend.Reader(), NOW))
    assert order[-1] is old_quiet and {p.id for p in order[:2]} == {old_loved.id, new_quiet.id}


def test_picks_close_the_feed_and_mix_in_while_quiet():
    pool = [cand(uuid.uuid4(), "suggested", n) for n in range(7)]
    closing = blend.arrange(list(pool), blend.Reader(), NOW, picks=2)
    assert [e.type for e in closing][-2:] == ["pick", "pick"]
    quiet = blend.arrange(list(pool), blend.Reader(), NOW, picks=2, sparse=True)
    assert [e.type for e in quiet].index("pick") == blend.PICK_EVERY
    assert sorted(e.pick for e in quiet if e.type == "pick") == [0, 1]
    assert [e.type for e in blend.arrange([], blend.Reader(), NOW, picks=3)] == ["pick"] * 3


def test_cursor_round_trip():
    cursor = blend.make_cursor(NOW, 40)
    assert blend.parse_cursor(cursor) == (NOW, 40)
    for bad in ("nope", "2026-10-15T18:00:00+00:00~-1", "x~1"):
        with pytest.raises(ValueError):
            blend.parse_cursor(bad)


# ------------------------------------------------------------ through the API


@pytest.fixture
def trails(session_factory):
    db = session_factory()
    ids = []
    for n in range(40):
        trail = Trail(name=f"Feed Trail {n}", region=f"Park {n % 5}, AB", country_code="CA", province_code="AB",
                      terrain_difficulty="easy")
        db.add(trail)
        db.flush()
        ids.append(trail.id)
    db.commit()
    db.close()
    return ids


@pytest.fixture
def person(client, make_token):
    def _make(username, *, share=True, **privacy):
        user_id = uuid.uuid4()
        headers = {"Authorization": f"Bearer {make_token(user_id, email=f'{username}@example.com')}"}
        assert client.patch("/api/me/profile", json={"username": username}, headers=headers).status_code == 200
        response = client.patch("/api/me/privacy", json={"share_activity": share, **privacy}, headers=headers)
        assert response.status_code == 200, response.text
        return {"id": user_id, "headers": headers, "username": username}

    return _make


@pytest.fixture
def post(session_factory, trails):
    """A shared hike post by `who`, `hours_ago` hours old (on a trail of its own)."""
    used = iter(range(10_000))

    def _post(who, hours_ago=1.0, **fields):
        db = session_factory()
        when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        log = HikeLog(user_id=who["id"], trail_id=trails[next(used) % len(trails)], hiked_on=TODAY,
                      created_at=when)
        db.add(log)
        db.flush()
        row = ActivityPost(user_id=who["id"], kind="hike", hike_log_id=log.id, created_at=when, **fields)
        db.add(row)
        db.commit()
        post_id = row.id
        db.close()
        return post_id

    return _post


def add(session_factory, *rows):
    db = session_factory()
    db.add_all(rows)
    db.commit()
    db.close()


def follow(session_factory, viewer, *others):
    add(session_factory, *(Follow(follower_id=viewer["id"], followee_id=o["id"], status="accepted") for o in others))


def get(client, who=None, **params):
    response = client.get("/api/activity", params=params, headers=(who or {}).get("headers", {}))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def everything(client, who=None, limit=10):
    """Every page, in order."""
    pages, cursor = [], None
    while True:
        body = get(client, who, limit=limit, **({"cursor": cursor} if cursor else {}))
        pages.append(body)
        cursor = body["next_cursor"]
        if cursor is None:
            return pages


def ids(pages):
    return [item["id"] for page in pages for item in page["items"]]


@pytest.fixture
def crowd(person, post):
    """Twelve hikers with three posts each."""
    hikers = [person(f"hiker{n}") for n in range(12)]
    for n, hiker in enumerate(hikers):
        for k in range(3):
            post(hiker, hours_ago=n + k * 20)
    return hikers


@pytest.mark.parametrize("following", [0, 3, 12])
def test_a_full_first_page_whoever_you_follow(client, session_factory, person, crowd, following):
    viewer = person("viewer")
    follow(session_factory, viewer, *crowd[:following])
    body = get(client, viewer, limit=10)
    posts_on_page = [e for e in body["entries"] if e["type"] == "post"]
    assert len(posts_on_page) >= 9 and len(body["entries"]) == 10
    assert len(body["items"]) == len(posts_on_page)
    assert body["next_cursor"]
    reasons = {item["reason"] for item in body["items"]}
    if following == 0:
        assert reasons == {"suggested"} and body["follows_anyone"] is False
        assert "caught_up" not in [e["type"] for e in body["entries"]]
    else:
        assert body["items"][0]["reason"] == "following" and body["follows_anyone"] is True
    if following == 12:
        # Following everyone: the whole page is theirs.
        assert reasons == {"following"}


def test_guests_get_a_full_first_page_too(client, crowd):
    body = get(client, limit=10)
    assert len(body["items"]) == 10 and body["suggested_hikers"] is None
    assert all(item["author"]["follow"] is None for item in body["items"])


def test_no_post_twice_across_pages(client, session_factory, person, crowd, post):
    viewer = person("viewer")
    follow(session_factory, viewer, *crowd[:4])
    first = get(client, viewer, limit=10)
    # A post made after the first page doesn't push the rest along.
    late = post(crowd[0], hours_ago=0)
    pages = [first]
    cursor = first["next_cursor"]
    while cursor:
        body = get(client, viewer, limit=10, cursor=cursor)
        pages.append(body)
        cursor = body["next_cursor"]
    seen = ids(pages)
    assert len(seen) == len(set(seen)) == 36
    assert late not in seen
    # Exactly one divider in all, and entries match items page by page.
    assert sum(e["type"] == "caught_up" for p in pages for e in p["entries"]) == 1
    for page in pages:
        assert [e["post_id"] for e in page["entries"] if e["type"] == "post"] == [i["id"] for i in page["items"]]


def test_the_caught_up_divider_follows_the_last_fresh_followed_post(client, session_factory, person, post):
    viewer, friend, stranger = person("viewer"), person("friend"), person("stranger")
    follow(session_factory, viewer, friend)
    new = [post(friend, hours_ago=h) for h in (1, 2)]
    old = post(friend, hours_ago=24 * 30)
    strangers = [post(stranger, hours_ago=h) for h in (0.5, 3)]
    body = get(client, viewer)
    order = [e["post_id"] if e["type"] == "post" else "divider" for e in body["entries"]]
    divider = order.index("divider")
    assert [o for o in order[:divider] if o in map(str, new)] == [str(n) for n in new]
    assert str(old) in order[divider:]
    assert set(map(str, strangers)) <= set(order)


def test_your_own_posts_are_in_your_feed(client, person, post):
    me = person("myself")
    mine = post(me, hours_ago=1)
    body = get(client, me)
    assert body["items"][0]["id"] == str(mine) and body["items"][0]["reason"] == "own"
    assert body["items"][0]["mine"] is True


def test_new_posts_count_since_the_page_was_made(client, session_factory, person, post):
    viewer, friend, stranger = person("viewer"), person("friend"), person("stranger")
    follow(session_factory, viewer, friend)
    post(friend, hours_ago=2)
    as_of = get(client, viewer)["as_of"]

    def count(who=viewer):
        response = client.get("/api/activity/new", params={"since": as_of}, headers=(who or {}).get("headers", {}))
        assert response.status_code == 200
        return response.json()["count"]

    assert count() == 0
    post(friend, hours_ago=-0.01)
    post(stranger, hours_ago=-0.01)  # not followed
    post(viewer, hours_ago=-0.01)  # your own
    assert count() == 1
    assert count(None) == 0


def test_bad_cursor_is_a_422(client):
    assert client.get("/api/activity", params={"cursor": "garbage"}).status_code == 422


# ------------------------------------------------------------ who may appear


def authors(body):
    return {item["author"]["username"] for item in body["items"]}


def test_only_sharing_public_listed_authors_appear(client, session_factory, person, post):
    viewer = person("viewer")
    shown = person("shown")
    quiet = person("quiet", share=False)
    private = person("private", is_private=True)
    journal_off = person("journaloff", show_journal=False)
    hidden = person("hidden")
    for who in (shown, quiet, private, journal_off, hidden):
        post(who)
    add(session_factory, ProfileModeration(user_id=hidden["id"]))
    # Even an approved follower of a private profile doesn't get its posts.
    follow(session_factory, viewer, private)
    assert authors(get(client, viewer)) == {"shown"}
    assert authors(get(client)) == {"shown"}


def test_hidden_and_held_posts_never_appear(client, person, post):
    viewer, author = person("viewer"), person("author")
    kept = post(author)
    post(author, hidden_at=datetime.now(timezone.utc), hidden_reason="admin")
    post(author, hidden_at=datetime.now(timezone.utc), hidden_reason="Held for review")
    assert [item["id"] for item in get(client, viewer)["items"]] == [str(kept)]


def test_blocks_hide_posts_both_ways(client, session_factory, person, post):
    viewer, blocked, blocker, other = person("viewer"), person("blocked"), person("blocker"), person("other")
    for who in (blocked, blocker, other):
        post(who)
    post(viewer)
    add(session_factory, Block(blocker_id=viewer["id"], blocked_id=blocked["id"]),
        Block(blocker_id=blocker["id"], blocked_id=viewer["id"]))
    assert authors(get(client, viewer)) == {"viewer", "other"}
    # The blocker doesn't see the viewer either.
    assert "viewer" not in authors(get(client, blocker))
    # Nobody else is affected.
    assert authors(get(client)) == {"viewer", "blocked", "blocker", "other"}


def test_hidden_dates_stay_hidden(client, person, post):
    viewer, shy = person("viewer"), person("shy", hide_hike_dates=True)
    post(shy)
    item = get(client, viewer)["items"][0]
    assert item["posted_at"] is None and item["hike"]["hiked_on"] is None


def test_demo_accounts_show_badged_and_last(client, session_factory, person, post):
    viewer, real, demo = person("viewer"), person("real"), person("demo")
    add(session_factory, AccountLabel(user_id=demo["id"], label="demo"))
    for _ in range(3):
        post(demo, hours_ago=0.1)  # newer than the real hiker's
    post(real, hours_ago=24 * 20)
    items = get(client, viewer)["items"]
    assert items[0]["author"]["username"] == "real"
    assert {i["author"]["label"] for i in items[1:]} == {"demo"} and {i["reason"] for i in items[1:]} == {"demo"}


def test_suggested_posts_offer_a_follow(client, person, post):
    viewer, author = person("viewer"), person("author")
    post(author)
    item = get(client, viewer)["items"][0]
    assert item["reason"] == "suggested" and item["author"]["follow"] == "none"


# ------------------------------------------------------------ the follow card


def test_following_nobody_offers_three_hikers(client, session_factory, person, crowd):
    viewer = person("viewer")
    add(session_factory, Follow(follower_id=viewer["id"], followee_id=crowd[0]["id"], status="pending"))
    body = get(client, viewer)
    hikers = body["suggested_hikers"]
    assert len(hikers) == 3
    names = [h["username"] for h in hikers]
    assert len(set(names)) == 3 and "hiker0" not in names and "viewer" not in names
    assert all(h["follow"] == "none" for h in hikers)
    # Not on later pages, and not once they follow someone.
    assert get(client, viewer, cursor=body["next_cursor"])["suggested_hikers"] is None
    follow(session_factory, viewer, crowd[1])
    assert get(client, viewer)["suggested_hikers"] is None


def test_the_follow_card_puts_database_suggestions_first(client, person, crowd):
    viewer = person("viewer")
    pick = crowd[7]

    class One:
        def suggest(self, db, viewer_id, limit):
            from app.hiker_search import Suggestion
            return [Suggestion(pick["id"], 2, False)]

    app.dependency_overrides[get_feed_finder] = lambda: One()
    hikers = get(client, viewer)["suggested_hikers"]
    assert hikers[0]["username"] == "hiker7" and hikers[0]["common_trails"] == 2
    assert len(hikers) == 3
