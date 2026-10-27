"""Trail photo review and publishing: the admin gate, server-side candidate
lookup, WebP processing, file replacement, and the public photo field."""

import importlib.util
import io
import urllib.error
import uuid
from pathlib import Path

import pytest
from PIL import Image

from app.main import app
from app.models.account import Profile
from app.models.trail import Trail
from app.routers import admin_trail_photos as admin
from app import trail_photos
from app.models.trail_photo import TrailPhotoCandidates
from app.trail_photos import PhotoError, SourceBusy, allowed_fetch_url, fetch_image, fetch_urls

_spec = importlib.util.spec_from_file_location(
    "load_photo_candidates", Path(__file__).resolve().parent.parent / "scripts" / "load_photo_candidates.py"
)
loader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(loader)

ADMIN = uuid.UUID("11111111-1111-4111-8111-111111111111")
IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Lake_Agnes.jpg"


def jpeg(width=2400, height=1600, gps=True):
    image = Image.new("RGB", (width, height), (90, 130, 160))
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {1: "N", 2: (51.0, 25.0, 0.0)}  # GPSInfo
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


class FakeStorage:
    def __init__(self):
        self.files, self.deleted = {}, []

    def upload(self, path, data):
        self.files[path] = data

    def delete(self, paths):
        self.deleted.extend(paths)
        for path in paths:
            self.files.pop(path, None)


@pytest.fixture
def trails(session_factory, client):
    session = session_factory()
    rows = [
        Trail(name="Lake Agnes Tea House", region="Banff National Park, AB", country_code="CA", province_code="AB",
              terrain_difficulty="easy", typical_duration_nights=0, popularity_rank=1),
        Trail(name="Joffre Lakes", region="Joffre Lakes Provincial Park, BC", country_code="CA", province_code="BC",
              terrain_difficulty="moderate", typical_duration_nights=0, popularity_rank=2),
    ]
    session.add_all(rows)
    session.commit()
    ids = [str(row.id) for row in rows]
    session.close()
    return ids


def candidate(cid, **overrides):
    return {
        "id": cid, "source": "commons", "origin": "Wikimedia Commons", "confidence": "high",
        "title": "Lake Agnes Tea House.jpg", "preview_url": IMAGE_URL, "image_url": IMAGE_URL,
        "width": 2400, "height": 1600, "photographer": "Wilson Hui", "license": "CC BY 2.0",
        "license_url": "https://creativecommons.org/licenses/by/2.0", "source_url": "https://commons.wikimedia.org/wiki/File:X.jpg",
        "distance_m": 2288, **overrides,
    }


@pytest.fixture
def setup(session_factory, monkeypatch, trails):
    load(session_factory, SEARCH_OUTPUT)
    monkeypatch.setenv("PHOTO_ADMIN_USER_IDS", f"{uuid.uuid4()}, {ADMIN}")
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    storage = FakeStorage()
    fetched = []
    app.dependency_overrides[admin.get_photo_storage] = lambda: storage
    app.dependency_overrides[admin.get_image_fetcher] = lambda: (lambda url: fetched.append(url) or jpeg())
    return {"storage": storage, "fetched": fetched, "agnes": trails[0], "joffre": trails[1]}


SEARCH_OUTPUT = {"generated": "2026-10-26", "trails": [
    {"name": "Lake Agnes Tea House", "province_code": "AB", "destination": "Lake Agnes Tea House",
     "best_confidence": "high", "default_choice": "commons:1",
     "candidates": [candidate("commons:1"), candidate("commons:2", photographer="Someone Else")]},
    {"name": "Joffre Lakes", "province_code": "BC", "destination": "Joffre Lakes",
     "best_confidence": "off_topic", "default_choice": None, "candidates": [candidate("commons:9")]},
]}


def load(session_factory, data):
    """Load search output the way scripts/load_photo_candidates.py does."""
    session = session_factory()
    plan = loader.plan_load(session, data)
    loader.apply_plan(session, plan)
    session.close()
    return plan


def add_profile(session_factory, user_id, display_name="Jordan Torske"):
    session = session_factory()
    session.add(Profile(id=user_id, display_name=display_name))
    session.commit()
    session.close()


def routes(trail_id):
    return [
        ("get", "/api/admin/trail-photos/me", {}),
        ("get", "/api/admin/trail-photos", {}),
        ("post", f"/api/admin/trail-photos/{trail_id}/approve", {"json": {"candidate_id": "commons:1"}}),
        ("post", f"/api/admin/trail-photos/{trail_id}/reject", {}),
        ("delete", f"/api/admin/trail-photos/{trail_id}/photo", {}),
        ("put", f"/api/admin/trail-photos/{trail_id}/upload", {"content": jpeg(), "headers": {"Content-Type": "image/jpeg"}}),
    ]


