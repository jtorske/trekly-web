"""Find stored user photos that still carry EXIF, GPS or other metadata.

The app re-encodes every avatar, gear and journal photo through a canvas
before upload, which drops all metadata. Photos uploaded before that (gear
photos went up as-is until migration 214aa07bf743) or by a client that
bypassed the app could still hold a location. This downloads every object
in the user-photo buckets and reports any with EXIF (GPS called out), XMP,
or PNG text/eXIf chunks.

    python scripts/scan_photo_metadata.py            # report only
    python scripts/scan_photo_metadata.py --strip    # also re-encode offenders in place

Targets SUPABASE_URL with SUPABASE_SERVICE_ROLE_KEY (the local stack by
default, from backend/.env). --strip on a non-local stack also needs
--allow-remote: rewriting users' files is a hosted write.
"""

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BUCKETS = ("avatars", "gear-photos", "hike-photos")
GPS_IFD = 0x8825


def request(method, url, key, body=None, content_type="application/json", extra=None):
    headers = {"Authorization": f"Bearer {key}", "apikey": key, **(extra or {})}
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers["Content-Type"] = content_type
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=60) as response:
        return response.read()


def list_objects(base, key, bucket, prefix=""):
    """Every object path in `bucket` (folders are listed recursively)."""
    offset = 0
    while True:
        page = json.loads(request("POST", f"{base}/storage/v1/object/list/{bucket}", key,
                                  {"prefix": prefix, "limit": 1000, "offset": offset}))
        for entry in page:
            path = f"{prefix}/{entry['name']}" if prefix else entry["name"]
            if entry.get("id") is None:  # a folder
                yield from list_objects(base, key, bucket, path)
            else:
                yield path, (entry.get("metadata") or {}).get("mimetype")
        if len(page) < 1000:
            return
        offset += 1000


def findings(data: bytes) -> list[str]:
    found = []
    with Image.open(io.BytesIO(data)) as image:
        exif = image.getexif()
        if exif:
            gps = exif.get_ifd(GPS_IFD)
            found.append(f"GPS ({len(gps)} tags)" if gps else f"EXIF ({len(exif)} tags)")
        info = image.info
        if info.get("xmp") or info.get("XML:com.adobe.xmp"):
            found.append("XMP")
        if image.format == "PNG":
            # A colour profile or DPI isn't personal data; text chunks can be.
            text = [k for k in info if k not in ("dpi", "gamma", "transparency", "srgb", "icc_profile", "exif")]
            if text:
                found.append(f"PNG text ({', '.join(text)})")
    return found


def stripped(data: bytes, mimetype: str | None) -> tuple[bytes, str]:
    """Re-encode without metadata, keeping the format the path promises."""
    with Image.open(io.BytesIO(data)) as image:
        image = image.copy()
    out = io.BytesIO()
    fmt = {"image/png": "PNG", "image/webp": "WEBP"}.get(mimetype or "", "JPEG")
    if fmt == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.save(out, fmt, quality=88) if fmt != "PNG" else image.save(out, fmt)
    return out.getvalue(), mimetype or "image/jpeg"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--strip", action="store_true", help="re-encode offending files in place")
    parser.add_argument("--allow-remote", action="store_true", help="permit --strip against a non-local stack")
    args = parser.parse_args()

    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not base or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    local = urllib.parse.urlparse(base).hostname in ("127.0.0.1", "localhost")
    if args.strip and not local and not args.allow_remote:
        sys.exit("Refusing to rewrite files on a non-local stack without --allow-remote.")
    print(f"Scanning {base} ({'local' if local else 'REMOTE'})")

    flagged = scanned = 0
    for bucket in BUCKETS:
        count = 0
        for path, mimetype in list_objects(base, key, bucket):
            count += 1
            url = f"{base}/storage/v1/object/{bucket}/{urllib.parse.quote(path)}"
            try:
                data = request("GET", url, key)
                found = findings(data)
            except (urllib.error.URLError, OSError) as error:
                print(f"  ?? {bucket}/{path}: couldn't read ({error})")
                continue
            if found:
                flagged += 1
                print(f"  !! {bucket}/{path}: {', '.join(found)}")
                if args.strip:
                    clean, content_type = stripped(data, mimetype)
                    request("PUT", url, key, clean, content_type, {"x-upsert": "true"})
                    print(f"     stripped ({len(data)} -> {len(clean)} bytes); still flagged: {findings(clean) or 'nothing'}")
        scanned += count
        print(f"{bucket}: {count} file(s)")
    print(f"\n{scanned} file(s) scanned, {flagged} with metadata")
    return 1 if flagged and not args.strip else 0


if __name__ == "__main__":
    sys.exit(main())
