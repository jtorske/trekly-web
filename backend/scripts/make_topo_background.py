"""Generate a topographic contour SVG for the site background from NRCan's CDEM.

One-off tool: run it by hand when adding or changing a background. It is not
part of any build. The output is committed (frontend/public/topo/*.svg) and
used as a CSS mask, so the contours take their colour from the page's ink
token (see frontend/components/TopoBackground.tsx).

Data: Canadian Digital Elevation Model (CDEM), Natural Resources Canada.
Contains information licensed under the Open Government Licence – Canada
(https://open.canada.ca/en/open-government-licence-canada). Tiles are 1:250k
NTS sheets, e.g. Mount Assiniboine is in 082J:

    https://ftp.maps.canada.ca/pub/nrcan_rncan/elevation/cdem_mnec/082/cdem_dem_082J_tif.zip

Download the zip somewhere outside the repo, then (from backend/):

    python scripts/make_topo_background.py path/to/cdem_dem_082J_tif.zip \\
        --bbox -115.80 50.80 -115.50 50.94 --name mount-assiniboine

Steps: read the GeoTIFF (16-bit, geographic NAD83, 0.75 arc-second cells)
with Pillow, crop to the bounding box, smooth lightly, trace contours with
contourpy every --interval metres (every --index-every-th line goes in a
heavier "index" path), simplify them (Douglas–Peucker), drop tiny loops, and
write compact relative path data into one SVG.

Needs: numpy, contourpy, Pillow (no GDAL).
"""

from __future__ import annotations

import argparse
import math
import sys
import zipfile
from pathlib import Path

import contourpy
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
NODATA = -32767
ATTRIBUTION = (
    "Contours generated from the Canadian Digital Elevation Model (CDEM), Natural Resources Canada. "
    "Contains information licensed under the Open Government Licence - Canada."
)


def read_cdem(source: Path) -> tuple[np.ndarray, float, float, float, float]:
    """(elevation array, west, north, lon step, lat step) from a CDEM zip or .tif."""
    Image.MAX_IMAGE_PIXELS = None
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            name = next(n for n in archive.namelist() if n.lower().endswith(".tif"))
            with archive.open(name) as handle:
                image = Image.open(handle)
                image.load()
    else:
        image = Image.open(source)
        image.load()
    scale = image.tag_v2[33550]  # ModelPixelScale
    tie = image.tag_v2[33922]  # ModelTiepoint: (i, j, k, x, y, z)
    data = np.asarray(image, dtype=np.float32)
    return data, tie[3], tie[4], scale[0], scale[1]


def crop(data, west, north, dlon, dlat, bbox):
    w, s, e, n = bbox
    c0, c1 = int(round((w - west) / dlon)), int(round((e - west) / dlon))
    r0, r1 = int(round((north - n) / dlat)), int(round((north - s) / dlat))
    if c0 < 0 or r0 < 0 or c1 > data.shape[1] or r1 > data.shape[0]:
        sys.exit(f"bbox {bbox} is outside this tile")
    out = data[r0:r1, c0:c1].copy()
    if (out == NODATA).any():
        sys.exit("bbox contains no-data cells; pick an area fully inside the tile")
    return out


def box_blur(z: np.ndarray, radius: int) -> np.ndarray:
    """Separable box blur (edges padded), applied twice ≈ a light Gaussian."""
    if radius <= 0:
        return z
    for _ in range(2):
        for axis in (0, 1):
            padded = np.pad(z, [(radius, radius) if a == axis else (0, 0) for a in (0, 1)], mode="edge")
            csum = np.cumsum(padded, axis=axis, dtype=np.float64)
            csum = np.insert(csum, 0, 0, axis=axis)
            size = 2 * radius + 1
            hi = np.take(csum, range(size, csum.shape[axis]), axis=axis)
            lo = np.take(csum, range(0, csum.shape[axis] - size), axis=axis)
            z = ((hi - lo) / size).astype(np.float32)
    return z


