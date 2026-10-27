"""Find candidate landscape photos for each catalogue trail.

Two sources:

- Wikimedia Commons: geosearch around the trail's coordinates, plus a text
  search for its destination, kept only when the file is geotagged near the
  trail.
- Openverse (openverse.org): keyword search by trail name and destination.
  Openverse indexes Flickr and other CC collections; each result records its
  original source (e.g. Flickr). It has no geotags, so a hit must name the
  trail or destination and the region, and it is always low confidence.

Both keep licenses that allow commercial use and modification only (CC BY,
CC BY-SA, CC0, Public Domain), apply the same size and subject filters, and
keep the top --top candidates per trail with the image URL, photographer,
license and source page URL.

Trails with no candidate at 1600px are searched again at 1024px (Openverse
serves Flickr at 1024px only); those candidates are flagged low_res.

Every candidate gets a confidence:
  high       Commons, names the trail or destination
  medium     Commons, geotagged within NEARBY_M of the trailhead
  low        Openverse keyword match (names trail/destination and region)
  off_topic  Commons, only a regional shot
The review page starts a trail on the topo fallback unless its best candidate
is high or medium.

Nothing is downloaded or published: the output is a JSON file for the review
page. Run from backend/:

    python scripts/find_trail_photos.py --out photo_candidates.json
    python scripts/find_trail_photos.py --out photo_candidates.json --only 1 2 3

Responses are cached (--cache), so a rerun repeats no queries. Anonymous
Openverse use allows 20 requests/minute and 200/day; set OPENVERSE_CLIENT_ID
and OPENVERSE_CLIENT_SECRET to use a registered key instead. If the daily
limit runs out, the remaining trails are searched on Commons only and listed.
"""

import argparse
import hashlib
import html
import json
import math
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

CATALOG = Path(__file__).resolve().parent.parent / "catalog_data" / "trails_canada.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1"
USER_AGENT = "Trekly-photo-search/1.0 (jtorske27@gmail.com)"
PAUSE_S = 0.5
OPENVERSE_PAUSE_S = 3.2  # anonymous burst limit is 20/minute

GEO_RADIUS_M = 10000          # Commons geosearch maximum
TEXT_MATCH_RADIUS_M = 25000   # text-search hits must be geotagged this close
NEARBY_M = 3000               # "medium": geotagged this close to the trailhead
MIN_WIDTH = 1600              # enough for a hero after resizing (--min-width)
FALLBACK_MIN_WIDTH = 1024     # only for trails with nothing at MIN_WIDTH (--fallback-min-width)
MIN_ASPECT, MAX_ASPECT = 1.25, 2.4  # landscape; wider is a panorama strip

# Commons license short names that allow commercial use and modification.
COMMONS_LICENSES = re.compile(r"^(cc0|cc[- ]by(-sa)?[- ][\d.]+.*|public domain|pd\b.*|cc[- ]by(-sa)?)$", re.I)
# Openverse license codes; the API filters on these and they are checked again.
OPENVERSE_LICENSES = {"by": "CC BY", "by-sa": "CC BY-SA", "cc0": "CC0", "pdm": "Public Domain Mark"}
OPENVERSE_ORIGINS = {"flickr": "Flickr", "wikimedia": "Wikimedia Commons"}

