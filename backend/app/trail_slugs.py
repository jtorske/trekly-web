"""Trail URL slugs: /trails/lake-agnes-tea-house.

A trail's slug is its name in lowercase ASCII with dashes. When two trails
share a name (the Skyline Trails in Jasper and Cape Breton Highlands), each
gets its park added ("skyline-trail-jasper-national-park"), then its
province, then a number, until it's unique.

Slugs are assigned once and never change, so links and search results keep
working when a trail is renamed or a namesake is added later: only the new
trail gets the longer slug. New Trail rows get one on flush (see
`assign_on_flush`), so the catalogue sync and tests need no extra step.
"""

import re
import unicodedata
from collections.abc import Iterable

from sqlalchemy import event, select
from sqlalchemy.orm import Session

MAX_SLUG_LENGTH = 120


def slugify(text: str | None) -> str:
    """'Lake Agnes Tea House' -> 'lake-agnes-tea-house'; accents dropped, '&' -> 'and'."""
    if not text:
        return ""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.replace("&", " and ").replace("'", "").replace("’", "")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH].rstrip("-")


def candidates(name: str, park_name: str | None, province_code: str | None) -> Iterable[str]:
    """Slugs to try in order: the name, + park, + province, then numbered."""
    base = slugify(name) or "trail"
    yield base
    park = slugify(park_name)
    # "Chilkoot Trail" in "Chilkoot Trail National Historic Site": add only the rest.
    if park.startswith(f"{base}-"):
        park = park[len(base) + 1:]
    with_park = f"{base}-{park}" if park and park not in base else base
    if with_park != base:
        yield with_park
    province = slugify(province_code)
    with_province = f"{with_park}-{province}" if province else with_park
    if with_province != with_park:
        yield with_province
    number = 2
    while True:
        yield f"{with_province}-{number}"
        number += 1


def assign_slugs(
    trails: list[tuple[object, str, str | None, str | None, bool]], taken: set[str] = frozenset()
) -> dict:
    """Slugs for (id, name, park_name, province_code, live) rows, avoiding `taken`.

    Namesakes (rows whose plain name slug is the same) all get the longer
    form, so neither owns the short URL; except when only one of them is
    live, which keeps it (a retired namesake shouldn't cost it the clean URL).
    Deterministic: rows are processed in the order given.
    """
    used = set(taken)
    groups: dict[str, list[bool]] = {}
    for _, name, _, _, live in trails:
        groups.setdefault(slugify(name) or "trail", []).append(live)

    out = {}
    for trail_id, name, park_name, province_code, live in trails:
        options = candidates(name, park_name, province_code)
        base = next(options)
        group = groups[base]
        owns_base = len(group) == 1 or (live and group.count(True) == 1)
        if owns_base and base not in used:
            slug = base
        else:
            slug = next(option for option in options if option not in used)
        used.add(slug)
        out[trail_id] = slug
    return out


def assign_on_flush(session: Session, _flush_context, _instances) -> None:
    """Give new Trail rows without a slug a unique one before they're inserted."""
    from app.models.trail import Trail

    new = [obj for obj in session.new if isinstance(obj, Trail) and not obj.slug]
    if not new:
        return
    taken = set(session.execute(select(Trail.slug).where(Trail.slug.is_not(None))).scalars())
    taken |= {obj.slug for obj in session.new if isinstance(obj, Trail) and obj.slug}
    for obj in new:
        obj.slug = next(option for option in candidates(obj.name, obj.park_name, obj.province_code)
                        if option not in taken)
        taken.add(obj.slug)


event.listen(Session, "before_flush", assign_on_flush)
