"""Route-map images: a trail's stored route drawn on Trekly's topo style.

For trails with no photo (none found, or all rejected on /admin/photos) the
site shows these instead of the plain topo background. Each image has the
terrain's real contour lines and a faint hillshade around the route (NRCan
MRDEM-30), the route line from catalog_data/trail_routes.json (OpenStreetMap),
and the trailhead and high point marked, in the cream and green palette.
The trail name is not drawn into the image: the page lays it over the image
the same way it does on the topo fallback, so it stays sharp at every size
and isn't repeated where the name already sits beside the thumbnail.

Images are WebP at the photo sizes (hero 1600 px wide, thumbnail 640 px),
1.6:1, with the route kept inside the area every crop shows (the trail page
crops the hero to 16:7 on desktop and 3:2 on phones).

Two steps, run from backend/:

    python scripts/route_maps.py render --out ../route-maps --font-dir path/to/fonts
    python scripts/route_maps.py upload ../route-maps --dry-run
    python scripts/route_maps.py upload ../route-maps --confirm-host <db host>

`render` draws every trail with a stored route (or --only "Name|AB" ...) into
--out, with a manifest.json; it needs rasterio (requirements-dev.txt) and the
Fraunces Italic and DM Sans variable fonts (Google Fonts, OFL) in --font-dir.
`upload` matches trails in the target database by name and province, uploads
new or changed images to the trail-photos bucket (SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY) and writes trail_route_maps rows; old files are
deleted after the new rows are committed. Writing anywhere but a local
database also needs --confirm-host matching the DATABASE_URL host.

Map data © OpenStreetMap contributors (ODbL). Elevation: MRDEM-30, Natural
Resources Canada, Open Government Licence - Canada. The trail page credits
both under a route-map hero.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BACKEND = Path(__file__).resolve().parents[1]
sys.path.append(str(BACKEND))

ROUTES = BACKEND / "catalog_data" / "trail_routes.json"
MRDEM = "/vsicurl/https://canelevation-dem.s3.ca-central-1.amazonaws.com/mrdem-30/mrdem-30-dtm.tif"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Bump when the drawing changes, so every map is redrawn and re-uploaded.
STYLE_VERSION = 1

# frontend/app/globals.css
CREAM = (254, 250, 224)
OLIVE = (96, 108, 56)
DARK_OLIVE = (40, 54, 24)
RUST = (188, 108, 37)
# The topo fallback's frame: olive 10% over cream.
PAPER = tuple(round(c * 0.9 + o * 0.1) for c, o in zip(CREAM, OLIVE))
# Sea: a cooler, deeper wash of the same greens.
WATER = (196, 205, 178)

HERO = (1600, 1000)
THUMB = (640, 400)
SS = 2  # drawn at 2x, then downsampled: smooth lines without a vector renderer
WEBP_QUALITY = 86

# Where the route may go, as fractions of the image: inside the 16:7 and 3:2
# crops, and clear of the bottom-left corner where the page writes the name.
ROUTE_BOX = {"hero": (0.10, 0.19, 0.90, 0.70), "thumb": (0.12, 0.12, 0.88, 0.66)}
MIN_SPAN_M = 2500  # a short trail still shows some country around it


# ---------------------------------------------------------------- routes

def drawable_routes(path: Path = ROUTES) -> list[dict]:
    """Trails whose stored route has a line (the rest keep the topo)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for key, entry in data["trails"].items():
        route = entry.get("route") or {}
        if route.get("line") and len(route["line"]) >= 2:
            out.append({"key": key, "name": entry["name"], "province_code": entry["province_code"], "route": route})
    return sorted(out, key=lambda t: t["key"])


