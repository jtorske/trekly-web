"""Normalization helpers: text, slugs and exact unit conversion.

Conversions use Decimal throughout so the canonical value is exactly what the
published figure implies (e.g. 2.9 oz -> 82.214 g), rounded only once to the
column scale (3 decimals for grams, 1 for millilitres). Nothing here guesses a
missing value: an absent or unparseable measurement stays None or raises.
"""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

GRAMS_PER_UNIT = {
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "oz": Decimal("28.349523125"),  # avoirdupois ounce, exact by definition
    "lb": Decimal("453.59237"),  # international pound, exact by definition
}

ML_PER_UNIT = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "fl_oz": Decimal("29.5735295625"),  # US fluid ounce, exact by definition
    "cu_in": Decimal("16.387064"),  # cubic inch, exact by definition
}

GRAMS_SCALE = Decimal("0.001")
ML_SCALE = Decimal("0.1")


class MeasurementError(ValueError):
    pass


def normalize_text(value: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace.

    Used for search documents, alias matching and slugs, so "Arc'teryx",
    "ARCTERYX" and "Arcteryx" all normalize to "arcteryx".
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_marks.lower().replace("&", " and ")
    # Apostrophes join words ("arc'teryx" -> "arcteryx"); other punctuation splits them.
    lowered = re.sub(r"['’`]", "", lowered)
    lowered = re.sub(r"[^a-z0-9.]+", " ", lowered)
    lowered = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", lowered)  # keep decimals like 2.5
    return re.sub(r"\s+", " ", lowered).strip()


def slugify(value: str) -> str:
    return normalize_text(value).replace(".", "-").replace(" ", "-")


def to_decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise MeasurementError(f"Not a number: {value!r}")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as error:
        raise MeasurementError(f"Not a number: {value!r}") from error
    if not result.is_finite():
        raise MeasurementError(f"Not a finite number: {value!r}")
    return result


def grams_from(value: object, unit: str) -> Decimal:
    unit = unit.lower()
    if unit not in GRAMS_PER_UNIT:
        raise MeasurementError(f"Unknown mass unit {unit!r}")
    grams = to_decimal(value) * GRAMS_PER_UNIT[unit]
    if grams < 0:
        raise MeasurementError("Mass cannot be negative")
    return grams.quantize(GRAMS_SCALE, rounding=ROUND_HALF_UP)


def grams_to(grams: Decimal, unit: str) -> Decimal:
    unit = unit.lower()
    if unit not in GRAMS_PER_UNIT:
        raise MeasurementError(f"Unknown mass unit {unit!r}")
    return Decimal(grams) / GRAMS_PER_UNIT[unit]


def ml_from(value: object, unit: str) -> Decimal:
    unit = unit.lower()
    if unit not in ML_PER_UNIT:
        raise MeasurementError(f"Unknown volume unit {unit!r}")
    ml = to_decimal(value) * ML_PER_UNIT[unit]
    if ml <= 0:
        raise MeasurementError("Volume must be positive")
    return ml.quantize(ML_SCALE, rounding=ROUND_HALF_UP)


_LB_OZ = re.compile(
    r"^\s*(?:(?P<lb>\d+(?:\.\d+)?)\s*(?:lb|lbs)\.?)?\s*,?\s*"
    r"(?:(?P<oz>\d+(?:\.\d+)?)\s*oz\.?)?\s*$",
    re.IGNORECASE,
)
_SIMPLE = re.compile(r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|oz|lb|lbs)\.?\s*$", re.IGNORECASE)


def parse_weight_text(text: str) -> Decimal:
    """Parse a published weight like "2 lb 3 oz", "14.1 oz", "1.2 kg" or "505 g" to grams."""
    simple = _SIMPLE.match(text)
    if simple:
        unit = simple.group("unit").lower().replace("lbs", "lb")
        return grams_from(simple.group("value"), unit)
    combined = _LB_OZ.match(text)
    if combined and (combined.group("lb") or combined.group("oz")):
        grams = Decimal(0)
        if combined.group("lb"):
            grams += to_decimal(combined.group("lb")) * GRAMS_PER_UNIT["lb"]
        if combined.group("oz"):
            grams += to_decimal(combined.group("oz")) * GRAMS_PER_UNIT["oz"]
        return grams.quantize(GRAMS_SCALE, rounding=ROUND_HALF_UP)
    raise MeasurementError(f"Unrecognised weight {text!r}")


def build_search_text(*parts: str | None) -> str:
    seen: list[str] = []
    for part in parts:
        if not part:
            continue
        normalized = normalize_text(part)
        if normalized and normalized not in seen:
            seen.append(normalized)
    return " ".join(seen)