# Titles, descriptions, categories or tags that mean "not a landscape photo".
NOT_LANDSCAPE = re.compile(
    r"\b(map|maps|diagram|chart|logo|sign|signs|signage|plaque|poster|stamp|postcard|drawing|painting|"
    r"sketch|illustration|interior|museum|menu|portrait|selfie|bear|bears|elk|deer|moose|goat|sheep|"
    r"marmot|pika|squirrel|chipmunk|bird|birds|insect|butterfly|flower|flowers|mushroom|fungi|lichen|"
    r"moss|car|cars|truck|bus|train|locomotive|vehicle|parking|toilet|outhouse|tent|hotel|restaurant|"
    r"screenshot|graph|wedding|people|campers|couple|climbers|group photo|coast guard|station|building|"
    r"construction|house|powerhouse|residence|manor|lodge|hut|shelter|cabin|flag|kayaks?|tractor|rams?|"
    r"bighorn|goose|geese|branta|foliage|plants?|picea|pinus|abies|carex|acer|"
    r"manoir|maison|pavillon|barrage|chambre|façade|bâtiment|gîte|gite|"
    r"iss\d+|view of earth|astronaut|satellite|pictograms?|pictographs?|church|église|eglise|fox|ravens?|"
    r"magpie|hummingbird|sea ?lion|moon|imo \d{7}|mapillary|street|st|rd|tanker|ship|"
    r"inaturalist|store|bären|sculpture|statue)\b",
    re.I,
)
# iNaturalist-style species uploads: "Physarum viride 177577162.jpg",
# "Common ravens (Corvus corax principalis) pair".
SPECIES = re.compile(r"(^[A-Z][a-z]+ [a-z]+ \d{6,}|\([A-Z][a-z]+ [a-z]{3,}( [a-z]+)?\))")
# Keyword hits that share a trail's name but not its place or subject
# ("West coast of Ireland", "Kokanee Glacier Beer", a farmers' market).
ELSEWHERE = re.compile(
    r"\b(ireland|scotland|england|wales|australia|new zealand|usa|united states|washington|oregon|"
    r"california|montana|alaska|idaho|beer|brewery|ale|lager|can|bottle|market|farmers|food|cabbage|"
    r"restaurant|cafe|menu)\b"
)
QUALITY_CATEGORIES = re.compile(r"^(Quality images|Featured pictures|Valued images)", re.I)
GENERIC_WORDS = {"trail", "trails", "the", "loop", "hike", "route", "via", "to", "and", "path", "de", "la", "du", "des"}
# Words in a region name that say nothing about where it is.
REGION_FILLER = GENERIC_WORDS | {
    "national", "park", "provincial", "reserve", "territorial", "parc", "country", "wildland", "site",
    "historic", "of", "lake", "lakes", "mount", "mont", "river", "valley", "north", "south", "east", "west",
}
PROVINCES = {
    "AB": "alberta", "BC": "british columbia", "MB": "manitoba", "NB": "new brunswick", "NL": "newfoundland",
    "NS": "nova scotia", "NT": "northwest territories", "ON": "ontario", "PE": "prince edward island",
    "QC": "quebec", "SK": "saskatchewan", "YT": "yukon",
}
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2, "off_topic": 3}


# ---------------------------------------------------------------- helpers

def haversine_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def strip_html(value):
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fold(text):
    """Lowercase, accents and punctuation dropped: "Crêtes" -> "cretes"."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def distinctive(text, filler=GENERIC_WORDS):
    return [w for w in fold(text).split() if w not in filler and len(w) > 2]


def destination(trail):
    """The place the hike goes to: X in "X via Y", B in "A to B", the high point
    named during verification when there is one, otherwise the trail name."""
    feature = (trail.get("verification") or {}).get("max_elevation_m")
    if isinstance(feature, dict) and feature.get("feature"):
        return re.sub(r"\s*\(.*\)$", "", feature["feature"])
    name = trail["name"]
    parts = [p for p in name_parts(name) if p]
    pick = parts[0] if re.search(r"\bvia\b", name, re.I) else parts[-1]
    words = [w for w in pick.split() if w.lower() not in GENERIC_WORDS]
    return " ".join(words) if len(" ".join(words)) >= 4 else name


def name_parts(name):
    return re.split(r"\s*(?:/|\bto\b|\bvia\b|\s-\s|,)\s*", name, flags=re.I)


def topic_terms(trail, dest):
    """Word sets that identify the trail: its destination, its name, and each
    part of the name ("Egypt Lake / Healy Pass" -> {egypt, lake}, {healy, pass})."""
    sets = [frozenset(distinctive(p)) for p in [dest, trail["name"], *name_parts(trail["name"])]]
    return list(dict.fromkeys(s for s in sets if s))


def region_terms(trail):
    words = set(distinctive(trail["region"], REGION_FILLER))
    words.add(PROVINCES.get(trail["province_code"], ""))
    return [frozenset(w.split()) for w in words if w]


def mentions(text, terms):
    """True if every word of any one term set is in the text. Tags run words
    together ("lakeagnes"), so the squashed text is checked too."""
    folded = fold(text)
    words, squashed = set(folded.split()), folded.replace(" ", "")
    return any(all(w in words or w in squashed for w in term) for term in terms)


def is_landscape(width, height, min_width=MIN_WIDTH):
    if not width or not height or width < min_width:
        return False
    return MIN_ASPECT <= width / height <= MAX_ASPECT


def candidate_text(candidate):
    return " ".join([candidate["title"], candidate["description"], *candidate["_categories"]])


def confidence(candidate, terms):
    if candidate["source"] == "openverse":
        return "low"
    if mentions(candidate_text(candidate), terms):
        return "high"
    if candidate["distance_m"] is not None and candidate["distance_m"] <= NEARBY_M:
        return "medium"
    return "off_topic"


def score(candidate, dest_words):
    """Higher is better within a confidence level: close, big, on-topic, curated."""
    s = 0.0
    if candidate["distance_m"] is not None:
        s += max(0.0, 1.0 - candidate["distance_m"] / TEXT_MATCH_RADIUS_M) * 3
    s += min(candidate["width"], 6000) / 6000
    title = fold(candidate["title"])
    s += sum(1.0 for w in dest_words if w in title)
    if candidate.get("quality"):
        s += 2
    return round(s, 3)


# ---------------------------------------------------------------- remote

class RateLimited(Exception):
    """Openverse's daily request limit is used up."""