def route_hash(route: dict) -> str:
    payload = json.dumps({
        "line": [p[:2] for p in route["line"]],
        "trailhead": (route.get("trailhead") or [])[:2],
        "high_point": (route.get("high_point") or [])[:2],
        "style": STYLE_VERSION, "hero": HERO, "thumb": THUMB,
    }, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


# ---------------------------------------------------------------- terrain

class Terrain:
    """MRDEM-30 (EPSG:3979, metres) read by window over HTTP."""

    def __init__(self, url: str = MRDEM):
        import rasterio

        self._env = rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                                 GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2")
        self._env.__enter__()
        self.dataset = rasterio.open(url)

    def project(self, lonlat: list[tuple[float, float]]) -> np.ndarray:
        from rasterio.warp import transform

        xs, ys = transform("EPSG:4326", self.dataset.crs, [p[0] for p in lonlat], [p[1] for p in lonlat])
        return np.column_stack([xs, ys])

    def grid(self, bounds: tuple[float, float, float, float], shape: tuple[int, int]) -> np.ndarray:
        """Elevations over (west, south, east, north) at shape (rows, cols); NaN where missing."""
        from rasterio.enums import Resampling
        from rasterio.windows import from_bounds

        window = from_bounds(*bounds, transform=self.dataset.transform)
        data = self.dataset.read(1, window=window, out_shape=shape, resampling=Resampling.bilinear,
                                 boundless=True, fill_value=self.dataset.nodata if self.dataset.nodata is not None else -9999)
        z = data.astype(np.float64)
        nodata = self.dataset.nodata
        z[(z <= -1000) | ((z == nodata) if nodata is not None else False)] = np.nan
        return z


def smooth(z: np.ndarray, radius: int = 1) -> np.ndarray:
    """Box blur that ignores NaN cells."""
    if radius < 1:
        return z
    valid = ~np.isnan(z)
    filled = np.where(valid, z, 0.0)
    k = 2 * radius + 1

    def blur(a):
        padded = np.pad(a, radius, mode="edge")
        c = padded.cumsum(0).cumsum(1)
        c = np.pad(c, ((1, 0), (1, 0)))
        return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k])

    total, count = blur(filled), blur(valid.astype(np.float64))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = total / count
    out[~valid] = np.nan
    return out


def contour_interval(relief: float) -> int:
    """About 25-40 lines across the map, on a round interval."""
    for step in (5, 10, 20, 25, 50, 100, 200):
        if relief / step <= 40:
            return step
    return 250


def hillshade(z: np.ndarray, cell_m: float) -> np.ndarray:
    """0 (shadow) .. 1 (lit), light from the north-west."""
    filled = np.where(np.isnan(z), np.nanmean(z), z)
    dy, dx = np.gradient(filled, cell_m)
    slope = np.arctan(np.hypot(dx, dy) * 1.4)
    aspect = np.arctan2(-dx, dy)
    az, alt = math.radians(315), math.radians(45)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(shade, 0, 1)


# ---------------------------------------------------------------- drawing

def frame(points: np.ndarray, size: tuple[int, int], box: tuple[float, float, float, float]):
    """Map bounds (west, south, east, north) in metres and metres per pixel,
    so the route fits `box` (fractions of the image) and is centred in it."""
    w, h = size
    bx0, by0, bx1, by1 = box
    (x0, y0), (x1, y1) = points.min(0), points.max(0)
    span_x, span_y = max(x1 - x0, MIN_SPAN_M * (bx1 - bx0)), max(y1 - y0, MIN_SPAN_M * (bx1 - bx0) * h / w)
    mpp = max(span_x / ((bx1 - bx0) * w), span_y / ((by1 - by0) * h))
    # Centre the route in the box, then extend to the whole image.
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    box_cx, box_cy = (bx0 + bx1) / 2 * w, (by0 + by1) / 2 * h
    west = cx - box_cx * mpp
    north = cy + box_cy * mpp
    return (west, north - h * mpp, west + w * mpp, north), mpp


def to_pixels(points: np.ndarray, bounds, mpp: float, scale: float) -> list[tuple[float, float]]:
    west, _, _, north = bounds
    return [((x - west) / mpp * scale, (north - y) / mpp * scale) for x, y in points]


def polyline(draw: ImageDraw.ImageDraw, pts, fill, width: float):
    if len(pts) < 2:
        return
    draw.line(pts, fill=fill, width=max(1, round(width)), joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def font(font_dir: Path, name: str, size: int, weight: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(font_dir / name), size)
    try:
        axes = f.get_variation_axes()
        values = []
        for axis in axes:
            label = axis["name"].decode() if isinstance(axis["name"], bytes) else axis["name"]
            values.append(weight if label.lower() == "weight" else min(max(size, axis["minimum"]), axis["maximum"])
                          if label.lower().startswith("optical") else axis["default"])
        f.set_variation_by_axes(values)
    except OSError:
        pass
    return f


def dense_points(pts, step):
    """Points every `step` pixels along a polyline (for clearance checks)."""
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) // step))
        out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
    return np.array(out + [pts[-1]])