def simplify(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Douglas–Peucker, iterative."""
    if len(points) < 3:
        return points
    keep = np.zeros(len(points), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        p, q = points[a], points[b]
        seg = points[a + 1:b]
        d = q - p
        norm = math.hypot(*d)
        if norm == 0:
            dist = np.hypot(*(seg - p).T)
        else:
            dist = np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / norm
        i = int(np.argmax(dist))
        if dist[i] > tolerance:
            mid = a + 1 + i
            keep[mid] = True
            stack += [(a, mid), (mid, b)]
    return points[keep]


def path_data(lines: list[np.ndarray]) -> str:
    """Compact SVG path data: integer coordinates, relative moves after the first point."""
    parts = []
    for line in lines:
        pts = np.round(line).astype(int)
        # Drop repeated points created by rounding.
        pts = pts[np.r_[True, np.any(np.diff(pts, axis=0) != 0, axis=1)]]
        if len(pts) < 2:
            continue
        deltas = np.diff(pts, axis=0)
        parts.append(f"M{pts[0][0]} {pts[0][1]}l" + _join(deltas))
    return "".join(parts)


def _join(deltas: np.ndarray) -> str:
    """dx dy pairs for an "l" command; a minus sign doubles as the separator."""
    out = []
    for dx, dy in deltas:
        for v in (int(dx), int(dy)):
            if out and v >= 0:
                out.append(" ")
            out.append(str(v))
    return "".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="CDEM tile: cdem_dem_XXXX_tif.zip or the .tif inside it")
    parser.add_argument("--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"), required=True)
    parser.add_argument("--name", required=True, help="output name, e.g. mount-assiniboine")
    parser.add_argument("--label", default=None, help="place name for the SVG title (default: from --name)")
    parser.add_argument("--interval", type=float, default=50, help="contour interval in metres (default 50)")
    parser.add_argument("--index-every", type=int, default=5, help="every Nth contour is an index line (default 5)")
    parser.add_argument("--width", type=int, default=2400, help="SVG viewBox width (default 2400)")
    parser.add_argument("--smooth", type=int, default=2, help="box-blur radius in cells before contouring (default 2)")
    parser.add_argument("--tolerance", type=float, default=2.0, help="simplification tolerance in viewBox units")
    parser.add_argument("--min-length", type=float, default=40, help="drop contours shorter than this (viewBox units)")
    parser.add_argument("--out-dir", type=Path, default=REPO / "frontend" / "public" / "topo")
    args = parser.parse_args(argv)

    data, west, north, dlon, dlat = read_cdem(args.source)
    z = box_blur(crop(data, west, north, dlon, dlat, args.bbox), args.smooth)
    rows, cols = z.shape

    # Equirectangular → metres, so contours aren't stretched east-west.
    w, s, e, n = args.bbox
    mid_lat = math.radians((s + n) / 2)
    width_m = (e - w) * 111_320 * math.cos(mid_lat)
    height_m = (n - s) * 110_574
    width = args.width
    height = round(width * height_m / width_m)
    sx, sy = width / (cols - 1), height / (rows - 1)

    lo = math.ceil(float(z.min()) / args.interval) * args.interval
    hi = math.floor(float(z.max()) / args.interval) * args.interval
    generator = contourpy.contour_generator(z=z.astype(np.float64))
    minor, index = [], []
    stats = {"levels": 0, "lines": 0, "points": 0}
    level = lo
    while level <= hi:
        is_index = round(level / args.interval) % args.index_every == 0
        for line in generator.lines(level):
            pts = np.column_stack([line[:, 0] * sx, line[:, 1] * sy])
            if np.sum(np.hypot(*np.diff(pts, axis=0).T)) < args.min_length:
                continue
            pts = simplify(pts, args.tolerance)
            (index if is_index else minor).append(pts)
            stats["lines"] += 1
            stats["points"] += len(pts)
        stats["levels"] += 1
        level += args.interval

    label = args.label or args.name.replace("-", " ").title()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'fill="none" stroke="#000" stroke-linejoin="round" stroke-linecap="round">'
        f"<title>{label}: {args.interval:g} m contours</title>"
        f"<desc>{ATTRIBUTION} Area {w},{s} to {e},{n}; elevations {lo:g}-{hi:g} m.</desc>"
        f'<path stroke-width="1.6" d="{path_data(minor)}"/>'
        f'<path stroke-width="3.2" d="{path_data(index)}"/>'
        "</svg>"
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.name}.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"{out}: {len(svg.encode()) / 1024:.0f} KB, {width}x{height}, "
          f"{stats['levels']} levels ({lo:g}-{hi:g} m), {stats['lines']} lines, {stats['points']} points")
    return 0


if __name__ == "__main__":
    sys.exit(main())