def _cache_path(cache_dir, key):
    return cache_dir / (hashlib.sha256(key.encode()).hexdigest()[:20] + ".json")


def get_json(url, params, cache_dir, headers=None, pause=PAUSE_S):
    query = f"{url}?{urllib.parse.urlencode(sorted(params.items()))}"
    cached = _cache_path(cache_dir, query)
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    request = urllib.request.Request(query, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for wait in (0, 10, 30, 60):
        time.sleep(wait or pause)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read())
            cached.write_text(json.dumps(data), encoding="utf-8")
            return data
        except urllib.error.HTTPError as error:
            # A long Retry-After is the daily limit; a short one is the burst limit.
            if error.code == 429 and int(error.headers.get("Retry-After") or 0) > 120:
                raise RateLimited(error.headers.get("Retry-After")) from error
            if error.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError):
            pass
    return None


COMMONS_PROPS = {
    "action": "query", "format": "json", "formatversion": "2",
    "prop": "imageinfo|coordinates|categories",
    "iiprop": "url|size|mime|extmetadata",
    "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl|ImageDescription|ObjectName|DateTimeOriginal",
    "iiurlwidth": "800",
    "clshow": "!hidden", "cllimit": "max", "colimit": "max",
}


def commons_query(params, cache_dir):
    """One generator batch, following prop continuations (categories and
    coordinates are capped per request across all pages) and merging them."""
    pages, extra = {}, {}
    while True:
        data = get_json(COMMONS_API, {**params, **extra}, cache_dir)
        for page in ((data or {}).get("query") or {}).get("pages", []):
            merged = pages.setdefault(page["pageid"], page)
            if merged is not page:
                for key in ("categories", "coordinates"):
                    merged.setdefault(key, []).extend(page.get(key, []))
        extra = {k: v for k, v in ((data or {}).get("continue") or {}).items()}
        if not any(k in extra for k in ("clcontinue", "cocontinue", "iicontinue")):
            return {"query": {"pages": list(pages.values())}}


def commons_geosearch(lat, lon, cache_dir):
    return commons_query({
        **COMMONS_PROPS, "generator": "geosearch", "ggscoord": f"{lat}|{lon}",
        "ggsradius": str(GEO_RADIUS_M), "ggsnamespace": "6", "ggslimit": "100",
    }, cache_dir)


def commons_text_search(text, cache_dir):
    return commons_query({
        **COMMONS_PROPS, "generator": "search", "gsrsearch": f'filetype:bitmap "{text}"',
        "gsrnamespace": "6", "gsrlimit": "50",
    }, cache_dir)


