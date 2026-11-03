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
        "Lighting, poles, storage, camp chairs and everything else.",
        (
            Subcategory("lighting", "Lighting", "headlamp"),
            Subcategory("trekking-poles", "Trekking poles", "poles"),
            Subcategory("storage", "Stuff sacks & dry bags", "generic"),
            Subcategory("repair", "Repair kits", "generic"),
            Subcategory("power", "Power banks", "generic"),
            Subcategory("camp-furniture", "Camp chairs", "chair"),
            Subcategory("sanitation", "Trowels & sanitation", "trowel"),
            Subcategory("misc", "Miscellaneous", "generic"),
        ),
    ),
)

# Everyday words people search with that aren't in a product's name or its
# category name ("headlamp" for Lighting, "mat" for Sleeping pads). They are
# folded into each product's search text, so the existing token and typo
# matching applies to them. Include plurals: matching is by substring, so
# "headlamp" already finds "headlamps" but not the other way round.
SEARCH_SYNONYMS: dict[str, tuple[str, ...]] = {
    "backpacks": ("pack", "packs", "rucksack", "rucksacks", "backpacking pack"),
    "pack-accessories": ("rain cover", "raincover", "pack cover", "pack liner", "liner"),
    "tents": ("tent", "shelter", "shelters", "trekking pole tent"),
    "tarps": ("tarp", "shelter", "shelters", "pyramid", "mid"),
    "footprints": ("groundsheet", "ground sheet", "footprint"),
    "bivy-sacks": ("bivy", "bivvy", "bivi"),
    "stakes-guylines": ("stake", "stakes", "peg", "pegs", "tent stakes", "guyline", "guy line"),
    "sleeping-bags": ("sleeping bag", "bag", "mummy", "down bag"),
    "quilts": ("quilt", "sleeping bag", "top quilt"),
    "sleeping-pads": ("sleeping pad", "pad", "pads", "mat", "mats", "sleeping mat", "mattress", "air mattress", "foam pad"),
    "pillows": ("pillow", "camp pillow", "inflatable pillow"),
    "sleep-liners": ("liner", "sleeping bag liner"),
    "rainwear": ("rain jacket", "rain shell", "shell", "waterproof jacket", "hardshell", "raincoat"),
    "insulation": ("puffy", "puffer", "down jacket", "insulated jacket", "synthetic jacket", "hoody", "hoodie"),
    "fleece-midlayers": ("fleece", "midlayer", "mid layer", "grid fleece"),
    "base-layers": ("base layer", "baselayer", "thermal", "thermals", "merino"),
    "wind-layers": ("wind jacket", "windbreaker", "wind shirt", "windshirt"),
    "headwear-gloves": ("hat", "beanie", "toque", "gloves", "mittens", "buff"),
    "stoves": ("stove", "burner", "cook system", "canister stove", "jetboil"),
    "cookware": ("pot", "pots", "pan", "kettle", "cook set", "cookset", "cook pot"),
    "fuel-accessories": ("fuel", "gas", "canister", "isobutane"),
    "utensils": ("mug", "cup", "spoon", "spork", "cutlery", "bowl"),
    "food-storage": ("bear canister", "bear can", "bear bag", "food bag", "canister"),
    "water-treatment": ("water filter", "filter", "purifier", "water purifier", "tablets", "uv"),
    "bottles-reservoirs": ("bottle", "water bottle", "bladder", "reservoir", "hydration"),
    "hiking-boots": ("boot", "boots", "hiking boot", "hiking shoe", "hiking shoes", "hiker", "shoes"),
    "trail-runners": ("trail runner", "trail running shoe", "trail running shoes", "running shoes", "shoes", "sneakers"),
    "gaiters": ("gaiter",),
    "camp-shoes": ("sandals", "sandal", "camp shoe", "slippers"),
    "gps-satellite": ("gps", "satellite messenger", "messenger", "sos", "plb", "beacon"),
    "compasses": ("compass",),
    "watches": ("watch", "gps watch", "smartwatch"),
    "first-aid": ("first aid kit", "first aid", "medical kit", "med kit"),
    "emergency": ("emergency blanket", "space blanket", "survival", "emergency bivy"),
    "bear-safety": ("bear spray", "pepper spray", "bear deterrent"),
    "lighting": ("headlamp", "headlamps", "head lamp", "headlight", "torch", "flashlight", "lantern", "light"),
    "trekking-poles": ("trekking pole", "hiking poles", "hiking pole", "walking poles", "poles", "sticks"),
    "storage": ("dry bag", "drybag", "stuff sack", "stuffsack", "bag"),
    "repair": ("repair kit", "patch", "tape"),
    "power": ("power bank", "powerbank", "battery", "battery pack", "charger"),
    "camp-furniture": ("chair", "chairs", "camp chair", "stool", "seat"),
    "sanitation": ("trowel", "poop trowel", "toilet", "wipes"),
    "misc": (),
}

TOP_LEVEL_SLUGS = tuple(top.slug for top in TAXONOMY)
SUBCATEGORY_TO_TOP = {sub.slug: top.slug for top in TAXONOMY for sub in top.subcategories}
ALL_SLUGS = frozenset(TOP_LEVEL_SLUGS) | frozenset(SUBCATEGORY_TO_TOP)

_missing_synonyms = set(SUBCATEGORY_TO_TOP) - set(SEARCH_SYNONYMS)
assert not _missing_synonyms, f"Search synonyms missing for: {_missing_synonyms}"
