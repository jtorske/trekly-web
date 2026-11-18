"""People search and suggestions in the database (migration e6b2d8a4c0f7),
checked against the local Supabase stack: matching (prefixes, accents,
typos), ranking, every rule for who may appear, and the client grants.

Opt-in and local-only, like test_profile_privacy_policies.py: set
LOCAL_SUPABASE_DB_URL to the CLI stack's Postgres. Every test runs in a
transaction that is rolled back. The local database has other people in it,
so each check looks only at the users the test made.
"""

import uuid

import pytest
from sqlalchemy import text

from tests.test_profile_privacy_policies import (  # noqa: F401  (fixtures)
    DB_URL, act_as, as_admin, conn, engine, refused, rows,
)

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")


class World:
    def __init__(self, conn):
        self.conn = conn
        self.tag = uuid.uuid4().hex[:6]
        self.ids: dict[str, uuid.UUID] = {}
        self.viewer = self.user("viewer", f"viewer_{self.tag}", "Viewer")

    def user(self, key, username, display_name=None, **settings):
        as_admin(self.conn)
        user_id = uuid.uuid4()
        self.conn.execute(
            text("INSERT INTO auth.users (id, aud, role, email) VALUES (:id, 'authenticated', 'authenticated', :e)"),
            {"id": user_id, "e": f"{user_id}@search-test.local"},
        )
        self.conn.execute(
            text("UPDATE public.profiles SET username = :u, display_name = :d WHERE id = :id"),
            {"u": username, "d": display_name, "id": user_id},
        )
        if settings:
            self.settings(user_id, **settings)
        self.ids[key] = user_id
        return user_id

    def settings(self, user_id, **values):
        as_admin(self.conn)
        sets = ", ".join(f"{column} = :{column}" for column in values)
        self.conn.execute(text(f"UPDATE public.profile_settings SET {sets} WHERE user_id = :id"), {**values, "id": user_id})

    def province(self, user_id, code, shown=True):
        as_admin(self.conn)
        self.conn.execute(text("UPDATE public.profiles SET home_province = :p WHERE id = :id"), {"p": code, "id": user_id})
        self.settings(user_id, show_home_province=shown)

    def trail(self):
        as_admin(self.conn)
        return self.conn.execute(
            text("INSERT INTO public.trails (id, name, slug, region, country_code, terrain_difficulty) "
                 "VALUES (gen_random_uuid(), :n, 'search-test-trail-' || gen_random_uuid(), 'Search Test Park', 'CA', 'easy') RETURNING id"),
            {"n": f"Search test trail {uuid.uuid4()}"},
        ).scalar_one()

    def hiked(self, user_id, trail, on="2026-08-01"):
        as_admin(self.conn)
        self.conn.execute(
            text("INSERT INTO public.hike_logs (user_id, trail_id, hiked_on) VALUES (:u, :t, :d)"),
            {"u": user_id, "t": trail, "d": on},
        )

    def follow(self, follower, followee, status="accepted"):
        as_admin(self.conn)
        self.conn.execute(
            text("INSERT INTO public.follows (follower_id, followee_id, status) VALUES (:a, :b, :s)"),
            {"a": follower, "b": followee, "s": status},
        )

    def block(self, blocker, blocked):
        as_admin(self.conn)
        self.conn.execute(text("INSERT INTO public.blocks (blocker_id, blocked_id) VALUES (:a, :b)"), {"a": blocker, "b": blocked})

    def label(self, user_id, label):
        as_admin(self.conn)
        if label == "official":  # only one may exist; the local stack has @trekly
            self.conn.execute(text("DELETE FROM public.account_labels WHERE label = 'official'"))
        self.conn.execute(text("INSERT INTO public.account_labels (user_id, label) VALUES (:u, :l)"), {"u": user_id, "l": label})

    def _names(self):
        return {user_id: key for key, user_id in self.ids.items()}

    def search(self, q, viewer=None, limit=50):
        """The test's own users the search finds, in order: [(key, tier, common_trails, opened)]."""
        as_admin(self.conn)
        names = self._names()
        found = rows(
            self.conn,
            "SELECT user_id, tier, common_trails, opened FROM private.search_hikers(:v, :q, :n, 0)",
            {"v": viewer or self.viewer, "q": q, "n": limit},
        )
        return [(names[r.user_id], r.tier, r.common_trails, r.opened) for r in found if r.user_id in names]

    def keys(self, q, viewer=None):
        return [hit[0] for hit in self.search(q, viewer)]

    def suggest(self, viewer=None):
        as_admin(self.conn)
        names = self._names()
        found = rows(self.conn, "SELECT user_id, common_trails, same_province FROM private.suggest_hikers(:v, 20)",
                     {"v": viewer or self.viewer})
        return [(names[r.user_id], r.common_trails, r.same_province) for r in found if r.user_id in names]


