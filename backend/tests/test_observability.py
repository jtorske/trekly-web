"""Sentry reporting (app/observability.py): off without a DSN, no personal
data, no expected 4xx errors, and a real 500 does get reported."""

import logging
import uuid

import pytest
import sentry_sdk
from fastapi import HTTPException
from starlette.testclient import TestClient

from app.main import app
from app.observability import FILTERED, scrub_event, sentry_options

ADMIN = uuid.UUID("22222222-2222-4222-8222-222222222222")
FAKE_DSN = "https://publickey@o1.ingest.us.sentry.io/1"


def test_off_without_a_dsn():
    assert sentry_options({}) is None
    assert sentry_options({"SENTRY_DSN": "  "}) is None


def test_production_on_render_with_the_git_sha_and_10_percent_traces():
    options = sentry_options({"SENTRY_DSN": FAKE_DSN, "RENDER": "true", "RENDER_GIT_COMMIT": "abc123"})
    assert options["environment"] == "production"
    assert options["release"] == "abc123"
    assert options["traces_sample_rate"] == 0.1
    assert options["send_default_pii"] is False


def test_local_sends_no_traces():
    options = sentry_options({"SENTRY_DSN": FAKE_DSN})
    assert options["environment"] == "local"
    assert options["traces_sample_rate"] == 0.0


def test_personal_data_is_scrubbed():
    event = {
        "message": "Couldn't email hiker@example.com",
        "request": {
            "url": "https://trekly-api.onrender.com/api/x?email=a@b.co",
            "headers": {"Authorization": "Bearer eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl", "Cookie": "sb=1",
                        "User-Agent": "Mozilla", "X-Refresh-Token": "r"},
            "cookies": {"sb": "1"},
            "data": {"password": "hunter2"},
            "query_string": "access_token=xyz&province_code=AB&code=123",
        },
        "user": {"id": "u1", "email": "hiker@example.com", "ip_address": "1.2.3.4"},
        "exception": {"values": [{"type": "ValueError", "value": "bad token eyJabc.eyJdef.ghi for x@y.ca"}]},
        "breadcrumbs": {"values": [{"message": "sent to someone@trekly.ca"}]},
        "extra": {"refresh_token": "secret", "trail": "Lake Agnes"},
    }
    out = scrub_event(event, {})
    text = str(out)
    for leaked in ("hiker@example.com", "a@b.co", "x@y.ca", "someone@trekly.ca", "hunter2", "xyz", "1.2.3.4", "eyJ"):
        assert leaked not in text, leaked
    headers = out["request"]["headers"]
    assert headers["Authorization"] == FILTERED and headers["Cookie"] == FILTERED and headers["X-Refresh-Token"] == FILTERED
    assert headers["User-Agent"] == "Mozilla"
    assert "cookies" not in out["request"] and "data" not in out["request"]
    assert "province_code=AB" in out["request"]["query_string"]
    assert out["user"] == {"id": "u1"}
    assert out["extra"]["trail"] == "Lake Agnes"


@pytest.mark.parametrize("status", [401, 403, 404, 422, 429])
def test_expected_errors_are_dropped(status):
    error = HTTPException(status_code=status)
    assert scrub_event({"message": "x"}, {"exc_info": (type(error), error, None)}) is None
    assert scrub_event({"contexts": {"response": {"status_code": status}}}, {}) is None


def test_a_server_error_is_kept():
    error = RuntimeError("boom")
    assert scrub_event({"message": "x"}, {"exc_info": (RuntimeError, error, None)}) is not None


@pytest.fixture
def captured(monkeypatch):
    """A real Sentry client whose events land in a list instead of the network."""
    events = []

    class Transport(sentry_sdk.transport.Transport):
        def capture_envelope(self, envelope):
            for item in envelope.items:
                if item.type == "event":
                    events.append(item.payload.json)

    options = sentry_options({"SENTRY_DSN": FAKE_DSN})
    sentry_sdk.init(**options, transport=Transport)
    yield events
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # back to a disabled client


def test_the_admin_test_endpoint_reports_one_scrubbed_500(client, auth_headers, monkeypatch, captured, caplog):
    monkeypatch.setenv("ADMIN_USER_IDS", str(ADMIN))
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        response = client.post("/api/admin/sentry-test", headers=auth_headers(ADMIN))
    assert response.status_code == 500
    sentry_sdk.flush()
    assert len(captured) == 1, captured
    event = captured[0]
    assert "Trekly Sentry test (backend)" in str(event)
    assert "Bearer" not in str(event)
    frames = event["exception"]["values"][-1]["stacktrace"]["frames"] if "exception" in event else []
    assert all("vars" not in frame for frame in frames)


def test_non_admins_get_403_and_nothing_is_reported(client, auth_headers, monkeypatch, captured):
    monkeypatch.setenv("ADMIN_USER_IDS", str(ADMIN))
    assert client.post("/api/admin/sentry-test", headers=auth_headers(uuid.uuid4())).status_code == 403
    assert client.get("/api/trails/by-slug/no-such-trail").status_code == 404
    sentry_sdk.flush()
    assert captured == []