def commons_candidates(data, origin):
    out = []
    for page in ((data or {}).get("query") or {}).get("pages", []):
        info = (page.get("imageinfo") or [None])[0]
        if not info or info.get("mime") != "image/jpeg":
            continue
        meta = {k: strip_html(v.get("value")) for k, v in (info.get("extmetadata") or {}).items()}
        coords = (page.get("coordinates") or [None])[0]
        distance = haversine_m(origin, (coords["lat"], coords["lon"])) if coords else None
        categories = [c["title"].removeprefix("Category:") for c in page.get("categories", [])]
        out.append({
            "source": "commons",
            "origin": "Wikimedia Commons",
            "id": f"commons:{page['pageid']}",
            "title": page["title"].removeprefix("File:"),
            "description": meta.get("ImageDescription", "")[:300],
            "image_url": info["url"],
            "preview_url": info.get("thumburl") or info["url"],
            "width": info.get("width") or 0,
            "height": info.get("height") or 0,
            "photographer": meta.get("Artist") or None,
            "license": meta.get("LicenseShortName", ""),
            "license_url": meta.get("LicenseUrl") or None,
            "source_url": info.get("descriptionurl"),
            "taken": meta.get("DateTimeOriginal") or None,
            "latitude": coords["lat"] if coords else None,
            "longitude": coords["lon"] if coords else None,
            "distance_m": round(distance) if distance is not None else None,
            "quality": any(QUALITY_CATEGORIES.match(c) for c in categories),
            "_categories": categories,
        })
    return out


def openverse_headers():
    """Bearer token for a registered Openverse key, or {} for anonymous use."""
    client_id, secret = os.environ.get("OPENVERSE_CLIENT_ID"), os.environ.get("OPENVERSE_CLIENT_SECRET")
    if not (client_id and secret):
        return {}
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": client_id, "client_secret": secret,
    }).encode()
    request = urllib.request.Request(f"{OPENVERSE_API}/auth_tokens/token/", data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return {"Authorization": f"Bearer {json.loads(response.read())['access_token']}"}


def openverse_search(text, cache_dir, headers):
    # No category filter: most Flickr photos carry none and would be dropped.
    return get_json(f"{OPENVERSE_API}/images/", {
        "q": text, "license": ",".join(OPENVERSE_LICENSES), "mature": "false", "page_size": "20",
    }, cache_dir, headers, pause=OPENVERSE_PAUSE_S)


def openverse_candidates(data):
    out = []
    for item in (data or {}).get("results", []):
        code = item.get("license")
        if code not in OPENVERSE_LICENSES:
            continue
        version = item.get("license_version") or ""
        source = item.get("source") or ""
        out.append({
            "source": "openverse",
            "origin": OPENVERSE_ORIGINS.get(source, source.replace("_", " ").title() or "Unknown"),
            "id": f"openverse:{item['id']}",
            "title": item.get("title") or "",
            "description": "",
            "image_url": item["url"],
            "preview_url": item.get("thumbnail") or item["url"],
            "width": item.get("width") or 0,
            "height": item.get("height") or 0,
            "photographer": (item.get("creator") or "").strip() or None,
            "license": OPENVERSE_LICENSES[code] + (f" {version}" if version and code != "pdm" else ""),
            "license_url": item.get("license_url"),
            "source_url": item.get("foreign_landing_url"),
            "taken": None,
            "latitude": None,
            "longitude": None,
            "distance_m": None,
            "_categories": [t["name"] for t in item.get("tags") or [] if t.get("name")],
        })
    return out


def photo_keys(candidate):
    """Keys that identify one photo across sources. A Commons copy of a Flickr
    photo keeps the Flickr id in its title: "Lake Agnes Tea House (15464773570).jpg"."""
    keys = {candidate["id"]}
    if candidate["origin"] == "Wikimedia Commons":
        keys.add("commons:" + fold(re.sub(r"^File:|\.[a-z]{3,4}$", "", candidate["title"], flags=re.I)))
    for flickr_id in re.findall(r"\b(\d{9,11})\b", f"{candidate['title']} {candidate['source_url'] or ''}"):
        keys.add(f"flickr:{flickr_id}")
    return keys


# ---------------------------------------------------------------- filtering

def rejection(candidate, from_text_search=False, dest="", min_width=MIN_WIDTH, terms=(), region=()):
    """Why a candidate is not a usable landscape photo, or None if it is."""
    if candidate["source"] == "commons" and not COMMONS_LICENSES.match(candidate["license"] or ""):
        return f"license {candidate['license'] or 'unknown'}"
    if not candidate["photographer"] or re.match(r"(unknown|anonymous)\b", candidate["photographer"], re.I):
        return "no photographer to credit"
    # Some Flickr accounts use an email address as their name; we'd publish it in the credit line.
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", candidate["photographer"]):
        return "photographer name is an email address"
    if not is_landscape(candidate["width"], candidate["height"], min_width):
        return "not a large landscape image"
    if candidate["distance_m"] is None and from_text_search:
        return "not geotagged"
    if candidate["distance_m"] is not None and candidate["distance_m"] > TEXT_MATCH_RADIUS_M:
        return "too far from the trail"
    text = candidate_text(candidate)
    # Keyword hits have no location: they must name the trail and its region
    # ("Skyline" alone could be Jasper or Cape Breton).
    # The title must name the trail; tags alone matched "Kokanee Glacier" beer.
    if candidate["source"] == "openverse" and not (mentions(candidate["title"], terms) and mentions(text, region)):
        return "keyword hit does not name the trail and region"
    if candidate["source"] == "openverse" and ELSEWHERE.search(fold(text)):
        return "keyword hit is about somewhere or something else"
    # "BMSCsign.JPG", "Bear_crossing": split camel case and separators into words.
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).replace("_", " ")
    if SPECIES.search(candidate["title"]):
        return "subject is not a landscape"
    # A word that names the destination ("Lake Agnes Tea House") is on topic.
    if any(m.group(0).lower() not in dest.lower() for m in NOT_LANDSCAPE.finditer(words)):
        return "subject is not a landscape"
    return None


