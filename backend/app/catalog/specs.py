"""Category-specific structured specifications.

Each subcategory declares which spec keys it accepts, their type and their
canonical unit. Catalogue records are validated against this registry, so a
sleeping pad can carry an R-value and a stove a boil time without forcing
every product into one generic shape. Weight and capacity are first-class
columns on products/variants and are not repeated here.

Canonical units: cm, m², °C, minutes, litres/minute, lumens, metres, hours.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.catalog.normalize import MeasurementError, to_decimal
from app.catalog.taxonomy import SUBCATEGORY_TO_TOP

SpecKind = Literal["number", "integer", "text", "boolean"]


@dataclass(frozen=True)
class SpecField:
    key: str
    label: str
    kind: SpecKind
    unit: str | None = None
    choices: tuple[str, ...] | None = None
    minimum: Decimal | None = None


def _n(key: str, label: str, unit: str | None = None, minimum: str | None = "0") -> SpecField:
    return SpecField(key, label, "number", unit, minimum=Decimal(minimum) if minimum else None)


def _i(key: str, label: str, unit: str | None = None) -> SpecField:
    return SpecField(key, label, "integer", unit, minimum=Decimal(0))


def _t(key: str, label: str, choices: tuple[str, ...] | None = None) -> SpecField:
    return SpecField(key, label, "text", choices=choices)


def _b(key: str, label: str) -> SpecField:
    return SpecField(key, label, "boolean")


# Allowed on every product: published text kept verbatim for provenance.
COMMON = (
    _t("published_weight", "Published weight"),
    _t("materials", "Materials"),
    _t("packed_dimensions", "Packed size"),
    _t("dimensions", "Dimensions"),
    _t("gender_fit", "Fit", ("unisex", "mens", "womens")),
    _n("packaged_weight_g", "Packaged weight", "g"),
)

SHELTER = (
    _i("capacity_persons", "Sleeps", "persons"),
    _t("seasons", "Seasons", ("3", "3+", "4")),
    _b("freestanding", "Freestanding"),
    _i("doors", "Doors"),
    _n("floor_area_m2", "Floor area", "m2"),
    _n("vestibule_area_m2", "Vestibule area", "m2"),
    _n("peak_height_cm", "Peak height", "cm"),
)

INSULATED_SLEEP = (
    _n("comfort_rating_c", "Comfort rating", "c", minimum=None),
    _n("limit_rating_c", "Lower limit", "c", minimum=None),
    _t("temperature_rating_label", "Temperature rating"),
    _t("insulation_type", "Insulation", ("down", "synthetic", "wool", "hybrid")),
    _i("fill_power", "Fill power"),
    _n("fill_weight_g", "Fill weight", "g"),
)

SPECS_BY_SUBCATEGORY: dict[str, tuple[SpecField, ...]] = {
    "backpacks": (
        _t("frame_type", "Frame", ("frameless", "internal", "external")),
        _t("torso_range", "Torso range"),
        _n("max_load_kg", "Max recommended load", "kg"),
    ),
    "pack-accessories": (),
    "tents": SHELTER,
    "tarps": (_n("area_m2", "Coverage", "m2"), _i("capacity_persons", "Sleeps", "persons")),
    "footprints": (_t("fits", "Fits"),),
    "bivy-sacks": (_b("waterproof", "Waterproof"),),
    "stakes-guylines": (_i("pieces", "Pieces"), _n("length_cm", "Length", "cm")),
    "sleeping-bags": INSULATED_SLEEP,
    "quilts": INSULATED_SLEEP,
    "sleeping-pads": (
        _n("r_value", "R-value"),
        _t("pad_type", "Type", ("air", "foam", "self_inflating")),
        _n("thickness_cm", "Thickness", "cm"),
        _n("length_cm", "Length", "cm"),
        _n("width_cm", "Width", "cm"),
    ),
    "pillows": (_t("pad_type", "Type", ("air", "foam", "compressible", "hybrid")),),
    "sleep-liners": (_t("insulation_type", "Material"),),
    "rainwear": (
        _n("waterproof_rating_mm", "Waterproof rating", "mm"),
        _t("membrane", "Membrane"),
    ),
    "insulation": (
        _t("insulation_type", "Insulation", ("down", "synthetic", "fleece", "wool", "hybrid")),
        _i("fill_power", "Fill power"),
        _n("fill_weight_g", "Fill weight", "g"),
        _b("hooded", "Hood"),
    ),
    "fleece-midlayers": (_b("hooded", "Hood"),),
    "base-layers": (_n("fabric_weight_gsm", "Fabric weight", "gsm"),),
    "wind-layers": (_b("hooded", "Hood"),),
    "headwear-gloves": (),
    "stoves": (
        _t("fuel_type", "Fuel", ("canister", "liquid", "multi_fuel", "alcohol", "solid", "wood")),
        _n("boil_time_min", "Boil time (1 L)", "min"),
        _n("burn_time_min", "Burn time per canister", "min"),
        _b("piezo_ignition", "Push-button ignition"),
        _b("integrated_system", "Integrated cook system"),
    ),
    "cookware": (_t("cookware_material", "Material", ("titanium", "aluminum", "stainless_steel", "silicone", "plastic")),),
    "fuel-accessories": (),
    "utensils": (),
    "food-storage": (_b("igbc_certified", "IGBC certified"),),
    "water-treatment": (
        _t("treatment_type", "Method", ("filter", "purifier", "chemical", "uv", "gravity")),
        _n("pore_size_micron", "Pore size", "micron"),
        _n("flow_rate_l_per_min", "Flow rate", "l/min"),
        _n("lifespan_l", "Rated lifespan", "l"),
    ),
    "bottles-reservoirs": (_b("insulated", "Insulated"),),
    "hiking-boots": (
        _b("waterproof", "Waterproof"),
        _n("drop_mm", "Heel-to-toe drop", "mm"),
    ),
    "trail-runners": (
        _b("waterproof", "Waterproof"),
        _n("drop_mm", "Heel-to-toe drop", "mm"),
        _n("stack_height_mm", "Stack height", "mm"),
    ),
    "gaiters": (),
    "camp-shoes": (),
    "gps-satellite": (
        _t("satellite_network", "Satellite network"),
        _b("two_way_messaging", "Two-way messaging"),
        _b("sos", "SOS"),
        _n("battery_life_hours", "Battery life", "h"),
    ),
    "compasses": (_b("declination_adjustment", "Declination adjustment"),),
    "watches": (_n("battery_life_hours", "Battery life (smartwatch mode)", "h"),),
    "first-aid": (_i("persons", "People"), _i("days", "Days")),
    "emergency": (),
    "bear-safety": (_b("igbc_certified", "IGBC certified"),),
    "lighting": (
        _i("max_lumens", "Max output", "lm"),
        _n("max_beam_distance_m", "Max beam distance", "m"),
        _t("power_source", "Power"),
        _t("water_rating", "Water rating"),
    ),
    "trekking-poles": (
        _t("pole_material", "Material", ("aluminum", "carbon")),
        _t("adjustable_length", "Length range"),
        _n("collapsed_length_cm", "Collapsed length", "cm"),
        _t("locking", "Locking"),
    ),
    "storage": (_b("waterproof", "Waterproof"),),
    "repair": (),
    "power": (_i("capacity_mah", "Capacity", "mAh"),),
    "misc": (),
}

missing = set(SUBCATEGORY_TO_TOP) - set(SPECS_BY_SUBCATEGORY)
assert not missing, f"Spec registry missing subcategories: {missing}"


def fields_for(subcategory: str) -> dict[str, SpecField]:
    return {field.key: field for field in COMMON + SPECS_BY_SUBCATEGORY.get(subcategory, ())}


def validate_specs(subcategory: str, specs: dict) -> dict:
    """Return a JSON-safe, validated copy of specs; raise ValueError on any problem.

    Unknown keys are rejected rather than stored, so typos in a feed surface
    as import errors instead of silently-ignored data.
    """
    allowed = fields_for(subcategory)
    clean: dict[str, object] = {}
    for key, raw in specs.items():
        if raw is None:
            continue  # unknown stays unknown
        field = allowed.get(key)
        if field is None:
            raise ValueError(f"Spec '{key}' isn't defined for category '{subcategory}'")
        if field.kind in ("number", "integer"):
            try:
                number = to_decimal(raw)
            except MeasurementError as error:
                raise ValueError(f"Spec '{key}': {error}") from error
            if field.kind == "integer" and number != number.to_integral_value():
                raise ValueError(f"Spec '{key}' must be a whole number")
            if field.minimum is not None and number < field.minimum:
                raise ValueError(f"Spec '{key}' must be at least {field.minimum}")
            clean[key] = int(number) if field.kind == "integer" else float(number)
        elif field.kind == "boolean":
            if not isinstance(raw, bool):
                raise ValueError(f"Spec '{key}' must be true or false")
            clean[key] = raw
        else:
            text = str(raw).strip()
            if not text:
                continue
            if field.choices and text not in field.choices:
                raise ValueError(f"Spec '{key}' must be one of {', '.join(field.choices)}")
            clean[key] = text
    return clean


def present_specs(subcategory: str, specs: dict) -> list[dict]:
    """Specs as labelled rows for the API, in registry order."""
    allowed = fields_for(subcategory)
    ordered = [key for key in allowed if key in specs and key != "published_weight"]
    return [
        {"key": key, "label": allowed[key].label, "value": specs[key], "unit": allowed[key].unit}
        for key in ordered
    ]
