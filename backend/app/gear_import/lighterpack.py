"""LighterPack CSV import: parse an export and match its items to the catalogue.

Nothing here touches the database or saves anything. The router
(app/routers/me_gear_import.py) loads the catalogue, calls match_rows(), and
shows the user every proposed match with its confidence; items are only
added once they confirm.

A LighterPack export ("Export to CSV") has the columns
    Item Name, Category, desc, qty, weight, unit, url, price, worn, consumable
with weight per item in `unit` (gram, ounce, pound or kilogram) and "Worn" /
"Consumable" in the last two columns when set.

Matching: an item's name and description are compared with each product's
name and aliases. The score is how much of the product's name the item
mentions, raised when the item names the product's brand and lowered when it
names a different brand, when a model number differs ("Exos 58" vs "Exos
55"), or when its weight is far from the product's. CONFIDENCE turns the
score into high / medium / low; below that the item is unmatched and is
offered as a custom item with its own weight.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.catalog.normalize import normalize_text

MAX_ROWS = 500
MAX_NAME = 120
MAX_NOTES = 2000

UNITS = {
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
}
GRAMS = {"g": Decimal(1), "kg": Decimal(1000), "oz": Decimal("28.349523125"), "lb": Decimal("453.59237")}

# Lowest score for each confidence, best first.
CONFIDENCE = (("high", 0.85), ("medium", 0.65), ("low", 0.45))
ALTERNATIVE_MIN = 0.35
MAX_ALTERNATIVES = 2
# The item's weight within this share of the product's (or a variant's) backs the match up.
WEIGHT_CLOSE = 0.15
# Further off than this, it's probably a different product.
WEIGHT_FAR = 0.6

# Subcategory for an item with no catalogue match, by words in its name,
# description or LighterPack category. First match wins, so specific phrases
# come before broad ones.
CATEGORY_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bear-safety", ("bear spray",)),
    ("food-storage", ("bear can", "bear canister", "bear bag", "bearvault", "ursack", "food bag", "odor proof")),
    ("sleeping-pads", ("sleeping pad", "sleep pad", "pad", "mat", "neoair", "z lite", "zlite")),
    ("sleeping-bags", ("sleeping bag",)),
    ("quilts", ("quilt",)),
    ("sleep-liners", ("liner",)),
    ("pillows", ("pillow",)),
    ("footprints", ("footprint", "groundsheet", "ground sheet", "polycryo")),
    ("stakes-guylines", ("stake", "stakes", "peg", "pegs", "guyline", "guy line", "guylines")),
    ("bivy-sacks", ("bivy", "bivvy")),
    ("tarps", ("tarp",)),
    ("tents", ("tent", "shelter", "trekking pole tent", "duplex", "hubba", "copper spur")),
    ("rainwear", ("rain jacket", "rain pants", "rain shell", "poncho", "rain kilt", "rain", "hardshell")),
    ("wind-layers", ("wind shirt", "windshirt", "wind jacket", "windbreaker")),
    ("insulation", ("puffy", "down jacket", "synthetic jacket", "insulated", "down vest", "parka")),
    ("fleece-midlayers", ("fleece", "midlayer", "mid layer", "grid", "hoodie")),
    ("headwear-gloves", ("hat", "beanie", "cap", "toque", "glove", "gloves", "mitt", "mitts", "buff", "balaclava")),
    ("base-layers", (
        "base layer", "baselayer", "shirt", "tee", "t shirt", "leggings", "tights", "underwear", "boxers", "bra",
        "sock", "socks", "shorts", "pants", "trousers",
    )),
    ("gaiters", ("gaiter", "gaiters")),
    ("camp-shoes", ("sandal", "sandals", "camp shoes", "crocs", "flip flops")),
    ("hiking-boots", ("boot", "boots")),
    ("trail-runners", ("trail runner", "trail runners", "shoe", "shoes", "runners")),
    ("water-treatment", ("filter", "purifier", "aquamira", "tablets", "steripen", "sawyer squeeze", "befree")),
    ("bottles-reservoirs", ("bottle", "smartwater", "bladder", "reservoir", "hydration", "water bag", "nalgene")),
    ("fuel-accessories", ("fuel", "canister", "lighter", "matches", "windscreen")),
    ("stoves", ("stove", "burner", "jetboil", "pocketrocket")),
    ("utensils", ("spoon", "spork", "fork", "knife", "utensil")),
    ("cookware", ("pot", "pan", "mug", "cup", "bowl", "cook", "kettle", "pot cozy")),
    ("gps-satellite", ("inreach", "gps", "satellite", "plb", "spot", "zoleo")),
    ("compasses", ("compass",)),
    ("watches", ("watch",)),
    ("first-aid", ("first aid", "firstaid", "med kit", "medical", "blister", "bandage", "meds")),
    ("emergency", ("whistle", "emergency", "space blanket", "signal mirror")),
    ("lighting", ("headlamp", "head lamp", "lamp", "lantern", "flashlight", "torch", "light")),
    ("trekking-poles", ("trekking pole", "trekking poles", "poles", "pole")),
    ("repair", ("repair", "tenacious tape", "patch", "duct tape", "sewing")),
    ("power", ("battery", "power bank", "powerbank", "charger", "cable", "cord", "phone")),
    ("camp-furniture", ("chair", "stool", "sit pad", "sitpad")),
    ("sanitation", (
        "trowel", "toilet", "tp", "wipes", "sanitizer", "soap", "toothbrush", "toothpaste", "bidet", "deodorant",
        "toiletries", "hygiene",
    )),
    ("storage", ("stuff sack", "dry bag", "drybag", "pouch", "stuffsack", "pack liner", "ditty bag")),
    ("pack-accessories", ("rain cover", "pack cover", "hip belt pocket", "shoulder pocket")),
    ("backpacks", ("backpack", "pack")),
)
# When the words say nothing, LighterPack's category heading might.
CATEGORY_HEADINGS: tuple[tuple[str, str], ...] = (
    ("shelter", "tents"), ("sleep", "sleeping-bags"), ("kitchen", "cookware"), ("cook", "cookware"),
    ("water", "bottles-reservoirs"), ("hydration", "bottles-reservoirs"), ("clothing", "base-layers"),
    ("worn", "base-layers"), ("electronics", "power"), ("toiletries", "sanitation"), ("hygiene", "sanitation"),
    ("first aid", "first-aid"), ("navigation", "compasses"), ("safety", "emergency"), ("pack", "backpacks"),
)
FALLBACK_CATEGORY = "misc"


class ImportFileError(ValueError):
    """The file isn't a LighterPack CSV we can read; the message says why."""