def openverse_queries(trail, dest):
    """The trail name, and the destination when it differs; Openverse returns
    nothing for OR or multi-phrase queries, so each is its own request."""
    queries = [re.sub(r"\s*/\s*", " ", trail["name"])]
    if fold(dest) != fold(trail["name"]):
        queries.append(dest)
    return queries


def search_one(trail, cache_dir, top, openverse, min_width):
    """openverse is None (Commons only) or the request headers to use."""
    origin = (trail["latitude"], trail["longitude"])
    dest = destination(trail)
    dest_words = distinctive(dest)
    terms, region = topic_terms(trail, dest), region_terms(trail)

    found = [(c, False) for c in commons_candidates(commons_geosearch(*origin, cache_dir), origin)]
    found += [(c, True) for c in commons_candidates(commons_text_search(dest, cache_dir), origin)]
    if openverse is not None:
        for query in openverse_queries(trail, dest):
            # Not held to the geotag rule: keyword hits are checked by name instead.
            found += [(c, False) for c in openverse_candidates(openverse_search(query, cache_dir, openverse))]

    # Commons comes first, so a photo found on both keeps its full-size
    # Commons copy and geotag.
    seen, kept, rejected = set(), [], {}
    for candidate, from_text in found:
        keys = photo_keys(candidate)
        if keys & seen:
            continue
        seen |= keys
        reason = rejection(candidate, from_text, dest, min_width, terms, region)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        candidate["confidence"] = confidence(candidate, terms)
        candidate["score"] = score(candidate, dest_words)
        kept.append(candidate)

    kept.sort(key=lambda c: (CONFIDENCE_ORDER[c["confidence"]], -c["score"]))
    # One photo per photographer first, so the review offers real alternatives
    # rather than three frames from one series; confidence order still wins.
    picked, photographers = [], set()
    for level in CONFIDENCE_ORDER:
        tier = [c for c in kept if c["confidence"] == level]
        for candidate in tier:
            if candidate["photographer"] not in photographers:
                photographers.add(candidate["photographer"])
                picked.append(candidate)
        picked += [c for c in tier if c not in picked]
    for candidate in picked:
        candidate.pop("_categories", None)
    best = picked[0]["confidence"] if picked else None
    return {
        "rank": trail["rank"],
        "name": trail["name"],
        "region": trail["region"],
        "province_code": trail["province_code"],
        "destination": dest,
        "latitude": trail["latitude"],
        "longitude": trail["longitude"],
        "best_confidence": best,
        # The review page starts here; anything below medium falls back to topo.
        "default_choice": picked[0]["id"] if best in ("high", "medium") else None,
        "considered": len(found),
        "usable": len(picked),
        "rejected": rejected,
        "candidates": picked[:top],
    }


