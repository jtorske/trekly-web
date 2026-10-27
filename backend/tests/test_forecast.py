"""Trail forecasts: Open-Meteo is never called; a saved live response
(fixtures/open_meteo_forecast.json, Lake Agnes Tea House at 1735 m and
2135 m, fetched 2026-10-26) stands in for it."""

import copy
import io
import json
import socket
import urllib.error
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app import weather
from app.main import app
from app.models.availability import AvailabilityCache
from app.models.trail import Trail
from app.routers.forecast import get_forecast_fetch

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "open_meteo_forecast.json").read_text())


@pytest.fixture
def trails(session_factory, client):
    session = session_factory()
    rows = {
        "both": Trail(name="Lake Agnes Tea House", region="Banff National Park, AB", country_code="CA", province_code="AB",
                      terrain_difficulty="easy", latitude=51.4159, longitude=-116.2112, max_elevation_m=2135, elevation_gain_m=400),
        "flat": Trail(name="Marsh Boardwalk", region="Banff National Park, AB", country_code="CA", province_code="AB",
                      terrain_difficulty="easy", latitude=51.18, longitude=-115.57, max_elevation_m=1400, elevation_gain_m=20),
        "unknown": Trail(name="Mystery Ridge", region="Somewhere, BC", country_code="CA", province_code="BC",
                         terrain_difficulty="moderate", latitude=50.1, longitude=-122.9),
        "nowhere": Trail(name="No Coordinates", region="Somewhere, BC", country_code="CA", province_code="BC",
                         terrain_difficulty="moderate"),
    }
    session.add_all(rows.values())
    session.commit()
    ids = {key: str(row.id) for key, row in rows.items()}
    session.close()
    return ids


class FakeOpenMeteo:
    """Records each URL and answers with `body` (or raises `error`)."""

    def __init__(self, body=None, error=None):
        self.body = FIXTURE if body is None else body
        self.error = error
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if self.error:
            raise self.error
        # Single-location requests get one location object back.
        params = parse_qs(urlparse(url).query)
        if "," not in params["latitude"][0] and isinstance(self.body, list):
            return copy.deepcopy(self.body[0])
        return copy.deepcopy(self.body)


@pytest.fixture
def open_meteo():
    fake = FakeOpenMeteo()
    app.dependency_overrides[get_forecast_fetch] = lambda: fake
    return fake


def query(url):
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def test_forecast_has_trailhead_and_summit_days(client, trails, open_meteo):
    response = client.get(f"/api/trails/{trails['both']}/forecast")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "Open-Meteo"
    assert body["timezone"] == "America/Edmonton"
    assert body["trailhead"]["elevation_m"] == 1735
    assert body["summit"]["elevation_m"] == 2135
    assert len(body["trailhead"]["days"]) == 5 and len(body["summit"]["days"]) == 5
    day = body["trailhead"]["days"][0]
    assert set(day) == {
        "date", "weather_code", "temp_max_c", "temp_min_c", "precip_probability_pct",
        "precip_mm", "snowfall_cm", "wind_max_kmh", "sunrise", "sunset",
    }
    assert day["date"] == "2026-10-26"
    assert day["sunrise"].startswith("2026-10-26T")
    # The high point is colder than the trailhead.
    assert body["summit"]["days"][0]["temp_max_c"] < day["temp_max_c"]


def test_request_asks_for_both_elevations_in_one_call(client, trails, open_meteo):
    client.get(f"/api/trails/{trails['both']}/forecast")
    assert len(open_meteo.urls) == 1
    params = query(open_meteo.urls[0])
    assert params["latitude"] == "51.4159,51.4159"
    assert params["longitude"] == "-116.2112,-116.2112"
    # Trailhead = high point - elevation gain.
    assert params["elevation"] == "1735,2135"
    assert params["forecast_days"] == "5"
    assert params["timezone"] == "auto"
    assert set(params["daily"].split(",")) == set(weather.DAILY)