@dataclass(frozen=True)
class Row:
    """One item from the export."""

    index: int
    name: str
    category: str
    description: str
    quantity: int
    weight_value: Decimal | None
    weight_unit: str | None
    worn: bool
    consumable: bool

    @property
    def weight_g(self) -> Decimal | None:
        if self.weight_value is None or self.weight_unit is None:
            return None
        return self.weight_value * GRAMS[self.weight_unit]

    @property
    def carry(self) -> str | None:
        return "consumable" if self.consumable else "worn" if self.worn else None


@dataclass(frozen=True)
class Product:
    """What matching needs to know about a catalogue product."""

    id: UUID
    brand: str
    # Brand name and aliases, normalized.
    brand_names: tuple[str, ...]
    name: str
    # Product name and aliases, normalized.
    names: tuple[str, ...]
    category: str
    # The product's weight and each variant's, in grams.
    weights_g: tuple[Decimal, ...] = ()


@dataclass(frozen=True)
class Candidate:
    product: Product
    score: float
    # Lowered from the score's when another product is about as likely.
    capped: str | None = None

    @property
    def confidence(self) -> str:
        label = confidence_for(self.score) or "low"
        if self.capped and [c for c, _ in CONFIDENCE].index(label) < [c for c, _ in CONFIDENCE].index(self.capped):
            return self.capped
        return label


@dataclass
class Match:
    row: Row
    best: Candidate | None
    alternatives: list[Candidate] = field(default_factory=list)
    # For an unmatched item: the subcategory it would be added under.
    category: str = FALLBACK_CATEGORY


def confidence_for(score: float) -> str | None:
    for label, minimum in CONFIDENCE:
        if score >= minimum:
            return label
    return None


# ---------------------------------------------------------------- parsing