@pytest.fixture
def world(conn):  # noqa: F811
    return World(conn)


# ------------------------------------------------------------------ matching

def test_prefix_of_a_username(world):
    world.user("jordan", f"jordan_{world.tag}", "Jordan Torske")
    assert world.keys("jor") == ["jordan"]
    assert world.keys(f"jordan_{world.tag}") == ["jordan"]


def test_a_word_of_the_display_name(world):
    world.user("jordan", f"jt_{world.tag}", "Jordan Torske")
    assert world.keys("torske") == ["jordan"]
    assert world.keys("Jordan T") == ["jordan"]


def test_case_and_accents_are_ignored(world):
    world.user("joelle", f"jo_{world.tag}", "Joëlle Bédard")
    for q in ("Joelle", "joëlle", "JOELLE", "bedard", "BÉDARD", "joel"):
        assert world.keys(q) == ["joelle"], q


def test_accented_queries_find_plain_names(world):
    world.user("rene", f"rene_{world.tag}", "Rene Lavoie")
    assert world.keys("René") == ["rene"]


def test_typos_still_match(world):
    world.user("jordan", f"jordan_{world.tag}", "Jordan Torske")
    assert world.keys("jordna") == ["jordan"]  # swapped letters at the end
    assert world.keys("jordn") == ["jordan"]  # a letter missing
    assert world.keys("torskee") == ["jordan"]  # a letter too many


def test_a_leading_at_sign_is_ignored(world):
    world.user("jordan", f"jordan_{world.tag}")
    assert world.keys(f"@jordan_{world.tag}") == ["jordan"]
    assert world.search(f"@jordan_{world.tag}")[0][1] == 0  # still the exact username


def test_two_characters_at_least(world):
    world.user("jordan", f"jordan_{world.tag}")
    assert world.keys("j") == []
    assert world.keys(" @j ") == []
    assert world.keys("jo") == ["jordan"]


def test_like_wildcards_are_literal(world):
    world.user("jordan", f"jordan_{world.tag}", "Jordan")
    assert world.keys("%%") == []
    assert world.keys("__") == []
    assert world.keys("j%n") == []


def test_unrelated_names_dont_match(world):
    world.user("jordan", f"jordan_{world.tag}", "Jordan Torske")
    assert world.keys("mountain") == []


def test_pages_with_limit_and_offset(world):
    for n in range(5):
        world.user(f"p{n}", f"pager{n}_{world.tag}")
    as_admin(world.conn)
    names = world._names()
    pages = [
        [names[r.user_id] for r in rows(world.conn, "SELECT user_id FROM private.search_hikers(:v, :q, 2, :o)",
                                       {"v": world.viewer, "q": f"_{world.tag}", "o": offset}) if r.user_id in names]
        for offset in (0, 2, 4)
    ]
    assert pages == [["p0", "p1"], ["p2", "p3"], ["p4"]]


def test_the_name_indexes_serve_the_search(world):
    as_admin(world.conn)
    world.conn.execute(text("SET LOCAL enable_seqscan = off"))
    for column, index in (("username", "profiles_username_search_idx"), ("display_name", "profiles_display_name_search_idx")):
        plan = "\n".join(r[0] for r in rows(
            world.conn,
            f"EXPLAIN SELECT id FROM public.profiles WHERE username IS NOT NULL "
            f"AND private.search_fold({column}) LIKE '%torske%'",
        ))
        assert index in plan, plan


# ------------------------------------------------------------------- ranking

def test_ranking_exact_then_followed_then_in_common_then_the_rest(world):
    p = f"rk{world.tag}"
    viewer = world.viewer
    world.province(viewer, "AB")
    trail = world.trail()
    world.hiked(viewer, trail)

    world.user("rest", f"{p}_r")
    world.user("hidden_journal", f"{p}_h", show_journal=False)  # shares a trail, but you can't see it
    world.hiked(world.ids["hidden_journal"], trail)
    world.user("province", f"{p}_p")
    world.province(world.ids["province"], "AB")
    world.user("trail", f"{p}_t")
    world.hiked(world.ids["trail"], trail)
    world.user("followed", f"{p}_f")
    world.follow(viewer, world.ids["followed"])
    world.user("exact", p)

    assert world.search(p) == [
        ("exact", 0, 0, True),
        ("followed", 1, 0, True),
        ("trail", 2, 1, True),
        ("province", 2, 0, True),
        ("hidden_journal", 3, None, True),
        ("rest", 3, 0, True),
    ]