def test_every_route_needs_a_signed_in_photo_admin(client, auth_headers, setup):
    for method, path, kwargs in routes(setup["agnes"]):
        headers = kwargs.pop("headers", {})
        assert getattr(client, method)(path, headers=headers, **kwargs).status_code == 401, path
        outsider = {**headers, **auth_headers(uuid.uuid4())}
        assert getattr(client, method)(path, headers=outsider, **kwargs).status_code == 403, path
    assert setup["storage"].files == {} and setup["fetched"] == []


def test_nobody_is_an_admin_when_the_setting_is_empty(client, auth_headers, setup, monkeypatch):
    monkeypatch.setenv("PHOTO_ADMIN_USER_IDS", "")
    assert client.get("/api/admin/trail-photos/me", headers=auth_headers(ADMIN)).status_code == 403


def test_non_admin_gets_403_even_without_storage_configured(client, auth_headers, setup, monkeypatch):
    app.dependency_overrides.pop(admin.get_photo_storage)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    path = f"/api/admin/trail-photos/{setup['agnes']}/reject"
    assert client.post(path, headers=auth_headers(uuid.uuid4())).status_code == 403
    assert client.post(path, headers=auth_headers(ADMIN)).status_code == 503


def test_review_list_shows_candidates_and_defaults(client, auth_headers, setup):
    response = client.get("/api/admin/trail-photos", headers=auth_headers(ADMIN))
    assert response.status_code == 200
    agnes, joffre = response.json()
    assert agnes["trail"]["name"] == "Lake Agnes Tea House"
    assert agnes["default_choice"] == "commons:1" and len(agnes["candidates"]) == 2
    # An off-topic best candidate starts on the topo fallback.
    assert joffre["default_choice"] is None and joffre["best_confidence"] == "off_topic"
    assert agnes["review"] is None and agnes["trail"]["photo"] is None


def test_approve_publishes_webp_files_and_the_credit(client, auth_headers, setup):
    response = client.post(f"/api/admin/trail-photos/{setup['agnes']}/approve",
                           json={"candidate_id": "commons:1"}, headers=auth_headers(ADMIN))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["photographer"] == "Wilson Hui" and body["license"] == "CC BY 2.0"
    assert body["source_url"] == "https://commons.wikimedia.org/wiki/File:X.jpg"
    assert body["width"] == 1600 and body["height"] == round(1600 * 1600 / 2400)
    # The image came from the stored candidate, not from the request, and as
    # a 1920px Commons thumbnail since the original is wider.
    assert setup["fetched"] == ["https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Lake_Agnes.jpg/1920px-Lake_Agnes.jpg"]

    files = setup["storage"].files
    assert len(files) == 2 and all(path.startswith(f"{setup['agnes']}/") and path.endswith(".webp") for path in files)
    sizes = {}
    for path, data in files.items():
        image = Image.open(io.BytesIO(data))
        assert image.format == "WEBP"
        assert not image.getexif(), "metadata (including GPS) must be stripped"
        sizes["hero" if path.endswith("-hero.webp") else "thumb"] = image.width
    assert sizes == {"hero": 1600, "thumb": 640}

    trail = client.get(f"/api/trails/{setup['agnes']}").json()
    assert trail["photo"]["hero_url"].startswith(
        f"https://test-project.supabase.co/storage/v1/object/public/trail-photos/{setup['agnes']}/")
    assert trail["photo"]["origin"] == "Wikimedia Commons"
    listed = client.get("/api/trails").json()
    assert next(t for t in listed if t["id"] == setup["agnes"])["photo"]["thumb_url"].endswith("-thumb.webp")


def test_candidate_must_belong_to_the_trail(client, auth_headers, setup):
    response = client.post(f"/api/admin/trail-photos/{setup['agnes']}/approve",
                           json={"candidate_id": "commons:9"}, headers=auth_headers(ADMIN))
    assert response.status_code == 404
    assert setup["fetched"] == []


def test_approving_again_replaces_the_files(client, auth_headers, setup):
    url = f"/api/admin/trail-photos/{setup['agnes']}/approve"
    client.post(url, json={"candidate_id": "commons:1"}, headers=auth_headers(ADMIN))
    first = set(setup["storage"].files)
    response = client.post(url, json={"candidate_id": "commons:2"}, headers=auth_headers(ADMIN))
    assert response.json()["photographer"] == "Someone Else"
    assert set(setup["storage"].deleted) == first
    assert len(setup["storage"].files) == 2 and not first & set(setup["storage"].files)


