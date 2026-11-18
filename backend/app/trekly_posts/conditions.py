"""Official trail closures and warnings, read from Parks Canada's bulletin pages.

Each park's "Important bulletins" page (e.g.
https://parks.canada.ca/pn-np/ab/banff/bulletins) lists bulletins as a linked
<h4> title and a date ("November 09, 2026"). There's no feed, so the page is
read as HTML. Only the title, its date and its link are used, word for word:
the post quotes the title, names Parks Canada and the issue date, says it is a
copy of the version on parks.canada.ca (their reproduction terms,
https://parks.canada.ca/termes-terms) and links the bulletin. Nothing here is
generated or paraphrased, and none of it goes near the AI writer.

Avalanche Canada forecasts are left out on purpose: their terms of use forbid
reproducing their material without written consent.
"""

import logging
import re
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

log = logging.getLogger(__name__)

ALLOWED_HOST = "parks.canada.ca"
USER_AGENT = "TreklyBot/1.0 (+https://trekly-web.vercel.app)"
MAX_PAGE_BYTES = 2_000_000
DATE_RE = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December)"
                     r" (\d{1,2}), (\d{4})$")


@dataclass(frozen=True)
class Bulletin:
    park: str
    title: str
    url: str
    issued_on: date
    source_page: str


class _BulletinParser(HTMLParser):
    """Collects (href, h4 title, following date) from the results list."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str, str | None]] = []
        self._href: str | None = None
        self._in_h4 = False
        self._title: list[str] = []
        self._pending: tuple[str, str] | None = None
        self._in_date = False
        self._date: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self._href = attrs.get("href")
        elif tag == "h4" and self._href:
            self._in_h4 = True
            self._title = []
        elif tag == "span" and self._pending and "text-muted" in (attrs.get("class") or ""):
            self._in_date = True
            self._date = []

    def handle_endtag(self, tag):
        if tag == "h4" and self._in_h4:
            self._in_h4 = False
            title = " ".join("".join(self._title).split())
            if title and self._href:
                if self._pending:
                    self.items.append((*self._pending, None))
                self._pending = (self._href, title)
        elif tag == "a":
            self._href = None
        elif tag == "span" and self._in_date:
            self._in_date = False
            if self._pending:
                self.items.append((*self._pending, " ".join("".join(self._date).split())))
                self._pending = None

    def handle_data(self, data):
        if self._in_h4:
            self._title.append(data)
        elif self._in_date:
            self._date.append(data)

    def close(self):
        super().close()
        if self._pending:
            self.items.append((*self._pending, None))
            self._pending = None


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    match = DATE_RE.match(text.strip())
    if not match:
        return None
    try:
        return datetime.strptime(f"{match.group(1)} {int(match.group(2))} {match.group(3)}", "%B %d %Y").date()
    except ValueError:
        return None


def _official_url(url: str, page_url: str) -> bool:
    parsed = urlparse(url)
    page = urlparse(page_url)
    return (parsed.scheme == "https" and parsed.hostname == ALLOWED_HOST
            and parsed.path.startswith(page.path.rstrip("/") + "/"))


def parse_bulletins(html: str, park: str, page_url: str) -> list[Bulletin]:
    """Every dated bulletin on the page that links back under the same page."""
    parser = _BulletinParser()
    parser.feed(html)
    parser.close()
    out = []
    for href, title, raw_date in parser.items:
        issued = parse_date(raw_date)
        if issued is None or not _official_url(href, page_url):
            continue
        out.append(Bulletin(park=park, title=title, url=href, issued_on=issued, source_page=page_url))
    return out


def matches(bulletin: Bulletin, keywords: list[str]) -> bool:
    title = bulletin.title.lower()
    return any(word.lower() in title for word in keywords)


def fetch_page(url: str, timeout: float = 20.0) -> str:
    if urlparse(url).hostname != ALLOWED_HOST:
        raise ValueError(f"Not an official Parks Canada page: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https, fixed host)
        data = response.read(MAX_PAGE_BYTES + 1)
    if len(data) > MAX_PAGE_BYTES:
        raise ValueError("Bulletin page too large")
    return data.decode("utf-8", errors="replace")


def fetch_bulletins(sources: list[dict], fetch=fetch_page) -> tuple[list[Bulletin], list[str]]:
    """Bulletins from every configured page, plus a note per page that failed."""
    bulletins: list[Bulletin] = []
    errors: list[str] = []
    for source in sources:
        try:
            html = fetch(source["url"])
        except Exception as error:  # one park's page being down shouldn't stop the others
            errors.append(f"{source['park']}: {type(error).__name__}")
            continue
        bulletins += parse_bulletins(html, source["park"], source["url"])
    return bulletins, errors