def _header_key(value: str) -> str:
    return normalize_text(value).replace(" ", "")


COLUMNS = {
    "itemname": "name", "name": "name", "item": "name",
    "category": "category",
    "desc": "description", "description": "description",
    "qty": "quantity", "quantity": "quantity",
    "weight": "weight", "unit": "unit",
    "worn": "worn", "consumable": "consumable",
}


def _decimal(value: str) -> Decimal | None:
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number.is_finite() and number > 0 else None


def _quantity(value: str) -> int:
    number = _decimal(value)
    if number is None:
        return 1
    return max(1, min(99, int(number)))


def parse_csv(text: str) -> list[Row]:
    """The export's items, in file order. Rows without a name are skipped."""
    text = text.lstrip("﻿")
    if not text.strip():
        raise ImportFileError("That file is empty.")
    try:
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
    except (csv.Error, StopIteration) as error:
        raise ImportFileError("That doesn't look like a CSV file.") from error
    columns = {COLUMNS[key]: i for i, key in enumerate(_header_key(h) for h in header) if key in COLUMNS}
    if "name" not in columns or "weight" not in columns:
        raise ImportFileError(
            "That doesn't look like a LighterPack export. In LighterPack, open your list and choose Export to CSV."
        )

    def cell(cells: list[str], key: str) -> str:
        i = columns.get(key)
        return cells[i].strip() if i is not None and i < len(cells) else ""

    rows: list[Row] = []
    try:
        for cells in reader:
            name = " ".join(cell(cells, "name").split())[:MAX_NAME]
            if not name:
                continue
            if len(rows) >= MAX_ROWS:
                raise ImportFileError(f"That list has more than {MAX_ROWS} items. Split it and import each part.")
            weight = _decimal(cell(cells, "weight"))
            unit = UNITS.get(cell(cells, "unit").lower()) or ("g" if weight is not None else None)
            rows.append(Row(
                index=len(rows),
                name=name,
                category=" ".join(cell(cells, "category").split())[:80],
                description=" ".join(cell(cells, "description").split())[:MAX_NOTES],
                quantity=_quantity(cell(cells, "quantity")),
                weight_value=weight,
                weight_unit=unit if weight is not None else None,
                worn=bool(cell(cells, "worn")),
                consumable=bool(cell(cells, "consumable")),
            ))
    except csv.Error as error:
        raise ImportFileError("Part of that file couldn't be read as CSV.") from error
    if not rows:
        raise ImportFileError("That export has no items in it.")
    return rows


# ---------------------------------------------------------------- matching

NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
# "750ml", "20f", "2p": a number with a unit, compared as the number.
NUMBER_UNIT = re.compile(r"^(\d+(?:\.\d+)?)(?:ml|l|g|oz|f|c|p)$")
# Words that say what kind of thing it is, not which one: they count for a
# little, and a match needs a word that isn't one of them (unless the
# product's whole name is generic, when its brand must be named).
GENERIC = {
    "tent", "tents", "shelter", "jacket", "rain", "shell", "pants", "hoody", "hoodie", "vest", "down", "quilt",
    "sleeping", "bag", "pad", "mat", "pillow", "pack", "backpack", "pot", "cup", "mug", "stove", "filter", "water",
    "bottle", "system", "trekking", "poles", "pole", "trail", "hiking", "boot", "boots", "shoe", "shoes", "mens",
    "womens", "men", "women", "s", "titanium", "ultralight", "lite", "light", "the", "and", "with", "kit",
    "headlamp", "lamp", "classic", "insulated", "air", "person",
}
GENERIC_WEIGHT = 0.3
# A model number the item contradicts ("Exos 48" for an Exos 38) keeps the
# product as an alternative at most, never the proposed match.
CLASH_CEILING = 0.4


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def _words(text: str) -> list[str]:
    out = []
    for word in text.split():
        unit = NUMBER_UNIT.match(word)
        out.append(unit.group(1) if unit else word)
    return out


@dataclass(frozen=True)
class Cover:
    share: float
    """Weighted share of the product name's words the item has (generic words weigh less)."""
    hits: int
    """Words matched (distinctive ones, unless the whole name is generic)."""
    clash: bool = False
    """The item names a different model number."""
    generic_only: bool = False


