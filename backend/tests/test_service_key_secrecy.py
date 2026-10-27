"""The service-role key (SUPABASE_SERVICE_ROLE_KEY) must never leave the server.

Every route in the app is called as a photo admin while all outbound HTTP
fails in the worst way: the "server" echoes the request's own headers (which
carry the key) in its error message, headers and body. No response body,
response header or log line may contain the key.
"""

import io
import logging
import re
import time
import urllib.error
import urllib.request
import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Profile
from app.models.trail import Trail
from app.routers import admin_trail_photos as admin
from app.trail_photos import PhotoStorage, StorageError, storage_from_env

from tests.test_trail_photos import ADMIN, jpeg

SECRET = f"service-role-{uuid.uuid4().hex}"


def _echo(request):
    """Everything the request carried, as a misbehaving server might repeat it."""
    return " ".join(f"{k}: {v}" for k, v in request.header_items()) if hasattr(request, "header_items") else str(request)


class FakeNetwork:
    def __init__(self):
        self.mode = "http_error"
        self.calls = 0

    def urlopen(self, request, *args, **kwargs):
        self.calls += 1
        echoed = _echo(request)
        if self.mode == "http_error":
            raise urllib.error.HTTPError(
                getattr(request, "full_url", str(request)), 500, f"Internal error: {echoed}",
                {"X-Echo": echoed}, io.BytesIO(echoed.encode()),
            )
        if self.mode == "url_error":
            raise urllib.error.URLError(f"connection reset while sending {echoed}")
        return io.BytesIO(b"{}")


@pytest.fixture
def network(monkeypatch):
    fake = FakeNetwork()
    monkeypatch.setattr(urllib.request, "urlopen", fake.urlopen)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    return fake


@pytest.fixture
def setup(client, session_factory, tmp_path, monkeypatch, network):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    monkeypatch.setenv("PHOTO_ADMIN_USER_IDS", str(ADMIN))
    session = session_factory()
    trail = Trail(name="Lake Agnes Tea House", region="Banff National Park, AB", country_code="CA",
                  province_code="AB", terrain_difficulty="easy", typical_duration_nights=0, popularity_rank=1)
    session.add_all([trail, Profile(id=ADMIN, display_name="Jordan Torske")])
    session.commit()
    trail_id = str(trail.id)
    session.close()

    candidates = tmp_path / "photo_candidates.json"
    candidates.write_text(
        '{"trails": [{"name": "Lake Agnes Tea House", "province_code": "AB", "candidates": [{"id": "commons:1", '
        '"source": "commons", "origin": "Wikimedia Commons", "confidence": "high", "title": "t", "preview_url": '
        '"https://upload.wikimedia.org/a.jpg", "image_url": "https://upload.wikimedia.org/a.jpg", "width": 2400, '
        '"height": 1600, "photographer": "P", "license": "CC BY 2.0", "source_url": "https://commons.wikimedia.org/x"}]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(admin, "PHOTO_CANDIDATES_PATH", str(candidates))
    # The real storage client (it holds the key); only the image download is faked.
    app.dependency_overrides[admin.get_image_fetcher] = lambda: (lambda url: jpeg())
    return trail_id


def every_request(trail_id):
    """(method, path, kwargs) for every route, path params filled in."""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = re.sub(r"\{[^}]+\}", trail_id, route.path)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            if path.endswith("/upload"):
                kwargs = {"content": jpeg(), "headers": {"Content-Type": "image/jpeg"}}
            elif path.endswith("/approve"):
                kwargs = {"json": {"candidate_id": "commons:1"}}
            elif method in ("POST", "PUT", "PATCH"):
                kwargs = {"json": {}}
            else:
                kwargs = {}
            yield method, path, kwargs


def assert_no_secret(text, where):
    assert SECRET not in text, f"service-role key leaked in {where}"


@pytest.mark.parametrize("mode", ["http_error", "url_error", "ok"])
def test_no_endpoint_or_error_leaks_the_service_role_key(setup, network, auth_headers, caplog, capsys, mode):
    network.mode = mode
    caplog.set_level(logging.DEBUG)
    statuses = {}
    with TestClient(app, raise_server_exceptions=False) as raw:
        for method, path, kwargs in every_request(setup):
            headers = {**auth_headers(ADMIN), **kwargs.pop("headers", {})}
            response = raw.request(method, path, headers=headers, **kwargs)
            statuses[f"{method} {path}"] = response.status_code
            assert_no_secret(response.text, f"the body of {method} {path}")
            assert_no_secret(str(dict(response.headers)), f"the headers of {method} {path}")

    approve = f"POST /api/admin/trail-photos/{setup}/approve"
    if mode == "ok":
        assert statuses[approve] == 200
    else:
        # The storage path really ran and failed, and said so without the key.
        assert statuses[approve] == 502
    assert network.calls > 0
    assert_no_secret(caplog.text, "the logs")
    captured = capsys.readouterr()
    assert_no_secret(captured.out + captured.err, "stdout/stderr")


def test_storage_client_and_errors_never_show_the_key(monkeypatch, network):
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)
    storage = storage_from_env()
    assert isinstance(storage, PhotoStorage)
    assert_no_secret(repr(storage), "repr()")
    assert_no_secret(str(vars(storage)), "the public attributes")
    for mode in ("http_error", "url_error"):
        network.mode = mode
        with pytest.raises(StorageError) as raised:
            storage.upload("a/b-hero.webp", b"x")
        assert_no_secret(str(raised.value), "StorageError")
        # The original exception (which carries the echo) is dropped.
        assert raised.value.__cause__ is None and raised.value.__suppress_context__
