"""The stored-photo metadata scanner finds GPS/EXIF and strips it cleanly."""

import io
import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scan_photo_metadata import GPS_IFD, findings, stripped  # noqa: E402


def photo(fmt="JPEG", gps=True):
    image = Image.new("RGB", (32, 24), (90, 120, 60))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    if gps:
        exif.get_ifd(GPS_IFD).update({1: "N", 2: (51.0, 25.0, 0.0), 3: "W", 4: (116.0, 10.0, 0.0)})
    out = io.BytesIO()
    image.save(out, fmt, exif=exif)
    return out.getvalue()


@pytest.mark.parametrize("fmt", ["JPEG", "WEBP", "PNG"])
def test_finds_gps(fmt):
    assert findings(photo(fmt))[0].startswith("GPS")


def test_finds_plain_exif():
    assert findings(photo(gps=False))[0].startswith("EXIF")


def test_clean_image_has_no_findings():
    out = io.BytesIO()
    Image.new("RGB", (8, 8)).save(out, "WEBP")
    assert findings(out.getvalue()) == []


@pytest.mark.parametrize("fmt, mimetype", [("JPEG", "image/jpeg"), ("WEBP", "image/webp"), ("PNG", "image/png")])
def test_strip_removes_everything_and_keeps_the_format(fmt, mimetype):
    clean, content_type = stripped(photo(fmt), mimetype)
    assert findings(clean) == []
    assert content_type == mimetype
    with Image.open(io.BytesIO(clean)) as image:
        assert image.format == fmt and image.size == (32, 24)
