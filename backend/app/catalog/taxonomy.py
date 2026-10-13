"""Backpacking gear taxonomy.

Top-level categories are the zones of the Gear page flat lay; subcategories
are what catalogue products are filed under. Slugs are stable identifiers —
rename `name` freely, but changing a slug is a data migration.

`sync_taxonomy` (app/catalog/pipeline.py) upserts this tree idempotently.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Subcategory:
    slug: str
    name: str
    icon_key: str


@dataclass(frozen=True)
class TopCategory:
    slug: str
    name: str
    icon_key: str
    description: str
    subcategories: tuple[Subcategory, ...] = field(default_factory=tuple)


TAXONOMY: tuple[TopCategory, ...] = (
    TopCategory(
        "backpack",
        "Backpack",
        "backpack",
        "Packs and the gear that keeps them dry.",
        (
            Subcategory("backpacks", "Backpacks", "backpack"),
            Subcategory("pack-accessories", "Pack covers & liners", "backpack"),
        ),
    ),
    TopCategory(
        "shelter",
        "Shelter",
        "tent",
        "Tents, tarps and what goes under or around them.",
        (
            Subcategory("tents", "Tents", "tent"),
            Subcategory("tarps", "Tarps", "tarp"),
            Subcategory("footprints", "Footprints", "tent"),
            Subcategory("bivy-sacks", "Bivy sacks", "sleepingBag"),
            Subcategory("stakes-guylines", "Stakes & guylines", "stake"),
        ),
    ),
    TopCategory(
        "sleep",
        "Sleep system",
        "sleepingBag",
        "Bags, quilts, pads and pillows.",
        (
            Subcategory("sleeping-bags", "Sleeping bags", "sleepingBag"),
            Subcategory("quilts", "Quilts", "sleepingBag"),
            Subcategory("sleeping-pads", "Sleeping pads", "sleepingPad"),
            Subcategory("pillows", "Pillows", "pillow"),
            Subcategory("sleep-liners", "Liners", "sleepingBag"),
        ),
    ),
    TopCategory(
        "clothing",
        "Clothing",
        "insulation",
        "Layers for rain, wind and cold.",
        (
            Subcategory("rainwear", "Rainwear", "rainJacket"),
            Subcategory("insulation", "Insulation", "insulation"),
            Subcategory("fleece-midlayers", "Fleece & midlayers", "insulation"),
            Subcategory("base-layers", "Base layers", "insulation"),
            Subcategory("wind-layers", "Wind layers", "rainJacket"),
            Subcategory("headwear-gloves", "Headwear & gloves", "insulation"),
        ),
    ),
    TopCategory(
        "cooking",
        "Cooking",
        "pot",
        "Stoves, pots and everything for camp meals.",
        (
            Subcategory("stoves", "Stoves", "stove"),
            Subcategory("cookware", "Cookware", "pot"),
            Subcategory("fuel-accessories", "Fuel & accessories", "stove"),
            Subcategory("utensils", "Utensils & mugs", "pot"),
            Subcategory("food-storage", "Food storage", "canister"),
        ),
    ),
    TopCategory(
        "hydration",
        "Hydration",
        "bottle",
        "Water treatment and carrying.",
        (
            Subcategory("water-treatment", "Water treatment", "filter"),
            Subcategory("bottles-reservoirs", "Bottles & reservoirs", "bottle"),
        ),
    ),
    TopCategory(
        "footwear",
        "Footwear",
        "boot",
        "Boots, trail shoes, gaiters and camp shoes.",
        (
            Subcategory("hiking-boots", "Hiking boots", "boot"),
            Subcategory("trail-runners", "Trail runners", "boot"),
            Subcategory("gaiters", "Gaiters", "boot"),
            Subcategory("camp-shoes", "Camp shoes", "boot"),
        ),
    ),
    TopCategory(
        "navigation",
        "Navigation",
        "compass",
        "GPS units, satellite communicators, compasses and watches.",
        (
            Subcategory("gps-satellite", "GPS & satellite communicators", "gps"),
            Subcategory("compasses", "Compasses", "compass"),
            Subcategory("watches", "Watches", "watch"),
        ),
    ),
    TopCategory(
        "safety",
        "Safety",
        "firstAid",
        "First aid, emergency and wildlife safety gear.",
        (
            Subcategory("first-aid", "First aid", "firstAid"),
            Subcategory("emergency", "Emergency gear", "firstAid"),
            Subcategory("bear-safety", "Bear safety", "canister"),
        ),
    ),
    TopCategory(
        "accessories",
        "Accessories",
        "headlamp",
        "Lighting, poles, storage, repair and everything else.",
        (
            Subcategory("lighting", "Lighting", "headlamp"),
            Subcategory("trekking-poles", "Trekking poles", "poles"),
            Subcategory("storage", "Stuff sacks & dry bags", "generic"),
            Subcategory("repair", "Repair kits", "generic"),
            Subcategory("power", "Power banks", "generic"),
            Subcategory("misc", "Miscellaneous", "generic"),
        ),
    ),
)

TOP_LEVEL_SLUGS = tuple(top.slug for top in TAXONOMY)
SUBCATEGORY_TO_TOP = {sub.slug: top.slug for top in TAXONOMY for sub in top.subcategories}
ALL_SLUGS = frozenset(TOP_LEVEL_SLUGS) | frozenset(SUBCATEGORY_TO_TOP)