def search_with_fallback(trail, cache_dir, top, openverse, min_width, fallback_width):
    """Search at min_width; a trail with no candidate at all there is searched
    again at fallback_width (from the cache, no extra requests) and its
    candidates are marked low_res so the review page says so."""
    result = search_one(trail, cache_dir, top, openverse, min_width)
    result["low_res"] = False
    if not result["candidates"] and fallback_width and fallback_width < min_width:
        result = search_one(trail, cache_dir, top, openverse, fallback_width)
        result["low_res"] = bool(result["candidates"])
    for candidate in result["candidates"]:
        candidate["low_res"] = candidate["width"] < min_width
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="candidate JSON to write")
    parser.add_argument("--cache", default=".photo-search-cache")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--only", type=int, nargs="*", help="limit to these catalogue ranks")
    parser.add_argument("--commons-only", action="store_true", help="skip Openverse")
    parser.add_argument("--min-width", type=int, default=MIN_WIDTH, help="smallest usable image width (px)")
    parser.add_argument("--fallback-min-width", type=int, default=FALLBACK_MIN_WIDTH,
                        help="for trails with nothing at --min-width; 0 turns the fallback off")
    args = parser.parse_args()

    trails = json.loads(CATALOG.read_text(encoding="utf-8"))["trails"]
    if args.only:
        trails = [t for t in trails if t["rank"] in set(args.only)]
    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)

    openverse = None if args.commons_only else openverse_headers()
    if openverse is not None:
        print(f"Sources: Commons + Openverse ({'registered key' if openverse else 'anonymous'})")
    else:
        print("Sources: Commons only")

    results, skipped = [], []
    for trail in trails:
        if trail.get("latitude") is None:
            continue
        widths = (args.min_width, args.fallback_min_width)
        try:
            result = search_with_fallback(trail, cache_dir, args.top, openverse, *widths)
        except RateLimited as limit:
            print(f"Openverse daily limit reached (retry after {limit}s); continuing with Commons only.")
            openverse = None
            result = search_with_fallback(trail, cache_dir, args.top, openverse, *widths)
        if openverse is None and not args.commons_only:
            skipped.append(trail["name"])
        results.append(result)
        sources = "/".join(sorted({c["source"] for c in result["candidates"]})) or "-"
        print(f"{trail['rank']:>3} {trail['name'][:44]:<44} {result['usable']:>3} usable  "
              f"best={result['best_confidence'] or '-':<9} [{sources}]{' low-res' if result['low_res'] else ''}", flush=True)

    Path(args.out).write_text(json.dumps({
        "generated": date.today().isoformat(),
        "sources": ["commons", *([] if args.commons_only else ["openverse"])],
        "min_width": args.min_width,
        "fallback_min_width": args.fallback_min_width,
        "openverse_skipped": skipped,
        "trails": results,
    }, indent=1, ensure_ascii=False), encoding="utf-8")

    levels = {level: sum(1 for r in results if r["best_confidence"] == level) for level in CONFIDENCE_ORDER}
    print(f"\nBest candidate per trail: " + ", ".join(f"{k} {v}" for k, v in levels.items())
          + f", none {sum(1 for r in results if not r['candidates'])}")
    print(f"Low-resolution fallback ({args.fallback_min_width}px) used for "
          f"{sum(1 for r in results if r['low_res'])} trails with nothing at {args.min_width}px")
    print(f"Photo by default: {sum(1 for r in results if r['default_choice'])}/{len(results)} (rest start on topo)")
    if skipped:
        print(f"Openverse not searched for {len(skipped)} trails (rate limit): {', '.join(skipped)}")
    print(f"Wrote {args.out}. Nothing was downloaded or published.")


if __name__ == "__main__":
    main()