def test_no_summit_when_the_high_point_is_barely_above_the_trailhead(client, trails, open_meteo):
    body = client.get(f"/api/trails/{trails['flat']}/forecast").json()
    assert body["summit"] is None
    params = query(open_meteo.urls[0])
    assert params["elevation"] == "1380"
    assert "," not in params["latitude"]


def test_without_elevation_data_the_trailhead_uses_open_meteos_terrain(client, trails, open_meteo):
    body = client.get(f"/api/trails/{trails['unknown']}/forecast").json()
    assert body["summit"] is None
    assert "elevation" not in query(open_meteo.urls[0])


def test_forecast_points_when_only_the_high_point_is_known():
    trail = Trail(latitude=50.1, longitude=-122.9, max_elevation_m=2100)
    points = weather.forecast_points(trail)
    assert (points.trailhead_m, points.summit_m) == (None, 2100)
    assert query(weather.forecast_url(points))["elevation"] == "nan,2100"


def test_summit_is_dropped_when_open_meteos_trailhead_is_nearly_as_high():
    points = weather.ForecastPoints(51.4, -116.2, None, 2135)
    body = copy.deepcopy(FIXTURE)
    body[0]["elevation"] = 2066.0
    assert weather.parse_forecast(body, points)["summit"] is None
    body[0]["elevation"] = 1900.0
    assert weather.parse_forecast(body, points)["summit"]["elevation_m"] == 2135


def test_trail_without_coordinates_or_unknown_trail_is_404(client, trails, open_meteo):
    assert client.get(f"/api/trails/{trails['nowhere']}/forecast").status_code == 404
    assert client.get(f"/api/trails/{uuid.uuid4()}/forecast").status_code == 404
    assert open_meteo.urls == []


# ------------------------------------------------------------- caching


def test_responses_are_cached_per_trail_for_an_hour(db, trails):
    fake = FakeOpenMeteo()
    trail = db.get(Trail, uuid.UUID(trails["both"]))
    start = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)

    first, fetched = weather.trail_forecast(db, trail, fake, now=lambda: start)
    again, cached_at = weather.trail_forecast(db, trail, fake, now=lambda: start + timedelta(minutes=59))
    assert len(fake.urls) == 1
    assert again == first and cached_at == fetched == start

    _, refreshed_at = weather.trail_forecast(db, trail, fake, now=lambda: start + timedelta(minutes=61))
    assert len(fake.urls) == 2
    assert refreshed_at == start + timedelta(minutes=61)
    # One cache row per trail, refreshed in place.
    keys = [row.cache_key for row in db.query(AvailabilityCache).all()]
    assert len(keys) == 1 and keys[0].startswith(f"open-meteo:forecast:{trail.id}:")


def test_cache_is_per_trail(client, trails, open_meteo):
    for _ in range(3):
        client.get(f"/api/trails/{trails['both']}/forecast")
        client.get(f"/api/trails/{trails['flat']}/forecast")
    assert len(open_meteo.urls) == 2


def test_cache_key_changes_when_the_catalogue_changes(db, trails):
    fake = FakeOpenMeteo()
    trail = db.get(Trail, uuid.UUID(trails["both"]))
    weather.trail_forecast(db, trail, fake)
    trail.max_elevation_m = 2200
    db.commit()
    weather.trail_forecast(db, trail, fake)
    assert len(fake.urls) == 2
    assert query(fake.urls[1])["elevation"] == "1800,2200"


# ------------------------------------------------------------- failures


def test_timeout_is_a_clean_504(client, trails):
    fake = FakeOpenMeteo(error=weather.ForecastTimeout("Open-Meteo didn't answer within 6s"))
    app.dependency_overrides[get_forecast_fetch] = lambda: fake
    response = client.get(f"/api/trails/{trails['both']}/forecast")
    assert response.status_code == 504
    assert response.json() == {"detail": "The weather service is taking too long. Try again shortly."}