def _name_cover(tokens: set[str], name: str) -> Cover:
    words = _words(name)
    if not words:
        return Cover(0.0, 0)
    weight = {word: GENERIC_WEIGHT if word in GENERIC else 1.0 for word in words}
    generic_only = all(word in GENERIC for word in words)
    hits = [word for word in words if word in tokens and (generic_only or word not in GENERIC)]
    if not hits:
        return Cover(0.0, 0)
    share = sum(weight[word] for word in words if word in tokens) / sum(weight.values())
    numbers = {word for word in words if NUMBER.match(word)}
    item_numbers = {token for token in tokens if NUMBER.match(token)}
    clash = bool(numbers - item_numbers and item_numbers - numbers)
    return Cover(share, len(hits), clash, generic_only)


def _weight_factor(row: Row, product: Product) -> float:
    grams = row.weight_g
    weights = [weight for weight in product.weights_g if weight > 0]
    if grams is None or not weights:
        return 0.0
    off = min(abs(grams - weight) / weight for weight in weights)
    if off <= WEIGHT_CLOSE:
        return 0.08
    if off >= WEIGHT_FAR:
        return -0.2
    return 0.0


def score(row: Row, product: Product, brand_named: set[str]) -> tuple[float, int, bool]:
    """(score 0-1, words matched, whether the item has the product's whole
    name) for one product. `brand_named` holds the normalized brands the item
    mentions."""
    tokens = set(_words(normalize_text(f"{row.name} {row.description}")))
    cover = max((_name_cover(tokens, name) for name in product.names), key=lambda c: (not c.clash, c.share, c.hits))
    if cover.hits == 0:
        return 0.0, 0, False
    own_brand = bool(set(product.brand_names) & brand_named)
    if cover.generic_only and not own_brand:
        return 0.0, 0, False
    value = 0.7 * cover.share
    if own_brand:
        value += 0.3
    elif brand_named:
        value *= 0.4
    elif cover.share == 1 and cover.hits >= 2:
        # No brand named: a full, distinctive name can still be a good match.
        value += 0.12
    value += _weight_factor(row, product)
    if cover.clash:
        value = min(value, CLASH_CEILING)
    return max(0.0, min(1.0, value)), cover.hits, cover.share == 1 and not cover.clash


def brands_named(row: Row, products: list[Product]) -> set[str]:
    text = " ".join(_words(normalize_text(f"{row.name} {row.description}")))
    return {name for product in products for name in product.brand_names if _contains_phrase(text, name)}


def guess_category(row: Row) -> str:
    text = normalize_text(f"{row.name} {row.description}")
    for slug, phrases in CATEGORY_WORDS:
        if any(_contains_phrase(text, normalize_text(phrase)) for phrase in phrases):
            return slug
    heading = normalize_text(row.category)
    for word, slug in CATEGORY_HEADINGS:
        if _contains_phrase(heading, word):
            return slug
    return FALLBACK_CATEGORY


def match_row(row: Row, products: list[Product]) -> Match:
    named = brands_named(row, products)
    scored = []
    for product in products:
        value, hits, whole = score(row, product, named)
        if value >= ALTERNATIVE_MIN:
            scored.append((value, hits, product, whole))
    # Best score first; on a tie, the product whose name the item covers more of.
    scored.sort(key=lambda item: (-item[0], -item[1], item[2].brand, item[2].name))
    candidates = [Candidate(product, round(value, 3)) for value, _, product, _ in scored]
    # The item lacks part of the best product's name and fits another as well
    # ("Tensor" for any of four Tensor pads): a judgement call, at most medium.
    if len(scored) > 1 and not scored[0][3] and scored[1][1] >= scored[0][1]:
        candidates[0] = Candidate(candidates[0].product, candidates[0].score, capped="medium")
    best = candidates[0] if candidates and confidence_for(candidates[0].score) else None
    rest = candidates[1:] if best else candidates
    return Match(
        row=row,
        best=best,
        alternatives=rest[:MAX_ALTERNATIVES],
        category=best.product.category if best else guess_category(row),
    )


def match_rows(rows: list[Row], products: list[Product]) -> list[Match]:
    return [match_row(row, products) for row in rows]