def test_a_better_match_ranks_higher_within_a_tier(world):
    world.user("fuzzy", f"x_{world.tag}", "Jordna Smith")
    world.user("prefix", f"jordan_{world.tag}")
    world.user("word", f"y_{world.tag}", "Ann Jordan")
    assert world.keys("jordan") == ["prefix", "word", "fuzzy"]


def test_more_trails_in_common_ranks_higher(world):
    trails = [world.trail() for _ in range(3)]
    for trail in trails:
        world.hiked(world.viewer, trail)
    world.user("one", f"cmn_a_{world.tag}")
    world.user("three", f"cmn_b_{world.tag}")
    world.hiked(world.ids["one"], trails[0])
    for trail in trails:
        world.hiked(world.ids["three"], trail)
    assert [(k, c) for k, _, c, _ in world.search(f"cmn_")] == [("three", 3), ("one", 1)]


def test_a_hidden_province_isnt_in_common(world):
    world.province(world.viewer, "BC")
    world.user("hidden", f"prov_{world.tag}")
    world.province(world.ids["hidden"], "BC", shown=False)
    assert world.search(f"prov_{world.tag}")[0][1] == 0  # exact, but:
    assert world.search("prov_")[0][1] == 3


def test_future_hikes_arent_in_common(world):
    trail = world.trail()
    world.hiked(world.viewer, trail)
    world.user("later", f"later_{world.tag}")
    world.hiked(world.ids["later"], trail, on="2099-01-01")
    assert world.search("later_")[0][2] == 0


# ------------------------------------------------------------ who may appear

def test_public_profiles_are_always_searchable(world):
    world.user("public", f"pub_{world.tag}", findable_in_search=False)
    assert world.keys(f"pub_{world.tag}") == ["public"]


def test_private_profiles_only_when_findable(world):
    world.user("private", f"priv_{world.tag}", is_private=True)
    assert world.keys(f"priv_{world.tag}") == []
    world.settings(world.ids["private"], findable_in_search=True)
    assert world.search(f"priv_{world.tag}") == [("private", 0, None, False)]


def test_a_findable_private_profile_shows_nothing_in_common(world):
    trail = world.trail()
    world.hiked(world.viewer, trail)
    world.province(world.viewer, "ON")
    world.user("private", f"priv_{world.tag}", is_private=True, findable_in_search=True)
    world.hiked(world.ids["private"], trail)
    world.province(world.ids["private"], "ON")
    assert world.search("priv_") == [("private", 3, None, False)]


def test_an_approved_follower_sees_a_private_profile_opened(world):
    trail = world.trail()
    world.hiked(world.viewer, trail)
    world.user("private", f"priv_{world.tag}", is_private=True, findable_in_search=True)
    world.hiked(world.ids["private"], trail)
    world.follow(world.viewer, world.ids["private"])
    assert world.search("priv_") == [("private", 1, 1, True)]


def test_a_pending_request_doesnt_open_a_private_profile(world):
    world.user("private", f"priv_{world.tag}", is_private=True, findable_in_search=True)
    world.follow(world.viewer, world.ids["private"], status="pending")
    assert world.search("priv_") == [("private", 3, None, False)]


def test_profiles_hidden_by_admins_never_appear(world):
    hidden = world.user("hidden", f"hid_{world.tag}")
    as_admin(world.conn)
    world.conn.execute(text("INSERT INTO public.profile_moderation (user_id) VALUES (:u)"), {"u": hidden})
    assert world.keys(f"hid_{world.tag}") == []


@pytest.mark.parametrize("label", ["demo", "official"])
def test_labeled_accounts_never_appear(world, label):
    labeled = world.user("labeled", f"lab_{world.tag}")
    world.label(labeled, label)
    assert world.keys(f"lab_{world.tag}") == []


def test_blocks_hide_people_both_ways(world):
    blocked = world.user("blocked", f"blk_a_{world.tag}")
    blocker = world.user("blocker", f"blk_b_{world.tag}")
    world.block(world.viewer, blocked)
    world.block(blocker, world.viewer)
    assert world.keys("blk_") == []
    # Only for the two people involved.
    other = world.user("other", f"other_{world.tag}")
    assert world.keys("blk_", viewer=other) == ["blocked", "blocker"]


def test_accounts_without_a_username_never_appear(world):
    as_admin(world.conn)
    nameless = uuid.uuid4()
    world.conn.execute(
        text("INSERT INTO auth.users (id, aud, role, email) VALUES (:id, 'authenticated', 'authenticated', :e)"),
        {"id": nameless, "e": f"{nameless}@search-test.local"},
    )
    world.conn.execute(text("UPDATE public.profiles SET display_name = :d WHERE id = :id"),
                       {"d": f"Nameless {world.tag}", "id": nameless})
    world.ids["nameless"] = nameless
    assert world.keys(f"Nameless {world.tag}") == []