@pytest.mark.parametrize(
    "error",
    [
        weather.ForecastUnavailable("HTTP Error 503: Service Unavailable"),
        RuntimeError("connection reset"),
    ],
)
def test_open_meteo_errors_are_a_clean_502(client, trails, error):
    app.dependency_overrides[get_forecast_fetch] = lambda: FakeOpenMeteo(error=error)
    response = client.get(f"/api/trails/{trails['both']}/forecast")
    assert response.status_code == 502
    assert response.json() == {"detail": "The weather forecast isn't available right now."}


@pytest.mark.parametrize(
    "body",
    [
        {"error": True, "reason": "Cannot initialize WeatherCode from invalid String value"},
        [FIXTURE[0]],  # one location when two were asked for
        "<html>Bad gateway</html>",
        [{**FIXTURE[0], "daily": {**FIXTURE[0]["daily"], "sunset": []}}, FIXTURE[1]],
    ],
)
def test_malformed_responses_are_a_502_and_never_cached(client, db, trails, body):
    app.dependency_overrides[get_forecast_fetch] = lambda: FakeOpenMeteo(body=body)
    assert client.get(f"/api/trails/{trails['both']}/forecast").status_code == 502
    assert db.query(AvailabilityCache).count() == 0


def test_a_failure_after_the_cache_expires_does_not_serve_a_broken_page(db, trails):
    trail = db.get(Trail, uuid.UUID(trails["both"]))
    start = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
    weather.trail_forecast(db, trail, FakeOpenMeteo(), now=lambda: start)
    with pytest.raises(weather.ForecastUnavailable):
        weather.trail_forecast(db, trail, FakeOpenMeteo(error=RuntimeError("down")), now=lambda: start + timedelta(hours=2))


# ------------------------------------------------------------- the real client


class SlowResponse:
    def __enter__(self):
        raise socket.timeout("timed out")

    def __exit__(self, *args):
        return False


def test_fetch_json_turns_socket_timeouts_into_forecast_timeouts(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["timeout"] = timeout
        return SlowResponse()

    monkeypatch.setattr(weather.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(weather.ForecastTimeout):
        weather.fetch_json("https://api.open-meteo.com/v1/forecast?x=1", timeout_s=2.5)
    assert seen["timeout"] == 2.5


def test_fetch_json_turns_connect_timeouts_and_http_errors_into_unavailable(monkeypatch):
    def connect_timeout(request, timeout):
        raise urllib.error.URLError(socket.timeout("timed out"))

    monkeypatch.setattr(weather.urllib.request, "urlopen", connect_timeout)
    with pytest.raises(weather.ForecastTimeout):
        weather.fetch_json("https://api.open-meteo.com/v1/forecast")

    def rate_limited(request, timeout):
        body = io.BytesIO(b'{"error": true, "reason": "Daily API request limit exceeded"}')
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, body)

    monkeypatch.setattr(weather.urllib.request, "urlopen", rate_limited)
    with pytest.raises(weather.ForecastUnavailable) as caught:
        weather.fetch_json("https://api.open-meteo.com/v1/forecast")
    assert not isinstance(caught.value, weather.ForecastTimeout)
    assert str(caught.value) == "Open-Meteo HTTP 429: Daily API request limit exceeded"

    def server_error(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, io.BytesIO(b"<html>"))

    monkeypatch.setattr(weather.urllib.request, "urlopen", server_error)
    with pytest.raises(weather.ForecastUnavailable) as caught:
        weather.fetch_json("https://api.open-meteo.com/v1/forecast")
    assert str(caught.value) == "Open-Meteo HTTP 503"


def test_failures_are_logged_with_the_reason(client, trails, caplog):
    error = weather.ForecastUnavailable("Open-Meteo HTTP 429: Daily API request limit exceeded")
    app.dependency_overrides[get_forecast_fetch] = lambda: FakeOpenMeteo(error=error)
    with caplog.at_level("WARNING", logger="uvicorn.error"):
        assert client.get(f"/api/trails/{trails['both']}/forecast").status_code == 502
    assert "Daily API request limit exceeded" in caplog.text
    assert trails["both"] in caplog.text