def place_label(draw, f, text, xy, route, taken, size):
    """The first spot beside a marker whose box clears the route, the image
    edge and other labels: right, left, above, below, then the diagonals.
    Falls back to the spot with the most room."""
    x, y = xy
    left, top, right, bottom = draw.textbbox((0, 0), text, font=f, anchor="lm", stroke_width=f.size // 6)
    tw, th = right - left, bottom - top
    gap = f.size * 1.05
    spots = [(x + gap, y), (x - gap - tw, y), (x - tw / 2, y - gap * 1.3), (x - tw / 2, y + gap * 1.3),
             (x + gap * 0.8, y - gap), (x + gap * 0.8, y + gap), (x - gap * 0.8 - tw, y - gap), (x - gap * 0.8 - tw, y + gap)]
    best, best_room = None, -1.0
    margin = f.size * 0.8
    for sx, sy in spots:
        box = (sx, sy - th / 2, sx + tw, sy + th / 2)
        if box[0] < margin or box[2] > size[0] - margin or box[1] < margin or box[3] > size[1] - margin:
            continue
        if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in taken):
            continue
        # Distance from the box to the nearest route point.
        dx = np.maximum(np.maximum(box[0] - route[:, 0], 0), route[:, 0] - box[2])
        dy = np.maximum(np.maximum(box[1] - route[:, 1], 0), route[:, 1] - box[3])
        room = float(np.min(np.hypot(dx, dy))) if len(route) else 1e9
        if room >= f.size * 0.6:
            return box
        if room > best_room:
            best, best_room = box, room
    return best


