"""Parks Canada backcountry catalogue from reservation.pc.gc.ca (GoingToCamp / Camis).

The API is undocumented. Everything below was established against live
responses (2026-10-15); the reasoning lives in docs/backcountry-catalog.md.

Discovery is fully data-driven, catalogue endpoints only (never availability):

  searchcriteriatabs   the "Backcountry" tab group -> its booking category ids
  bookingcategories    booking category -> allowed resource category ids
  resourcecategory     resource category names (zone / site / cabin / ...)
  attribute/filterable attribute names (to find "Out of Park")
  maps                 organisation map tree: region -> park -> booking location
  transactionlocation  park offices; their postal code gives the province
  resourceLocation     every booking location and the resource categories it has
  per backcountry location:
    maps?resourceLocationId=...                  published maps (backcountry areas)
    resourcelocation/resources?resourceLocationId=...   the sites themselves

build_catalog() is pure given a get(path) -> JSON callable, so tests run on
saved fixture responses.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PROVIDER = "parks_canada"
BASE_URL = "https://reservation.pc.gc.ca/api/"
LOCALE = "en-CA"

# The API 403s without browser-like headers.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-CA,en;q=0.9",
    "Referer": "https://reservation.pc.gc.ca/create-booking/results",
}

BACKCOUNTRY_TAB_NAME = "Backcountry"
OUT_OF_PARK_ATTRIBUTE = "Out of Park"
# resourceModel 3 = trailhead / access point that isn't itself bookable.
TRAILHEAD_MODEL = 3

CATEGORY_KINDS = {
    "Backcountry Zone": "zone",
    "Backcountry Site": "site",
    "Backcountry Zone Shelter": "shelter",
    "Backcountry Cabin": "cabin",
    "Backcountry Yurt": "yurt",
    "Backpacking Trip": "backpacking_campground",
    "Access Point": "trail_permit",
    "Hiking Trip": "trail_permit",
}

# Banff is the only park in the shared Banff/Kootenay/Yoho booking location
# that suffixes campground names with a trail code ("Allenby Junction - Br17").
SHARED_UNIT_CODED_PARK = {"Banff, Kootenay and Yoho - Backcountry": "Banff"}

SUFFIX_CODE = re.compile(r"^(?P<name>.+?) - (?P<code>[A-Z][a-z]?\d*[A-Z]?)$")  # Banff
PREFIX_CODE = re.compile(r"^(?P<code>\d+[A-Z]?) - (?P<name>.+)$")  # Jasper
BARE_CODE = re.compile(r"^(?=[A-Z0-9-]*\d)[A-Z0-9]{1,6}(?:-\d+)?[A-Z]?$|^[A-Z]{1,2}$")  # "HD1", "SHI-3", "17", "A"

# Canada Post forward sortation: first letter -> province. X is split by FSA.
POSTAL_PROVINCES = {
    "A": "NL", "B": "NS", "C": "PE", "E": "NB", "G": "QC", "H": "QC", "J": "QC",
    "K": "ON", "L": "ON", "M": "ON", "N": "ON", "P": "ON", "R": "MB", "S": "SK",
    "T": "AB", "V": "BC", "Y": "YT",
}
NUNAVUT_FSAS = ("X0A", "X0B", "X0C")


# ---------------------------------------------------------------- HTTP client


class ParksCanadaClient:
    """Polite GET client: fixed delay between live requests, retries with
    exponential backoff on 5xx / 429 / network errors (other 4xx fail fast),
    and an on-disk cache of raw responses so development reruns don't hit
    the server again."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        refresh: bool = False,
        delay_s: float = 1.0,
        max_retries: int = 4,
        timeout_s: float = 30.0,
        log: Callable[[str], None] = print,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.refresh = refresh
        self.delay_s = delay_s
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.log = log
        self.live_requests = 0
        self.cache_hits = 0
        self._last_request_at = 0.0
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, path: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha1(path.encode()).hexdigest()[:20] + ".json")

    def get(self, path: str) -> Any:
        cached = self._cache_path(path)
        if cached and cached.exists() and not self.refresh:
            self.cache_hits += 1
            return json.loads(cached.read_text(encoding="utf-8"))["body"]

        body = self._fetch(path)
        if cached:
            cached.write_text(json.dumps({"path": path, "body": body}), encoding="utf-8")
        return body

    def _fetch(self, path: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            wait = self.delay_s - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.monotonic()
            self.live_requests += 1
            request = urllib.request.Request(BASE_URL + path, headers=HEADERS)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if 400 <= error.code < 500 and error.code != 429:
                    raise
                last_error = error
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                last_error = error
            if attempt < self.max_retries:
                backoff = min(2 ** attempt, 30) + random.uniform(0, 0.5)
                self.log(f"  retry {attempt + 1}/{self.max_retries} for {path} in {backoff:.1f}s: {last_error}")
                time.sleep(backoff)
        raise RuntimeError(f"GET {path} failed after {self.max_retries} retries: {last_error}")


# ---------------------------------------------------------------- records


@dataclass
class ParkRecord:
    provider_park_id: str
    name: str
    province_code: str | None
    region: str | None


@dataclass
class SiteRecord:
    provider_resource_id: str
    provider_location_id: str
    provider_map_id: str | None
    provider_category_id: str
    provider_booking_category_id: str | None
    resource_model: int | None
    park_id: str | None  # provider_park_id
    province_code: str | None
    booking_unit: str
    area: str | None
    name: str
    raw_name: str
    site_code: str | None
    kind: str
    reservable_capacity: int | None
    max_capacity: int | None
    max_group_size: int | None
    is_publicly_listed: bool
    description: str | None
    raw: dict
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class Catalog:
    parks: dict[str, ParkRecord] = field(default_factory=dict)
    sites: list[SiteRecord] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)  # backcountry booking units found
    failed_locations: list[str] = field(default_factory=list)
    excluded: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.failed_locations


