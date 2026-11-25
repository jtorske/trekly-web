"""The season helper: date boundaries, snow adjustment near them, picks, and GET /api/season."""

from datetime import date

import pytest

from app import season
from app.season import by_date, info, near_boundary, next_change, pick_season, season_for


@pytest.mark.parametrize("day, expected", [
    (date(2026, 11, 14), "summer"),
    (date(2026, 11, 15), "winter"),
    (date(2026, 12, 31), "winter"),
    (date(2027, 1, 1), "winter"),
    (date(2027, 4, 14), "winter"),
    (date(2027, 4, 15), "summer"),
    (date(2027, 7, 1), "summer"),
    (date(2024, 2, 29), "winter"),
])
def test_by_date(day, expected):
    assert by_date(day) == expected


def test_snow_only_counts_near_a_boundary():
    # Mid-January with bare ground is still winter; mid-July with a dusting is still summer.
    assert season_for(date(2027, 1, 20), snow_depth_cm=0) == "winter"
    assert season_for(date(2027, 7, 20), snow_depth_cm=50) == "summer"


def test_snow_can_bring_winter_early_or_keep_it_late():
    assert season_for(date(2026, 11, 1), snow_depth_cm=25) == "winter"
    assert season_for(date(2027, 4, 30), snow_depth_cm=40) == "winter"


def test_bare_ground_can_end_winter_early_or_start_it_late():
    assert season_for(date(2027, 4, 1), snow_depth_cm=0) == "summer"
    assert season_for(date(2026, 11, 20), snow_depth_cm=1) == "summer"


def test_in_between_snow_or_none_keeps_the_date():
    assert season_for(date(2026, 11, 1), snow_depth_cm=5) == "summer"
    assert season_for(date(2026, 11, 20), snow_depth_cm=5) == "winter"
    assert season_for(date(2026, 11, 1)) == "summer"


def test_near_boundary_window():
    assert near_boundary(date(2026, 11, 15))
    assert near_boundary(date(2026, 10, 25))  # 21 days before
    assert not near_boundary(date(2026, 10, 24))
    assert near_boundary(date(2027, 5, 6))
    assert not near_boundary(date(2027, 1, 15))


def test_next_change():
    assert next_change(date(2026, 11, 24)) == date(2027, 4, 15)
    assert next_change(date(2027, 4, 15)) == date(2027, 11, 15)
    assert next_change(date(2026, 11, 14)) == date(2026, 11, 15)


def test_info_says_when_snow_decided():
    adjusted = info(date(2026, 11, 1), snow_depth_cm=30)
    assert (adjusted.season, adjusted.by_date, adjusted.adjusted_by_snow) == ("winter", "summer", True)
    plain = info(date(2026, 11, 24))
    assert (plain.season, plain.adjusted_by_snow) == ("winter", False)


@pytest.mark.parametrize("day, expected", [
    (date(2026, 11, 10), None),     # no fall picks in November
    (date(2026, 11, 24), "winter"),
    (date(2027, 3, 1), "winter"),
    (date(2027, 4, 20), "spring"),
    (date(2027, 7, 4), "summer"),
    (date(2026, 10, 5), "fall"),
])
def test_pick_season(day, expected):
    assert pick_season(day) == expected


def test_season_endpoint(client, monkeypatch):
    monkeypatch.setattr(season, "today", lambda: date(2026, 11, 24))
    body = client.get("/api/season").json()
    assert body == {"season": "winter", "by_date": "winter", "adjusted_by_snow": False,
                    "next_change": "2027-04-15", "today": "2026-11-24"}
    early = client.get("/api/season", params={"snow_depth_cm": 30, "on": "2026-11-01"}).json()
    assert early["season"] == "winter" and early["adjusted_by_snow"] is True
    assert client.get("/api/season", params={"snow_depth_cm": -1}).status_code == 422