def label(draw, xy, text, f, anchor):
    draw.text(xy, text, font=f, fill=DARK_OLIVE + (255,), anchor=anchor, stroke_width=max(2, f.size // 6),
              stroke_fill=CREAM + (235,))


def render(trail: dict, terrain: Terrain, variant: str, font_dir: Path) -> bytes:
    size = HERO if variant == "hero" else THUMB
    w, h = size
    W, H = w * SS, h * SS
    route = trail["route"]
    line = terrain.project([(p[1], p[0]) for p in route["line"]])
    bounds, mpp = frame(line, size, ROUTE_BOX[variant])

    # Terrain grid: about 3 image pixels per cell (finer is noise at this scale).
    cols = max(120, w // 3)
    rows = round(cols * h / w)
    z = terrain.grid(bounds, (rows, cols))
    cell_m = (bounds[2] - bounds[0]) / cols

    image = Image.new("RGBA", (W, H), PAPER + (255,))
    if np.isfinite(z).any():
        shade = hillshade(smooth(z, 1), cell_m)
        dark = np.clip(0.78 - shade, 0, 1) * (0.20 if variant == "hero" else 0.24)
        alpha = Image.fromarray(np.nan_to_num(dark * 255).astype(np.uint8), "L").resize((W, H), Image.Resampling.BICUBIC)
        alpha = alpha.filter(ImageFilter.GaussianBlur(SS * 1.5))
        layer = Image.new("RGBA", (W, H), DARK_OLIVE + (0,))
        layer.putalpha(alpha)
        image = Image.alpha_composite(image, layer)

        # Sea (at or below sea level, or no land data offshore): a cool olive wash.
        sea = np.where(np.isnan(z) | (z <= 0.5), 255, 0).astype(np.uint8)
        if sea.any():
            mask = Image.fromarray(sea, "L").resize((W, H), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(SS))
            water = Image.new("RGBA", (W, H), WATER + (0,))
            water.putalpha(mask.point(lambda v: round(v * 0.55)))
            image = Image.alpha_composite(image, water)

        import contourpy

        # Long routes cover a lot of country: smooth more so the lines read as terrain, not noise.
        zs = smooth(z, 2 if mpp < 15 else 3)
        lo, hi = np.nanmin(zs), np.nanmax(zs)
        step = contour_interval(hi - lo)
        generator = contourpy.contour_generator(z=np.where(np.isnan(zs), lo - 1000, zs))
        lines = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(lines)
        sx, sy = W / (cols - 1), H / (rows - 1)
        minor_w, index_w = (1.3, 2.6) if variant == "hero" else (1.0, 2.0)
        # No contours at or below sea level (the coastline is the water's edge).
        for level in np.arange(max(math.ceil(lo / step) * step, step), hi, step):
            index = round(level / step) % 5 == 0
            colour = DARK_OLIVE + (round(255 * (0.30 if index else 0.20)),)
            for seg in generator.lines(level):
                if len(seg) < 3:
                    continue
                pts = [(x * sx, y * sy) for x, y in seg]
                draw.line(pts, fill=colour, width=round((index_w if index else minor_w) * SS), joint="curve")
        image = Image.alpha_composite(image, lines)

    draw = ImageDraw.Draw(image)
    pts = to_pixels(line, bounds, mpp, SS)
    casing, core = (12, 6) if variant == "hero" else (8, 4.2)
    polyline(draw, pts, CREAM + (255,), casing * SS)
    polyline(draw, pts, DARK_OLIVE + (255,), core * SS)

    marks = []
    for kind in ("high_point", "trailhead"):  # trailhead on top
        point = route.get(kind)
        if point:
            xy = to_pixels(terrain.project([(point[1], point[0])]), bounds, mpp, SS)[0]
            marks.append((kind, xy))
    big = variant == "hero"
    for kind, (x, y) in marks:
        if kind == "trailhead":
            r = (11 if big else 7) * SS
            ring = (3.5 if big else 2.5) * SS
            draw.ellipse((x - r - ring, y - r - ring, x + r + ring, y + r + ring), fill=CREAM + (255,))
            draw.ellipse((x - r, y - r, x + r, y + r), fill=DARK_OLIVE + (255,))
            inner = r * 0.38
            draw.ellipse((x - inner, y - inner, x + inner, y + inner), fill=CREAM + (255,))
        else:
            s = (15 if big else 9.5) * SS
            outline = (3.5 if big else 2.5) * SS
            tri = [(x, y - s), (x + s * 0.95, y + s * 0.62), (x - s * 0.95, y + s * 0.62)]
            grow = [(x, y - s - outline * 1.6), (x + (s + outline * 1.4) * 0.95, y + (s + outline) * 0.62 + outline * 0.4),
                    (x - (s + outline * 1.4) * 0.95, y + (s + outline) * 0.62 + outline * 0.4)]
            draw.polygon(grow, fill=CREAM + (255,))
            draw.polygon(tri, fill=RUST + (255,))

    if big and font_dir:
        f = font(font_dir, "DMSans.ttf", 22 * SS, 600)
        taken = []  # label boxes already placed
        dense = dense_points(pts, 6 * SS)
        for kind, (x, y) in reversed(marks):  # trailhead first
            text = "Trailhead" if kind == "trailhead" else "High point"
            box = place_label(draw, f, text, (x, y), dense, taken, (W, H))
            if box:
                taken.append(box)
                label(draw, (box[0], (box[1] + box[3]) / 2), text, f, "lm")

    out = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    out.save(buffer, "WEBP", quality=WEBP_QUALITY, method=6)
    return buffer.getvalue()


# ---------------------------------------------------------------- commands

def cmd_render(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    trails = drawable_routes()
    if args.only:
        wanted = {tuple(o.split("|", 1)) for o in args.only}
        trails = [t for t in trails if (t["name"], t["province_code"]) in wanted]
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    terrain = Terrain()
    font_dir = Path(args.font_dir) if args.font_dir else None
    for i, trail in enumerate(trails, 1):
        digest = route_hash(trail["route"])
        entry = manifest.get(trail["key"])
        files = {v: out / f"{trail['key']}-{digest}-{v}.webp" for v in ("hero", "thumb")}
        if entry and entry["hash"] == digest and all(p.exists() for p in files.values()) and not args.force:
            print(f"{i:>3}/{len(trails)} {trail['name']}: unchanged")
            continue
        for variant, path in files.items():
            path.write_bytes(render(trail, terrain, variant, font_dir))
        with Image.open(files["hero"]) as hero:
            hero_size = hero.size
        manifest[trail["key"]] = {
            "name": trail["name"], "province_code": trail["province_code"], "hash": digest,
            "hero": files["hero"].name, "thumb": files["thumb"].name,
            "hero_width": hero_size[0], "hero_height": hero_size[1],
            "bytes": {v: p.stat().st_size for v, p in files.items()},
        }
        manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{i:>3}/{len(trails)} {trail['name']}: {manifest[trail['key']]['bytes']['hero'] // 1024} KB hero", flush=True)
    print(f"Rendered into {out}. Nothing was uploaded.")
    return 0


def plan_upload(db, manifest: dict) -> dict:
    """What an upload would do, by trail: new, changed (redrawn) or unchanged,
    plus which matched trails show it now (no photo)."""
    from app.models.trail import Trail
    from app.models.trail_photo import TrailPhoto, TrailRouteMap

    from sqlalchemy import inspect

    from sqlalchemy.orm import noload

    trails = {(t.name, t.province_code): t
              for t in db.query(Trail).options(noload("*")).filter(Trail.retired_at.is_(None)).all()}
    # A dry run works before migration b9e4d2a7c1f6 (every map is then new); an upload doesn't.
    table_exists = inspect(db.get_bind()).has_table(TrailRouteMap.__tablename__)
    existing = {r.trail_id: r for r in db.query(TrailRouteMap).all()} if table_exists else {}
    with_photo = {r.trail_id for r in db.query(TrailPhoto.trail_id).all()}
    plan = {"new": [], "changed": [], "unchanged": [], "unmatched": [], "shown": [], "table_exists": table_exists}
    for key, entry in sorted(manifest.items()):
        trail = trails.get((entry["name"], entry["province_code"]))
        if trail is None:
            plan["unmatched"].append(entry["name"])
            continue
        row = existing.get(trail.id)
        state = "new" if row is None else "unchanged" if row.route_hash == entry["hash"] else "changed"
        plan[state].append((trail, entry, row))
        if trail.id not in with_photo:
            plan["shown"].append(entry["name"])
    return plan


def cmd_upload(args) -> int:
    from app.database import SessionLocal, engine
    from app.models.trail_photo import TrailRouteMap
    from app.trail_photos import StorageError, storage_from_env

    source = Path(args.dir)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    host = engine.url.host or ""
    local = host in LOCAL_HOSTS
    print(f"Target database host: {host} ({'local' if local else 'NOT local'})")
    if not args.dry_run and not local and args.confirm_host != host:
        sys.exit(f"Refusing to write to {host}: pass --confirm-host {host} to confirm.")
    storage = None if args.dry_run else storage_from_env()
    if not args.dry_run and storage is None:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are needed to upload.")

    db = SessionLocal()
    try:
        plan = plan_upload(db, manifest)
        print(f"Route maps in {source}: {len(manifest)}")
        print(f"New: {len(plan['new'])}, redrawn: {len(plan['changed'])}, unchanged: {len(plan['unchanged'])}, "
              f"unmatched: {len(plan['unmatched'])}")
        for name in plan["unmatched"]:
            print(f"  unmatched: {name}")
        if not plan["table_exists"]:
            print("trail_route_maps doesn't exist yet: run migration b9e4d2a7c1f6 before uploading.")
        print(f"Shown now (trail has no photo): {len(plan['shown'])}")
        for name in plan["shown"]:
            print(f"  - {name}")
        if args.dry_run:
            print("Dry run: nothing uploaded or written.")
            return 0
        if not plan["table_exists"]:
            sys.exit("Run migration b9e4d2a7c1f6 first; nothing uploaded.")
        stale = []
        for trail, entry, row in plan["new"] + plan["changed"]:
            hero_path = f"{trail.id}/route-map-{entry['hash']}-hero.webp"
            thumb_path = f"{trail.id}/route-map-{entry['hash']}-thumb.webp"
            try:
                storage.upload(hero_path, (source / entry["hero"]).read_bytes(), upsert=True)
                storage.upload(thumb_path, (source / entry["thumb"]).read_bytes(), upsert=True)
            except StorageError as error:
                db.rollback()
                sys.exit(f"Upload failed for {entry['name']}: {error}. Database unchanged; rerun to retry.")
            if row is not None:
                stale += [row.hero_path, row.thumb_path]
            db.merge(TrailRouteMap(trail_id=trail.id, hero_path=hero_path, thumb_path=thumb_path,
                                   hero_width=entry["hero_width"], hero_height=entry["hero_height"],
                                   route_hash=entry["hash"]))
            print(f"  uploaded {entry['name']}", flush=True)
        db.commit()
        if stale:
            try:
                storage.delete(stale)
            except StorageError as error:
                print(f"Couldn't delete {len(stale)} replaced files ({error}); they're unreferenced.")
        print(f"Wrote {len(plan['new']) + len(plan['changed'])} route maps.")
        return 0
    finally:
        db.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("render", help="draw route maps into a folder")
    r.add_argument("--out", required=True)
    r.add_argument("--font-dir", help="folder with Fraunces-Italic.ttf and DMSans.ttf (marker labels)")
    r.add_argument("--only", nargs="*", help='"Trail name|AB" ...')
    r.add_argument("--force", action="store_true", help="redraw unchanged routes too")
    u = sub.add_parser("upload", help="upload rendered maps and write trail_route_maps")
    u.add_argument("dir")
    u.add_argument("--dry-run", action="store_true")
    u.add_argument("--confirm-host")
    args = parser.parse_args(argv)
    return cmd_render(args) if args.command == "render" else cmd_upload(args)


if __name__ == "__main__":
    sys.exit(main())
