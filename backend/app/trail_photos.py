"""Trail photo processing and storage.

Approved candidates and the owner's own uploads go through the same steps:
decode with Pillow (untrusted input: size- and pixel-capped), apply the EXIF
orientation, convert to sRGB, and re-encode as two WebP files, a hero and a
thumbnail. Re-encoding drops all metadata, including any GPS location.

Files go to the public trail-photos bucket through the Storage API with the
service-role key, the one place the backend holds it. The bucket has no
client write policies, so this module is the only writer; callers must have
checked PHOTO_ADMIN_USER_IDS first (see app/routers/admin_trail_photos.py).

Environment:
    SUPABASE_URL               project URL (also used for public file URLs)
    SUPABASE_SERVICE_ROLE_KEY  for uploads and deletes only
"""

import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from uuid import UUID

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

BUCKET = "trail-photos"
HERO_WIDTH = 1600
THUMB_WIDTH = 640
# Smallest source we publish; the search script asks for more (--min-width).
MIN_SOURCE_WIDTH = 1000
MAX_SOURCE_BYTES = 40 * 1024 * 1024
MAX_SOURCE_PIXELS = 80_000_000
WEBP_QUALITY = 80
ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}
# Candidate images are only fetched from these hosts (Commons originals and
# the Flickr copies Openverse links to), so an approve request can't make the
# server fetch an arbitrary URL.
FETCH_HOSTS = ("upload.wikimedia.org", "live.staticflickr.com", ".staticflickr.com")
USER_AGENT = "Trekly-photo-publish/1.0 (jtorske27@gmail.com)"


class PhotoError(ValueError):
    """The image can't be used; the message is safe to show the admin."""


class StorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessedPhoto:
    hero: bytes
    thumb: bytes
    hero_width: int
    hero_height: int


# ---------------------------------------------------------------- processing

def _to_srgb(image: Image.Image) -> Image.Image:
    profile = image.info.get("icc_profile")
    if profile:
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
            converted = ImageCms.profileToProfile(image, source, ImageCms.createProfile("sRGB"), outputMode="RGB")
            if converted is not None:
                return converted
        except (ImageCms.PyCMSError, OSError):
            pass
    return image.convert("RGB")


def _resized(image: Image.Image, width: int) -> Image.Image:
    if image.width <= width:
        return image.copy()
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _webp(image: Image.Image) -> bytes:
    out = io.BytesIO()
    # No exif/icc arguments: the file carries pixels only.
    image.save(out, "WEBP", quality=WEBP_QUALITY, method=6)
    return out.getvalue()


def process_image(data: bytes) -> ProcessedPhoto:
    if len(data) > MAX_SOURCE_BYTES:
        raise PhotoError("That image is over 40 MB.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ACCEPTED_FORMATS:
                raise PhotoError("Use a JPEG, PNG or WebP image.")
            if probe.width * probe.height > MAX_SOURCE_PIXELS:
                raise PhotoError("That image has too many pixels to process.")
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            image = ImageOps.exif_transpose(image)
            image = _to_srgb(image)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as error:
        raise PhotoError("That file isn't an image we can read.") from error
    if image.width < MIN_SOURCE_WIDTH:
        raise PhotoError(f"The image is {image.width}px wide; trail photos need at least {MIN_SOURCE_WIDTH}px.")
    if image.width <= image.height:
        raise PhotoError("Trail photos must be landscape (wider than tall).")
    hero = _resized(image, HERO_WIDTH)
    return ProcessedPhoto(
        hero=_webp(hero),
        thumb=_webp(_resized(image, THUMB_WIDTH)),
        hero_width=hero.width,
        hero_height=hero.height,
    )


# ---------------------------------------------------------------- fetching

def allowed_fetch_url(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or (h.startswith(".") and host.endswith(h)) for h in FETCH_HOSTS)


class _AllowlistRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_fetch_url(newurl):
            raise PhotoError("The image source redirected somewhere unexpected.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_image(url: str) -> bytes:
    """Download a candidate image from an allowlisted host, capped in size."""
    if not allowed_fetch_url(url):
        raise PhotoError("That image isn't hosted on Wikimedia Commons or Flickr.")
    opener = urllib.request.build_opener(_AllowlistRedirects)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(request, timeout=60) as response:
            data = response.read(MAX_SOURCE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise PhotoError("Couldn't download the image from its source. Try again shortly.") from error
    if len(data) > MAX_SOURCE_BYTES:
        raise PhotoError("That image is over 40 MB.")
    return data


# ---------------------------------------------------------------- storage

def public_photo_url(path: str) -> str:
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    return f"{base}/storage/v1/object/public/{BUCKET}/{path}"


def new_paths(trail_id: UUID) -> tuple[str, str]:
    name = uuid.uuid4()
    return f"{trail_id}/{name}-hero.webp", f"{trail_id}/{name}-thumb.webp"


class PhotoStorage:
    """The trail-photos bucket, written with the service-role key.

    The key is read only by storage_from_env() and lives only in this
    object's request headers. It is never logged or put in an error: a
    failed request raises StorageError carrying just the HTTP status, with
    the original exception dropped (`from None`), since a server could echo
    request headers in its error body.
    """

    def __init__(self, supabase_url: str, service_key: str):
        self.base = f"{supabase_url.rstrip('/')}/storage/v1/object"
        # A closure, not an attribute: dumping the object (vars(), an error
        # tracker capturing locals) shows a function, never the key.
        self._auth_headers = lambda: {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def __repr__(self) -> str:
        return f"PhotoStorage({self.base!r})"

    def _send(self, url: str, data: bytes, method: str, headers: dict[str, str]) -> None:
        request = urllib.request.Request(url, data=data, method=method, headers={**self._auth_headers(), "User-Agent": USER_AGENT, **headers})
        status = None
        try:
            with urllib.request.urlopen(request, timeout=60):
                return
        except urllib.error.HTTPError as error:
            status = error.code
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        raise StorageError(f"Storage request failed ({f'HTTP {status}' if status else 'no response'}).") from None

    def upload(self, path: str, data: bytes) -> None:
        self._send(f"{self.base}/{BUCKET}/{path}", data, "POST",
                   {"Content-Type": "image/webp", "x-upsert": "false", "cache-control": "max-age=31536000"})

    def delete(self, paths: list[str]) -> None:
        if not paths:
            return
        self._send(f"{self.base}/{BUCKET}", json.dumps({"prefixes": paths}).encode(), "DELETE",
                   {"Content-Type": "application/json"})


def storage_from_env() -> PhotoStorage | None:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    return PhotoStorage(url, key) if url and key else None