# ---------------------------------------------------------------- parsing helpers


def localized(values: list | None, key: str, locale: str = LOCALE):
    for entry in values or []:
        if entry.get("cultureName") == locale:
            return entry.get(key)
    return None


def province_from_postal(postal: str | None) -> str | None:
    postal = (postal or "").strip().upper()
    if not postal:
        return None
    if postal[0] == "X":
        return "NU" if postal[:3] in NUNAVUT_FSAS else "NT"
    return POSTAL_PROVINCES.get(postal[0])


def split_name(raw_name: str) -> tuple[str, str | None]:
    """(display name, site code) from the provider's name."""
    raw_name = raw_name.strip()
    if match := SUFFIX_CODE.match(raw_name):
        return match["name"].strip(), match["code"]
    if match := PREFIX_CODE.match(raw_name):
        return match["name"].strip(), match["code"]
    if BARE_CODE.match(raw_name):
        return raw_name, raw_name
    return raw_name, None


def _int(value) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _as_list(response) -> list:
    # Some list endpoints have been seen wrapped as {"value": [...]} elsewhere.
    return response if isinstance(response, list) else (response or {}).get("value", [])


@dataclass
class _ParkNode:
    map_id: str
    name: str
    region: str | None
    location_ids: list[str]


def _org_tree(maps: list) -> tuple[dict[str, _ParkNode], dict[str, str]]:
    """Park nodes keyed by map id, and booking location id -> park map id.

    The tree is: organisation root -> regions -> (park map -> locations) or
    (location linked straight from the region, which is then its own park)."""
    by_id = {m["mapId"]: m for m in maps}
    root = next((m for m in maps if m.get("isOrganizationRoot")), None)
    if root is None:
        raise ValueError("maps: no organisation root map in response")

    parks: dict[str, _ParkNode] = {}
    location_park: dict[str, str] = {}
    for region_link in root.get("mapLinks", []):
        region_map = by_id.get(region_link["childMapId"])
        if region_map is None:
            continue
        region = localized(region_map["localizedValues"], "title")
        for link in region_map.get("mapLinks", []):
            title = localized(link.get("localizations"), "title")
            map_id = str(link["childMapId"])
            if link.get("resourceLocationId") is not None:
                # Location hung directly off the region: it is the park.
                loc = str(link["resourceLocationId"])
                parks[map_id] = _ParkNode(map_id, title, region, [loc])
                location_park[loc] = map_id
                continue
            park_map = by_id.get(link["childMapId"])
            if park_map is None:
                continue
            node = _ParkNode(map_id, title, region, [])
            _collect_locations(park_map, by_id, node, location_park, seen=set())
            parks[map_id] = node
    return parks, location_park


