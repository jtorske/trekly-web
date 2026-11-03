"""Polite fetcher for manufacturer spec pages (catalogue curation helper).

It only downloads pages so a person can read the specs and enter them into
backend/catalog_data/*.json by hand. It never writes catalogue records.

Rules it enforces:
- robots.txt is checked for every URL, against our own User-Agent. A
  disallowed URL is reported and skipped, never fetched.
- At most one request every DELAY seconds per host (robots.txt included).
- It identifies itself in the User-Agent and doesn't retry around blocks:
  403s, 429s and bot challenges are reported as "blocked" and left alone.
- Pages are cached on disk, so re-runs don't hit the site again.

Run from backend/ (needs httpx, from requirements-dev.txt):

    python scripts/catalog_fetch.py fetch urls.txt --cache DIR
    python scripts/catalog_fetch.py text URL --cache DIR [--grep weight,capacity]
    python scripts/catalog_fetch.py check urls.txt     # HEAD/GET status for source_url validation

urls.txt has one URL per line; blank lines and # comments are ignored.
"""

import argparse
import gzip
import hashlib
import html
import json
import re
import sys
import time
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import httpx

USER_AGENT = "TreklyCatalogBot/1.0 (+https://trekly-web.vercel.app; manual gear spec verification)"
ROBOTS_AGENT = "TreklyCatalogBot"
DELAY = 3.0
TIMEOUT = 25.0
CHALLENGE_MARKERS = (
    "cf-browser-verification",
    "challenge-platform",
    "Attention Required! | Cloudflare",
    "Just a moment...",
    "px-captcha",
    "Access Denied",
    "_Incapsula_Resource",
)

_last_hit: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _wait(host: str) -> None:
    elapsed = time.monotonic() - _last_hit.get(host, 0.0)
    if elapsed < DELAY:
        time.sleep(DELAY - elapsed)
    _last_hit[host] = time.monotonic()


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-CA,en;q=0.8"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


def robots_allows(client: httpx.Client, url: str) -> tuple[bool, str]:
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in _robots:
        _wait(parts.netloc)
        try:
            response = client.get(f"{origin}/robots.txt")
        except httpx.HTTPError as error:
            _robots[origin] = None
            return False, f"robots.txt unreachable ({error.__class__.__name__})"
        if response.status_code in (401, 403):
            # Deliberately stricter than RFC 9309 (which lets crawlers treat a
            # 4xx robots.txt as "no rules"): a site that refuses us robots.txt
            # is refusing bots, so we don't crawl it at all.
            _robots[origin] = None
            return False, f"robots.txt returned {response.status_code}"
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(response.text.splitlines() if response.status_code == 200 else [])
        _robots[origin] = parser
    parser = _robots[origin]
    if parser is None:
        return False, "robots.txt not readable"
    return parser.can_fetch(ROBOTS_AGENT, url), "disallowed by robots.txt"


def _cache_path(cache: Path, url: str) -> Path:
    return cache / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")


def fetch(client: httpx.Client, url: str, cache: Path) -> dict:
    path = _cache_path(cache, url)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    allowed, reason = robots_allows(client, url)
    if not allowed:
        result = {"url": url, "status": "skipped", "reason": reason}
    else:
        _wait(urlsplit(url).netloc)
        try:
            response = client.get(url)
            body = response.text
            if url.endswith(".gz") and response.status_code == 200:
                body = gzip.decompress(response.content).decode("utf-8", "replace")
            blocked = response.status_code in (401, 403, 429) or (
                response.status_code == 200 and any(marker in body[:20000] for marker in CHALLENGE_MARKERS)
                and len(body) < 60000
            )
            result = {
                "url": url,
                "final_url": str(response.url),
                "http": response.status_code,
                "status": "blocked" if blocked else ("ok" if response.status_code == 200 else "error"),
                "body": body if response.status_code == 200 and not blocked else "",
            }
        except httpx.HTTPError as error:
            result = {"url": url, "status": "error", "reason": error.__class__.__name__}
    path.write_text(json.dumps(result), encoding="utf-8")
    return result


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
    BLOCK = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "td", "th", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.json_ld: list[str] = []
        self._in_ld = False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and ("type", "application/ld+json") in attrs:
            self._in_ld = True
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            self._in_ld = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_ld:
            self.json_ld.append(data)
        elif not self.skip:
            self.parts.append(data)


def page_text(body: str) -> tuple[str, list[str]]:
    parser = _Text()
    parser.feed(body)
    text = html.unescape("".join(parser.parts))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line), parser.json_ld


def _urls(path: str) -> list[str]:
    return [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def cmd_fetch(args) -> int:
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    with _client() as client:
        for url in _urls(args.urls):
            result = fetch(client, url, cache)
            print(f"{result['status']:>8} {result.get('http', '')} {url} {result.get('reason', '')}", flush=True)
    return 0


def cmd_text(args) -> int:
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    with _client() as client:
        result = fetch(client, args.url, cache)
    if result["status"] != "ok":
        print(f"[{result['status']}] {result.get('http', '')} {result.get('reason', '')}")
        return 1
    text, _ = page_text(result["body"])
    if args.grep:
        pattern = re.compile("|".join(re.escape(word) for word in args.grep.split(",")), re.I)
        lines = text.splitlines()
        keep: set[int] = set()
        for index, line in enumerate(lines):
            if pattern.search(line):
                keep.update(range(max(0, index - args.context), min(len(lines), index + args.context + 1)))
        text = "\n".join(lines[index] for index in sorted(keep))
    print(text[: args.max_chars])
    return 0


def cmd_check(args) -> int:
    failures = 0
    with _client() as client:
        for url in _urls(args.urls):
            allowed, reason = robots_allows(client, url)
            if not allowed:
                print(f"  skipped {url} ({reason})")
                continue
            _wait(urlsplit(url).netloc)
            try:
                status = client.get(url).status_code
            except httpx.HTTPError as error:
                status = error.__class__.__name__
            ok = status == 200
            failures += not ok
            print(f"{'ok' if ok else 'FAIL':>8} {status} {url}", flush=True)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch_cmd = sub.add_parser("fetch")
    fetch_cmd.add_argument("urls")
    fetch_cmd.add_argument("--cache", required=True)
    fetch_cmd.set_defaults(func=cmd_fetch)
    text_cmd = sub.add_parser("text")
    text_cmd.add_argument("url")
    text_cmd.add_argument("--cache", required=True)
    text_cmd.add_argument("--grep")
    text_cmd.add_argument("--context", type=int, default=1)
    text_cmd.add_argument("--max-chars", type=int, default=6000)
    text_cmd.set_defaults(func=cmd_text)
    check_cmd = sub.add_parser("check")
    check_cmd.add_argument("urls")
    check_cmd.set_defaults(func=cmd_check)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
