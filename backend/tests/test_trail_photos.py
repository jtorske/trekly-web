"""Trail photo review and publishing: the admin gate, server-side candidate
lookup, WebP processing, file replacement, and the public photo field."""

import io
import json
import uuid

import pytest
from PIL import Image

from app.main import app
from app.models.account import Profile
from app.models.trail import Trail
from app.routers import admin_trail_photos as admin
from app.trail_photos import allowed_fetch_url

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
def setup(tmp_path, monkeypatch, trails):
    path = tmp_path / "photo_candidates.json"
    path.write_text(json.dumps({"trails": [
        {"name": "Lake Agnes Tea House", "province_code": "AB", "destination": "Lake Agnes Tea House",
         "best_confidence": "high", "default_choice": "commons:1",
         "candidates": [candidate("commons:1"), candidate("commons:2", photographer="Someone Else")]},
        {"name": "Joffre Lakes", "province_code": "BC", "destination": "Joffre Lakes",
         "best_confidence": "off_topic", "default_choice": None, "candidates": [candidate("commons:9")]},
    ]}), encoding="utf-8")
    monkeypatch.setattr(admin, "PHOTO_CANDIDATES_PATH", str(path))
    monkeypatch.setenv("PHOTO_ADMIN_USER_IDS", f"{uuid.uuid4()}, {ADMIN}")
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    storage = FakeStorage()
    fetched = []
    app.dependency_overrides[admin.get_photo_storage] = lambda: storage
    app.dependency_overrides[admin.get_image_fetcher] = lambda: (lambda url: fetched.append(url) or jpeg())
    return {"storage": storage, "fetched": fetched, "agnes": trails[0], "joffre": trails[1]}


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
    # The image came from the candidate file, not from the request.
    assert setup["fetched"] == [IMAGE_URL]

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