def _collect_locations(park_map, by_id, node, location_park, seen):
    if park_map["mapId"] in seen:
        return
    seen.add(park_map["mapId"])
    for link in park_map.get("mapLinks", []):
        if link.get("resourceLocationId") is not None:
            loc = str(link["resourceLocationId"])
            node.location_ids.append(loc)
            location_park[loc] = node.map_id
        elif link["childMapId"] in by_id:
            # Nested grouping such as "Banff - Lake Louise" -> "Icefields Parkway".
            _collect_locations(by_id[link["childMapId"]], by_id, node, location_park, seen)


def load_overrides(path: Path | None) -> dict[str, dict]:
    if not path or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(k): v for k, v in data.get(PROVIDER, {}).get("sites", {}).items()}


# ---------------------------------------------------------------- catalogue


def build_catalog(
    get: Callable[[str], Any],
    *,
    park_overrides: dict[str, dict] | None = None,
    log: Callable[[str], None] = print,
) -> Catalog:
    park_overrides = park_overrides or {}
    catalog = Catalog()

    tabs = _as_list(get("searchcriteriatabs"))
    tab = next(
        (t for t in tabs if (t.get("bookingCategoryGroupLocalizedValues") or {}).get(LOCALE) == BACKCOUNTRY_TAB_NAME),
        None,
    )
    if tab is None:
        raise ValueError(f"searchcriteriatabs: no '{BACKCOUNTRY_TAB_NAME}' tab group")
    backcountry_booking_ids = {int(v) for v in tab["childBookingCategoryIds"].values()}

    category_booking: dict[int, int] = {}
    for booking in _as_list(get("bookingcategories")):
        if booking["bookingCategoryId"] in backcountry_booking_ids and not booking.get("isDisabled"):
            for category_id in booking.get("allowedResourceCategoryIds", []):
                category_booking[category_id] = booking["bookingCategoryId"]
    category_names = {
        c["resourceCategoryId"]: localized(c["localizedValues"], "name")
        for c in _as_list(get("resourcecategory"))
    }

    attributes = get("attribute/filterable") or {}
    out_of_park_ids = {
        a["attributeDefinitionId"]
        for a in attributes.values()
        if localized(a.get("localizedValues"), "displayName") == OUT_OF_PARK_ATTRIBUTE
    }
    group_size_ids = {
        a["attributeDefinitionId"]
        for a in attributes.values()
        if localized(a.get("localizedValues"), "displayName") == "Maximum Group Size"
    }

    # The bare "maps" call returns the organisation tree.
    park_nodes, location_park = _org_tree(_as_list(get("maps")))
    offices = {t["transactionLocationId"]: t for t in _as_list(get("transactionlocation"))}
    locations = [l for l in _as_list(get("resourceLocation")) if l.get("rootMapId") is not None]
    location_by_id = {str(l["resourceLocationId"]): l for l in locations}

    def location_province(loc_id: str) -> str | None:
        loc = location_by_id.get(loc_id)
        office = offices.get(loc["transactionLocationId"]) if loc else None
        return province_from_postal(office.get("regionCode")) if office else None

    def park_province(node: _ParkNode) -> str | None:
        for loc_id in node.location_ids:
            if province := location_province(loc_id):
                return province
        return None

    parks_by_name = {node.name: node for node in park_nodes.values()}

    def use_park(node: _ParkNode | None) -> tuple[str | None, str | None]:
        if node is None:
            return None, None
        if node.map_id not in catalog.parks:
            catalog.parks[node.map_id] = ParkRecord(node.map_id, node.name, park_province(node), node.region)
        return node.map_id, catalog.parks[node.map_id].province_code

    for loc in locations:
        if not set(loc.get("resourceCategoryIds", [])) & category_booking.keys():
            continue  # no backcountry categories: frontcountry / day use, never fetched
        loc_id = str(loc["resourceLocationId"])
        unit = localized(loc["localizedValues"], "fullName") or localized(loc["localizedValues"], "shortName")
        catalog.locations.append(unit)
        try:
            maps = _as_list(get(f"maps?resourceLocationId={loc_id}"))
            resources = get(f"resourcelocation/resources?resourceLocationId={loc_id}") or {}
        except Exception as error:  # noqa: BLE001 - one bad location must not abort the run
            catalog.failed_locations.append(unit)
            catalog.warnings.append(f"{unit}: fetch failed ({error}); its sites will not be retired this run")
            log(f"  ! {unit}: {error}")
            continue

        published = {m["mapId"]: localized(m["localizedValues"], "title") for m in maps}
        root_map = loc["rootMapId"]
        # A location without a provincial office (the shared Banff/Kootenay/Yoho
        # unit) spans parks: each site's park is resolved individually below.
        shared_unit = location_province(loc_id) is None
        location_park_node = None if shared_unit else park_nodes.get(location_park.get(loc_id))
        if not shared_unit and location_park_node is None:
            catalog.warnings.append(f"{unit}: not found in the organisation map tree; park left empty")

        values = resources.values() if isinstance(resources, dict) else resources
        for resource in values:
            category_id = resource.get("resourceCategoryId")
            if category_id not in category_booking:
                continue  # e.g. frontcountry campsites in a mixed location
            if resource.get("resourceModel") == TRAILHEAD_MODEL:
                catalog.excluded["trailhead"] = catalog.excluded.get("trailhead", 0) + 1
                continue
            attrs = {a["attributeDefinitionId"]: a for a in resource.get("definedAttributes", [])}
            if attrs.keys() & out_of_park_ids:
                catalog.excluded["out_of_park"] = catalog.excluded.get("out_of_park", 0) + 1
                continue

            resource_id = str(resource["resourceId"])
            raw_name = (localized(resource["localizedValues"], "name") or "").strip()
            name, code = split_name(raw_name)
            map_ids = resource.get("mapIds") or []
            on_published = [m for m in map_ids if m in published]
            map_id = (on_published or map_ids or [None])[0]
            area_map = next((m for m in on_published if m != root_map), None)
            area = published[area_map] if area_map is not None else None

            category_name = category_names.get(category_id)
            kind = CATEGORY_KINDS.get(category_name, "other")
            map_title = (area or "").lower()
            if kind == "zone" and ("random" in map_title or "random" in raw_name.lower()):
                kind = "random_zone"
            elif kind == "zone" and "grazing" in (map_title + " " + raw_name.lower()):
                kind = "horse_camp"
            if kind == "other":
                catalog.warnings.append(f"{unit}: unrecognised backcountry category '{category_name}' on {raw_name}")

            if shared_unit:
                node = None
                override = park_overrides.get(resource_id)
                if override:
                    node = parks_by_name.get(override["park"])
                    if node is None:
                        catalog.warnings.append(f"override for {raw_name}: unknown park '{override['park']}'")
                    if override.get("name") and override["name"] != raw_name:
                        catalog.warnings.append(
                            f"override for {resource_id} expects '{override['name']}' but provider now says '{raw_name}'"
                        )
                elif code and SUFFIX_CODE.match(raw_name) and unit in SHARED_UNIT_CODED_PARK:
                    node = parks_by_name.get(SHARED_UNIT_CODED_PARK[unit])
                elif area:
                    # "Banff Random Camping" -> Banff
                    node = next((n for n in parks_by_name.values() if area.startswith(n.name + " ")), None)
            else:
                node = location_park_node
            park_id, province = use_park(node)

            zone = resource.get("zoneCapacitySettings") or {}
            group_size = next((attrs[i].get("value") for i in group_size_ids if i in attrs), None)
            catalog.sites.append(
                SiteRecord(
                    provider_resource_id=resource_id,
                    provider_location_id=loc_id,
                    provider_map_id=str(map_id) if map_id is not None else None,
                    provider_category_id=str(category_id),
                    provider_booking_category_id=str(category_booking[category_id]),
                    resource_model=resource.get("resourceModel"),
                    park_id=park_id,
                    province_code=province,
                    booking_unit=unit,
                    area=area,
                    name=name,
                    raw_name=raw_name,
                    site_code=code,
                    kind=kind,
                    reservable_capacity=_int(zone.get("capacity")),
                    max_capacity=_int(resource.get("maxCapacity")),
                    max_group_size=_int(group_size),
                    is_publicly_listed=bool(on_published),
                    description=localized(resource["localizedValues"], "description") or None,
                    raw=resource,
                )
            )
    return catalog