def test_reject_falls_back_to_topo_but_keeps_your_own_photo(client, auth_headers, setup, session_factory):
    base = f"/api/admin/trail-photos/{setup['agnes']}"
    client.post(f"{base}/approve", json={"candidate_id": "commons:1"}, headers=auth_headers(ADMIN))
    assert client.post(f"{base}/reject", headers=auth_headers(ADMIN)).status_code == 204
    assert client.get(f"/api/trails/{setup['agnes']}").json()["photo"] is None
    assert setup["storage"].files == {}
    review = client.get("/api/admin/trail-photos", headers=auth_headers(ADMIN)).json()[0]["review"]
    assert review["decision"] == "rejected"

    add_profile(session_factory, ADMIN)
    client.put(f"{base}/upload", content=jpeg(), headers={**auth_headers(ADMIN), "Content-Type": "image/jpeg"})
    client.post(f"{base}/reject", headers=auth_headers(ADMIN))
    assert client.get(f"/api/trails/{setup['agnes']}").json()["photo"]["photographer"] == "Jordan Torske"

    assert client.delete(f"{base}/photo", headers=auth_headers(ADMIN)).status_code == 204
    assert client.get(f"/api/trails/{setup['agnes']}").json()["photo"] is None


def test_own_upload_is_credited_to_your_profile_name(client, auth_headers, setup, session_factory):
    url = f"/api/admin/trail-photos/{setup['joffre']}/upload"
    headers = {**auth_headers(ADMIN), "Content-Type": "image/jpeg"}
    assert client.put(url, content=jpeg(), headers=headers).status_code == 400  # no profile name yet

    add_profile(session_factory, ADMIN)
    response = client.put(url, content=jpeg(), headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["photographer"] == "Jordan Torske"
    assert body["license"] is None and body["source_url"] is None and body["origin"] is None


@pytest.mark.parametrize("data,content_type,code", [
    (b"not an image", "image/jpeg", 422),
    (jpeg(800, 500), "image/jpeg", 422),     # too small
    (jpeg(1200, 1800), "image/jpeg", 422),   # portrait
    (jpeg(), "image/gif", 415),
], ids=["not-an-image", "too-small", "portrait", "wrong-type"])
def test_unusable_uploads_are_refused(client, auth_headers, setup, session_factory, data, content_type, code):
    add_profile(session_factory, ADMIN)
    response = client.put(f"/api/admin/trail-photos/{setup['joffre']}/upload", content=data,
                          headers={**auth_headers(ADMIN), "Content-Type": content_type})
    assert response.status_code == code
    assert setup["storage"].files == {}


@pytest.mark.parametrize("url,ok", [
    ("https://upload.wikimedia.org/wikipedia/commons/a/ab/X.jpg", True),
    ("https://live.staticflickr.com/3937/1_a_b.jpg", True),
    ("https://farm4.staticflickr.com/3937/1_a_b.jpg", True),
    ("http://upload.wikimedia.org/x.jpg", False),
    ("https://upload.wikimedia.org.evil.example/x.jpg", False),
    ("https://evil.example/upload.wikimedia.org/x.jpg", False),
    ("https://staticflickr.com.evil.example/x.jpg", False),
    ("https://127.0.0.1/x.jpg", False),
])
def test_candidate_images_are_fetched_from_known_hosts_only(url, ok):
    assert allowed_fetch_url(url) is ok


# ---------------------------------------------------------------- loading candidates

def test_loader_matches_trails_by_name_and_province_to_this_databases_ids(trails, session_factory):
    data = {"generated": "2026-10-26", "trails": [
        *SEARCH_OUTPUT["trails"],
        {"name": "Lake Agnes Tea House", "province_code": "BC", "candidates": []},  # wrong province
        {"name": "Not In This Database", "province_code": "AB", "candidates": []},
    ]}
    session = session_factory()
    plan = loader.plan_load(session, data)
    assert {str(row.trail_id) for row in plan.rows} == set(trails)
    assert plan.unmatched == ["Lake Agnes Tea House (BC)", "Not In This Database (AB)"]
    assert plan.missing == [] and plan.problems == [] and plan.replaced == 0
    session.close()


def test_dry_run_writes_nothing_and_reloading_replaces(trails, session_factory):
    session = session_factory()
    loader.plan_load(session, SEARCH_OUTPUT)
    session.rollback()
    assert session.query(TrailPhotoCandidates).count() == 0
    session.close()

    load(session_factory, SEARCH_OUTPUT)
    again = load(session_factory, SEARCH_OUTPUT)
    session = session_factory()
    assert again.replaced == 2 and session.query(TrailPhotoCandidates).count() == 2
    session.close()


@pytest.mark.parametrize("bad,problem", [
    ({"image_url": "https://evil.example/a.jpg"}, "image host not allowed"),
    ({"source_url": "http://commons.wikimedia.org/x"}, "not https"),
    ({"photographer": "someone@example.com"}, "email address"),
    ({"license": ""}, "missing license"),
    ({"width": 1000, "height": 1500}, "not a landscape size"),
], ids=["host", "http-source", "email-credit", "no-license", "portrait"])
def test_one_invalid_candidate_blocks_the_whole_load(trails, session_factory, bad, problem):
    data = {"trails": [{**SEARCH_OUTPUT["trails"][0], "candidates": [candidate("commons:1", **bad)]}]}
    session = session_factory()
    plan = loader.plan_load(session, data)
    assert len(plan.problems) == 1 and problem in plan.problems[0]
    with pytest.raises(ValueError):
        loader.apply_plan(session, plan)
    assert session.query(TrailPhotoCandidates).count() == 0
    session.close()


# ---------------------------------------------------------------- fetching from the sources

ORIGINAL = "https://upload.wikimedia.org/wikipedia/commons/5/5f/Lady_Peak.jpg?utm_source=commons.wikimedia.org"


def test_wide_commons_originals_are_fetched_as_1920px_thumbnails_first():
    assert fetch_urls({"image_url": ORIGINAL, "width": 9441}) == [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5f/Lady_Peak.jpg/1920px-Lady_Peak.jpg", ORIGINAL]
    assert fetch_urls({"image_url": ORIGINAL, "width": 1920}) == [ORIGINAL]
    flickr = "https://live.staticflickr.com/1/2_a_b.jpg"
    assert fetch_urls({"image_url": flickr, "width": 1024}) == [flickr]


class FakeOpener:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def open(self, request, timeout):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(result)


def busy(code, retry_after):
    return urllib.error.HTTPError("u", code, "busy", {"Retry-After": retry_after}, io.BytesIO())


def opener(monkeypatch, *responses):
    fake = FakeOpener(responses)
    monkeypatch.setattr(trail_photos.urllib.request, "build_opener", lambda *_: fake)
    return fake


def test_fetch_sends_a_wikimedia_style_user_agent(monkeypatch):
    fake = opener(monkeypatch, b"image")
    assert fetch_image(ORIGINAL) == b"image"
    agent = fake.requests[0].get_header("User-agent")
    assert agent.startswith("TreklyPhotoPublisher/1.0 (") and "@" in agent and "python-urllib/" in agent


def test_a_short_rate_limit_is_retried_once(monkeypatch):
    waits = []
    opener(monkeypatch, busy(429, "2"), b"image")
    assert fetch_image(ORIGINAL, sleep=waits.append) == b"image"
    assert waits == [2]


@pytest.mark.parametrize("responses,retry_after", [
    ([busy(429, "120")], 120),             # too long to wait inside a request
    ([busy(503, "1"), busy(429, "1")], 1),  # still busy after the one retry
], ids=["long-wait", "busy-twice"])
def test_a_longer_rate_limit_says_when_to_try_again(monkeypatch, responses, retry_after):
    opener(monkeypatch, *responses)
    with pytest.raises(SourceBusy) as raised:
        fetch_image(ORIGINAL, sleep=lambda _: None)
    assert raised.value.retry_after == retry_after


def test_approve_reports_a_busy_source_and_changes_nothing(client, auth_headers, setup):
    def fetch(url):
        raise SourceBusy(300)
    app.dependency_overrides[admin.get_image_fetcher] = lambda: fetch
    response = client.post(f"/api/admin/trail-photos/{setup['agnes']}/approve",
                           json={"candidate_id": "commons:1"}, headers=auth_headers(ADMIN))
    assert response.status_code == 503 and response.headers["Retry-After"] == "300"
    assert "Nothing was changed" in response.json()["detail"]
    assert setup["storage"].files == {}
    assert client.get(f"/api/trails/{setup['agnes']}").json()["photo"] is None


def test_approve_falls_back_to_the_original_when_the_thumbnail_fails(client, auth_headers, setup, session_factory):
    wide = candidate("commons:wide", image_url=ORIGINAL, width=9441, height=4000)
    load(session_factory, {"trails": [{**SEARCH_OUTPUT["trails"][0], "default_choice": "commons:wide", "candidates": [wide]}]})
    tried = []

    def fetch(url):
        tried.append(url)
        if "/thumb/" in url:
            raise PhotoError("The source didn't return the image (HTTP 404).")
        return jpeg()
    app.dependency_overrides[admin.get_image_fetcher] = lambda: fetch
    response = client.post(f"/api/admin/trail-photos/{setup['agnes']}/approve",
                           json={"candidate_id": "commons:wide"}, headers=auth_headers(ADMIN))
    assert response.status_code == 200, response.text
    assert ["/thumb/" in url for url in tried] == [True, False]