def test_you_never_find_yourself(world):
    assert world.keys(f"viewer_{world.tag}") == []


# --------------------------------------------------------------- suggestions

def test_suggestions_from_home_province_and_trails_in_common(world):
    world.province(world.viewer, "AB")
    trails = [world.trail(), world.trail()]
    for trail in trails:
        world.hiked(world.viewer, trail)
    community = {"show_in_community": True}

    world.user("province", f"s_prov_{world.tag}", **community)
    world.province(world.ids["province"], "AB")
    world.user("two_trails", f"s_two_{world.tag}", **community)
    for trail in trails:
        world.hiked(world.ids["two_trails"], trail)
    world.user("one_trail", f"s_one_{world.tag}", **community)
    world.hiked(world.ids["one_trail"], trails[0])
    world.user("stranger", f"s_none_{world.tag}", **community)  # nothing in common

    assert world.suggest() == [("two_trails", 2, False), ("one_trail", 1, False), ("province", 0, True)]


def test_suggestions_need_community_features_on(world):
    world.province(world.viewer, "AB")
    cases = {
        "not_opted_in": {"show_in_community": False},
        "journal_hidden": {"show_in_community": True, "show_journal": False},
        "private": {"show_in_community": True, "is_private": True, "findable_in_search": True},
    }
    for key, settings in cases.items():
        world.user(key, f"{key}_{world.tag}", **settings)
        world.province(world.ids[key], "AB")
    assert world.suggest() == []


def test_suggestions_leave_out_followed_blocked_labeled_and_hidden_provinces(world):
    world.province(world.viewer, "AB")
    community = {"show_in_community": True}
    for key in ("followed", "blocked", "blocker", "demo", "hidden_province"):
        world.user(key, f"{key}_{world.tag}", **community)
        world.province(world.ids[key], "AB", shown=key != "hidden_province")
    world.follow(world.viewer, world.ids["followed"])
    world.block(world.viewer, world.ids["blocked"])
    world.block(world.ids["blocker"], world.viewer)
    world.label(world.ids["demo"], "demo")
    assert world.suggest() == []


def test_outside_canada_isnt_a_province_in_common(world):
    world.province(world.viewer, "outside")
    world.user("abroad", f"abroad_{world.tag}", show_in_community=True)
    world.province(world.ids["abroad"], "outside")
    assert world.suggest() == []


# ------------------------------------------------------------ client access

def test_clients_cant_call_the_search_functions(world):
    for who in (None, world.viewer):
        act_as(world.conn, who)
        assert refused(world.conn, "SELECT * FROM private.search_hikers(:v, 'jo', 10, 0)", {"v": world.viewer})
        assert refused(world.conn, "SELECT * FROM private.suggest_hikers(:v, 10)", {"v": world.viewer})
    as_admin(world.conn)


def test_blocks_are_readable_only_by_the_blocker(world):
    other = world.user("other", f"other_{world.tag}")
    world.block(world.viewer, other)
    query = "SELECT blocker_id, blocked_id FROM public.blocks WHERE blocked_id = :b OR blocker_id = :b"
    act_as(world.conn, world.viewer)
    assert len(rows(world.conn, query, {"b": world.viewer})) == 1
    act_as(world.conn, other)
    assert rows(world.conn, query, {"b": other}) == []
    act_as(world.conn, None)
    assert refused(world.conn, query, {"b": other})


def test_clients_cant_write_blocks(world):
    other = world.user("other", f"other_{world.tag}")
    act_as(world.conn, world.viewer)
    assert refused(world.conn, "INSERT INTO public.blocks (blocker_id, blocked_id) VALUES (:a, :b)",
                   {"a": world.viewer, "b": other})
    world.block(world.viewer, other)
    act_as(world.conn, world.viewer)
    assert refused(world.conn, "DELETE FROM public.blocks WHERE blocker_id = :a", {"a": world.viewer})
    as_admin(world.conn)


def test_users_switch_findable_on_for_themselves_only(world):
    other = world.user("other", f"other_{world.tag}")
    act_as(world.conn, world.viewer)
    world.conn.execute(text("UPDATE public.profile_settings SET findable_in_search = true WHERE user_id IN (:a, :b)"),
                       {"a": world.viewer, "b": other})
    as_admin(world.conn)
    found = dict(rows(world.conn, "SELECT user_id, findable_in_search FROM public.profile_settings WHERE user_id IN (:a, :b)",
                      {"a": world.viewer, "b": other}))
    assert found == {world.viewer: True, other: False}
