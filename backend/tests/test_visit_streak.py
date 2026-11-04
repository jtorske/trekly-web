"""Visit streaks: the rules (app/streaks.py), the time zone handling, POST
/api/me/visit, and who may see a streak (Settings → Privacy, off by default,
enforced by the API)."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.visit_streak import VisitStreak
from app.routers import me_visit
from app.streaks import NO_STREAK, Streak, current_on, earliest_today, local_today, record_visit

VISIT = "/api/me/visit"
PRIVACY = "/api/me/privacy"
PROFILE = "/api/me/profile"
EDMONTON = "America/Edmonton"
MON = date(2026, 11, 2)


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


# ------------------------------------------------------------- the rules


def visits(*days: date) -> tuple[Streak, list[bool]]:
    streak, grew = NO_STREAK, []
    for day in days:
        streak, g = record_visit(streak, day)
        grew.append(g)
    return streak, grew


def test_the_first_visit_starts_a_streak_of_one():
    streak, grew = visits(MON)
    assert streak == Streak(current=1, longest=1, last_visit=MON) and grew == [True]


def test_consecutive_days_add_one_each():
    streak, grew = visits(*(MON + timedelta(days=i) for i in range(5)))
    assert (streak.current, streak.longest) == (5, 5)
    assert grew == [True] * 5


def test_repeat_visits_on_the_same_day_change_nothing():
    first, _ = visits(MON, MON + timedelta(days=1))
    again, grew = record_visit(first, MON + timedelta(days=1))
    assert again == first and grew is False


def test_a_gap_of_two_days_or_more_resets_to_one():
    for gap in (2, 3, 30):
        streak, grew = visits(MON, MON + timedelta(days=1), MON + timedelta(days=1 + gap))
        assert streak.current == 1, gap
        assert streak.longest == 2
        assert grew[-1] is False  # 2 → 1 isn't growth


def test_the_longest_streak_is_kept_and_raised_only_when_passed():
    days = [MON + timedelta(days=i) for i in (0, 1, 2, 10, 11)]
    streak, _ = visits(*days)
    assert (streak.current, streak.longest) == (2, 3)
    streak, _ = visits(*days, MON + timedelta(days=12), MON + timedelta(days=13))
    assert (streak.current, streak.longest) == (4, 4)


def test_an_earlier_date_than_the_last_visit_changes_nothing():
    # E.g. flying west across the date line: never reset, never go backwards.
    streak, _ = visits(MON, MON + timedelta(days=1))
    assert record_visit(streak, MON) == (streak, False)


def test_a_lapsed_streak_reads_as_zero_until_the_next_visit():
    streak, _ = visits(MON, MON + timedelta(days=1))
    assert current_on(streak, MON + timedelta(days=1)) == 2
    assert current_on(streak, MON + timedelta(days=2)) == 2  # still alive: today would continue it
    assert current_on(streak, MON + timedelta(days=3)) == 0
    assert current_on(NO_STREAK, MON) == 0


# ------------------------------------------------------------ time zones


def test_today_is_the_date_in_the_users_time_zone():
    # 05:30 UTC on Tuesday is still Monday evening in Edmonton (Alberta Time, UTC-6 all year from 2026).
    assert local_today(EDMONTON, utc(2026, 11, 3, 5, 30)) == date(2026, 11, 2)
    assert local_today(EDMONTON, utc(2026, 11, 3, 6, 0)) == date(2026, 11, 3)  # midnight there
    assert local_today("UTC", utc(2026, 11, 3, 5, 30)) == date(2026, 11, 3)


def test_just_before_and_after_local_midnight_are_two_days():
    before = local_today(EDMONTON, utc(2026, 11, 3, 5, 59, 59))
    after = local_today(EDMONTON, utc(2026, 11, 3, 6, 0, 0))
    assert after - before == timedelta(days=1)
    streak, grew = visits(before, after)
    assert streak.current == 2 and grew == [True, True]


def test_daylight_saving_changes_are_followed():
    # Toronto falls back on 1 November 2026 (UTC-4 → UTC-5): 04:30 UTC is past midnight before, not after.
    assert local_today("America/Toronto", utc(2026, 10, 31, 4, 30)) == date(2026, 10, 31)
    assert local_today("America/Toronto", utc(2026, 11, 3, 4, 30)) == date(2026, 11, 2)


def test_zone_rules_come_from_the_current_tzdata():
    # Alberta stopped falling back in November 2026 (tzdata 2026f); an older
    # copy would put this an hour earlier, on the 3rd.
    assert local_today(EDMONTON, utc(2026, 11, 4, 6, 30)) == date(2026, 11, 4)


@pytest.mark.parametrize("zone", [None, "", "Not/AZone", "../../etc/passwd", "/etc/localtime", "America/Edmonton\x00", "x" * 65])
def test_missing_or_unknown_time_zones_count_as_utc(zone):
    assert local_today(zone, utc(2026, 11, 3, 5, 30)) == date(2026, 11, 3)


def test_the_extreme_real_zones_stay_within_a_day_of_utc():
    now = utc(2026, 11, 3, 11, 30)
    assert local_today("Pacific/Kiritimati", now) == date(2026, 11, 4)  # UTC+14
    assert local_today("Etc/GMT+12", now) == date(2026, 11, 2)  # UTC-12


def test_the_date_is_clamped_to_one_day_either_side_of_utc(monkeypatch):
    # A zone further than a day from UTC (no real one is) can't move the date more than a day.
    from app import streaks

    far_east = timezone(timedelta(hours=23, minutes=59))
    monkeypatch.setattr(streaks, "valid_time_zone", lambda name: far_east if name == "east" else timezone(-timedelta(hours=23, minutes=59)))
    now = utc(2026, 11, 3, 23, 0)  # far_east: 4 Nov 22:59, a day and a bit ahead
    assert local_today("east", now) == date(2026, 11, 4)
    assert local_today("west", utc(2026, 11, 3, 0, 30)) == date(2026, 11, 2)


def test_a_changed_time_zone_cant_add_days_beyond_one():
    # Hopping zones within one real day: at most one extra day either way, never more.
    now = utc(2026, 11, 3, 11, 30)
    days = {local_today(zone, now) for zone in ("Etc/GMT+12", "UTC", "Pacific/Kiritimati", "Asia/Tokyo")}
    assert min(days) >= now.date() - timedelta(days=1)
    assert max(days) <= now.date() + timedelta(days=1)


def test_visitors_see_a_streak_as_lapsed_only_once_it_has_lapsed_everywhere():
    streak = Streak(current=5, longest=5, last_visit=date(2026, 11, 2))
    # 3 Nov 11:30 UTC is 4 Nov in Kiritimati, but 2 Nov at UTC-12: still alive somewhere.
    assert current_on(streak, earliest_today(utc(2026, 11, 4, 11, 30))) == 5
    assert current_on(streak, earliest_today(utc(2026, 11, 5, 0, 30))) == 0


# --------------------------------------------------------------- the API


class Clock:
    def __init__(self, monkeypatch, start: datetime):
        self.value = start
        monkeypatch.setattr(me_visit, "now", lambda: self.value)

    def advance(self, **delta):
        self.value += timedelta(**delta)


@pytest.fixture
def clock(monkeypatch):
    # 19:00 in Edmonton on Monday 2 November.
    return Clock(monkeypatch, utc(2026, 11, 3, 1, 0))


@pytest.fixture
def people(make_token):
    def person():
        return {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}

    return {"alice": person(), "bob": person()}


def visit(client, who, zone=EDMONTON, **extra):
    response = client.post(VISIT, json={"time_zone": zone, **extra}, headers=who)
    assert response.status_code == 200, response.text
    return response.json()


def test_signing_in_is_required(client):
    assert client.post(VISIT, json={"time_zone": EDMONTON}).status_code == 401


def test_the_first_visit_counts_one_for_the_local_date(client, people, clock):
    body = visit(client, people["alice"])
    assert body == {"current_streak": 1, "longest_streak": 1, "today": "2026-11-02", "grew": True}


def test_visits_on_consecutive_days_build_the_streak(client, people, clock):
    for expected in (1, 2, 3):
        assert visit(client, people["alice"])["current_streak"] == expected
        clock.advance(days=1)


def test_repeat_calls_the_same_day_change_nothing(client, people, clock, db):
    visit(client, people["alice"])
    clock.advance(days=1)
    first = visit(client, people["alice"])
    clock.advance(hours=3)  # 22:00 Tuesday in Edmonton, the same day
    again = visit(client, people["alice"])
    assert first["grew"] is True and again["grew"] is False
    assert again["current_streak"] == first["current_streak"] == 2


def test_a_missed_day_resets_to_one_and_keeps_the_best(client, people, clock):
    visit(client, people["alice"])
    clock.advance(days=1)
    visit(client, people["alice"])
    clock.advance(days=2)
    body = visit(client, people["alice"])
    assert (body["current_streak"], body["longest_streak"], body["grew"]) == (1, 2, False)


def test_late_evening_and_early_morning_local_time_are_consecutive_days(client, people, clock):
    clock.value = utc(2026, 11, 3, 5, 50)  # 23:50 Monday in Edmonton (05:50 Tuesday UTC)
    assert visit(client, people["alice"])["today"] == "2026-11-02"
    clock.advance(minutes=20)  # 00:10 Tuesday in Edmonton
    body = visit(client, people["alice"])
    assert (body["today"], body["current_streak"]) == ("2026-11-03", 2)


def test_the_utc_date_alone_would_have_merged_those_visits(client, people, clock):
    # The same two moments, sent without a zone: both are Tuesday in UTC.
    clock.value = utc(2026, 11, 3, 5, 50)
    visit(client, people["alice"], zone=None)
    clock.advance(minutes=20)
    assert visit(client, people["alice"], zone=None)["current_streak"] == 1


def test_switching_zones_cant_add_more_than_a_day(client, people, clock):
    clock.value = utc(2026, 11, 3, 11, 30)
    visit(client, people["alice"], zone="Etc/GMT+12")  # 2 Nov
    visit(client, people["alice"], zone="UTC")  # 3 Nov
    visit(client, people["alice"], zone="Pacific/Kiritimati")  # 4 Nov
    body = visit(client, people["alice"], zone="Pacific/Kiritimati")
    assert body["current_streak"] == 3  # never more than the dates a day either side of UTC allow
    # Going back west the same day: no change, no reset.
    back = visit(client, people["alice"], zone="Etc/GMT+12")
    assert (back["current_streak"], back["grew"]) == (3, False)


def test_counts_sent_by_the_browser_are_refused(client, people, clock):
    response = client.post(VISIT, json={"time_zone": EDMONTON, "current_streak": 99}, headers=people["alice"])
    assert response.status_code == 422


def test_an_overlong_time_zone_is_refused(client, people, clock):
    assert client.post(VISIT, json={"time_zone": "x" * 65}, headers=people["alice"]).status_code == 422


def test_each_user_has_their_own_streak(client, people, clock):
    visit(client, people["alice"])
    clock.advance(days=1)
    visit(client, people["alice"])
    assert visit(client, people["bob"])["current_streak"] == 1


def test_only_the_date_and_two_counts_are_stored(client, people, clock, db):
    visit(client, people["alice"])
    clock.advance(days=1)
    visit(client, people["alice"])
    rows = db.query(VisitStreak).all()
    assert len(rows) == 1
    assert set(VisitStreak.__table__.columns.keys()) == {"user_id", "current_streak", "longest_streak", "last_visit_date"}
    assert (rows[0].current_streak, rows[0].longest_streak, rows[0].last_visit_date) == (2, 2, date(2026, 11, 3))


def test_deleting_the_account_deletes_the_streak(client, people, clock, db):
    visit(client, people["alice"])
    response = client.request("DELETE", "/api/me", json={"confirm": "delete my account"}, headers=people["alice"])
    assert response.status_code == 204, response.text
    assert db.query(VisitStreak).count() == 0


# ------------------------------------------------------------ privacy


@pytest.fixture
def alice(client, people, clock):
    """A public profile with a 3-day streak (best 3)."""
    who = people["alice"]
    assert client.patch(PROFILE, json={"username": "alice"}, headers=who).status_code == 200
    settings = client.get(PRIVACY, headers=who).json()
    assert settings["is_private"] is False
    for _ in range(3):
        visit(client, who)
        clock.advance(days=1)
    return who


def public(client, headers=None):
    response = client.get("/api/profiles/alice", headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def set_privacy(client, who, **changes):
    response = client.patch(PRIVACY, json=changes, headers=who)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_switch_starts_off_and_visitors_see_no_streak(client, people, alice):
    assert client.get(PRIVACY, headers=alice).json()["show_visit_streak"] is False
    assert public(client)["visit_streak"] is None
    assert public(client, people["bob"])["visit_streak"] is None


def test_visitors_see_it_once_switched_on(client, people, alice, monkeypatch):
    set_privacy(client, alice, show_visit_streak=True)
    # The public view reads the real clock; pin "now" to just after the last visit.
    monkeypatch.setattr("app.routers.public_profiles.datetime", _frozen(utc(2026, 11, 5, 18, 0)))
    for view in (public(client), public(client, people["bob"])):
        assert view["visit_streak"] == {"current": 3, "longest": 3}


def test_a_private_profile_hides_it_even_with_the_switch_on(client, people, alice):
    set_privacy(client, alice, show_visit_streak=True, is_private=True)
    assert public(client)["visit_streak"] is None
    assert public(client, people["bob"])["visit_streak"] is None


def test_switching_it_off_hides_it_on_the_next_request(client, alice):
    set_privacy(client, alice, show_visit_streak=True)
    assert public(client)["visit_streak"] is not None
    set_privacy(client, alice, show_visit_streak=False)
    assert public(client)["visit_streak"] is None


def test_a_lapsed_streak_shows_as_zero_with_the_best_kept(client, alice, monkeypatch):
    set_privacy(client, alice, show_visit_streak=True)
    monkeypatch.setattr("app.routers.public_profiles.datetime", _frozen(utc(2026, 11, 10, 12, 0)))
    assert public(client)["visit_streak"] == {"current": 0, "longest": 3}


def test_no_visits_yet_shows_zero(client, people):
    who = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=who)
    set_privacy(client, who, show_visit_streak=True)
    assert public(client)["visit_streak"] == {"current": 0, "longest": 0}


def _frozen(moment: datetime):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)

    return Frozen
