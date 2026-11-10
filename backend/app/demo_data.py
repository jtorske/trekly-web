"""The demo hikers: who they are and what they've done.

Made-up people with realistic Trail Journals, gear and plans, so the app
can be explored filled in. Every one is labeled "demo" (app/account_labels.py)
and shows a "Demo account" badge wherever their name appears; their
usernames start with demo_ too. Hikes are given as days before the day the
script runs, so the profiles stay current. Trails and gear are looked up
in the catalogue by name and category; any that aren't there are skipped.

`share`: the hike is posted to the Activity feed (with what it earned).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DemoHike:
    trail: str
    province: str
    days_ago: int
    note: str | None = None
    nights: int | None = None
    share: bool = False


@dataclass(frozen=True)
class DemoHiker:
    username: str
    display_name: str
    bio: str
    province: str
    # The avatar's colours: background, then the mountain.
    colours: tuple[str, str]
    hikes: tuple[DemoHike, ...]
    saved: tuple[tuple[str, str], ...] = ()
    # (trail, province, days ahead, nights, title)
    plan: tuple[str, str, int, int, str] | None = None
    # Catalogue category slugs; one product from each.
    gear: tuple[str, ...] = ()
    experience: str = "few_seasons"
    style: str = "both"
    extra: dict = field(default_factory=dict)


# The one the landing page links to ("See a demo profile").
FEATURED_DEMO = "demo_maya"

DEMO_HIKERS: tuple[DemoHiker, ...] = (
    DemoHiker(
        username="demo_maya",
        display_name="Maya Okafor",
        bio="Canmore weekends, early starts, too many larch photos. (Demo account: made up to show what Trekly looks like.)",
        province="AB",
        colours=("#283618", "#dda15e"),
        hikes=(
            DemoHike("Ha Ling Peak", "AB", 150, "First scramble of the year. Windy on top but the view of Canmore is worth it."),
            DemoHike("Grassi Lakes", "AB", 140, "Easy evening loop. Climbers all over the walls above the lakes."),
            DemoHike("Rawson Lake", "AB", 128, "Snow still on the upper trail in June. Lake was half thawed."),
            DemoHike("Chester Lake", "AB", 115),
            DemoHike("Ptarmigan Cirque", "AB", 104, "Short and steep. Saw three ptarmigan right on cue."),
            DemoHike("Wilcox Pass", "AB", 92, "Bighorn sheep at the pass and the Athabasca Glacier the whole way up."),
            DemoHike("Skoki Valley Trail", "AB", 80, "Two nights at Merlin Meadows. Deception Pass in the rain, then sun.", nights=2),
            DemoHike("Parker Ridge", "AB", 66),
            DemoHike("Sentinel Pass via Larch Valley", "AB", 54, "Peak larch. Started at 6 to beat the shuttle crowds.", share=True),
            DemoHike("Tent Ridge Horseshoe", "AB", 40, "Exposed in a couple of spots. Loved the ridge walk.", share=True),
            DemoHike("Burstall Pass", "AB", 19, "First snow up high. Microspikes earned their place in the pack.", share=True),
            DemoHike("Prairie Mountain", "AB", 4, "Shoulder-season leg burner. Clear and cold, chinook arch to the east.", share=True),
        ),
        saved=(("Crypt Lake", "AB"), ("Skyline Trail", "AB"), ("Berg Lake Trail", "BC")),
        plan=("Tonquin Valley", "AB", 230, 3, "Tonquin Valley, three nights"),
        gear=("backpacks", "tents", "sleeping-bags", "sleeping-pads", "stoves", "lighting", "trekking-poles",
              "water-treatment", "rainwear"),
        experience="seasoned",
    ),
    DemoHiker(
        username="demo_luc",
        display_name="Luc Tremblay",
        bio="Randonnée au Québec, café au sommet. Charlevoix is home. (Demo account: made up to show what Trekly looks like.)",
        province="QC",
        colours=("#1d3557", "#a8dadc"),
        hikes=(
            DemoHike("Les Graves", "QC", 160, "Seals off the point at Forillon. Easy, foggy, beautiful."),
            DemoHike("Mont Albert", "QC", 120, "Caribou on the plateau. Long day but the tundra up top is unreal."),
            DemoHike("Mont Jacques-Cartier", "QC", 118),
            DemoHike("Traversée de Charlevoix", "QC", 75, "Three nights hut to hut. Fall colours starting in the valleys.", nights=3),
            DemoHike("Mont du Lac des Cygnes", "QC", 47, "Peak colours. The whole Charlevoix crater in red and gold.", share=True),
            DemoHike("L'Acropole des Draveurs", "QC", 33, "Stairs and more stairs. The view over the Malbaie gorge pays for all of them.", share=True),
            DemoHike("Pain de Sucre", "QC", 9, "Quick one before the snow. Had the summit to myself.", share=True),
        ),
        saved=(("Sentier des Crêtes", "QC"), ("Long Range Traverse", "NL")),
        plan=("Long Range Traverse", "NL", 250, 4, "Long Range Traverse in July"),
        gear=("backpacks", "sleeping-bags", "lighting", "trekking-poles", "hiking-boots", "cookware"),
    ),
    DemoHiker(
        username="demo_priya",
        display_name="Priya Raman",
        bio="Squamish local. Trail runner on weekdays, slow backpacker on weekends. (Demo account: made up to show what Trekly looks like.)",
        province="BC",
        colours=("#3a5a40", "#e9edc9"),
        hikes=(
            DemoHike("Quarry Rock", "BC", 170, "Rainy Tuesday loop. Still busy at 7 am!"),
            DemoHike("Stawamus Chief", "BC", 150, "All three peaks. Chains and ladders on the second."),
            DemoHike("Grouse Grind", "BC", 140),
            DemoHike("Joffre Lakes", "BC", 120, "Booked the day pass a week ahead. The upper lake colour is unreal."),
            DemoHike("Garibaldi Lake", "BC", 100, nights=1, note="One night at the lake. Loons at dusk."),
            DemoHike("Panorama Ridge", "BC", 99, "From the Garibaldi camp. Best view in the Sea to Sky, no contest."),
            DemoHike("Wedgemount Lake", "BC", 82, "Brutal climb, glacier at the top. Bring poles for the way down."),
            DemoHike("Juan de Fuca Marine Trail", "BC", 60, "Four days of mud, beaches and tide tables.", nights=3, share=True),
            DemoHike("Iceline Trail", "BC", 45, "Glaciers everywhere and Takakkaw Falls on the way back.", share=True),
            DemoHike("Elfin Lakes", "BC", 24, "Bluebird day, first dusting of snow on the Gargoyles.", share=True),
            DemoHike("Wild Pacific Trail", "BC", 6, "Storm-watching weekend in Ucluelet. Waves over the rocks.", share=True),
        ),
        saved=(("West Coast Trail", "BC"), ("Berg Lake Trail", "BC"), ("Cape Scott Trail", "BC")),
        plan=("West Coast Trail", "BC", 260, 6, "West Coast Trail, finally"),
        gear=("backpacks", "tents", "quilts", "sleeping-pads", "stoves", "water-treatment", "trail-runners", "rainwear",
              "lighting"),
        experience="seasoned",
    ),
    DemoHiker(
        username="demo_sam",
        display_name="Sam Keller",
        bio="East coast hiker with a dog and a thermos. Learning the backcountry one trip at a time. (Demo account: made up to show what Trekly looks like.)",
        province="NS",
        colours=("#6d4c41", "#ffe8d6"),
        hikes=(
            DemoHike("Cape Split", "NS", 135, "Classic. The split at the end is wild at high tide."),
            DemoHike("Skyline Trail", "NS", 110, "Moose on the boardwalk and whales offshore. Same day!"),
            DemoHike("Fishing Cove Trail", "NS", 108),
            DemoHike("Fundy Circuit", "NB", 72, "First real backpacking trip. Two nights, lots of river crossings.", nights=2,
                     share=True),
            DemoHike("Green Gardens", "NL", 50, "Sea stacks and sheep. Gros Morne trip day one.", share=True),
            DemoHike("Gros Morne Mountain", "NL", 48, "Steep gully, then a big empty plateau. Very glad I went.", share=True),
            DemoHike("Snug Harbour", "NL", 12, "Cold and quiet. The tide was way out at the end.", share=True),
        ),
        saved=(("East Coast Trail", "NL"), ("Fundy Footpath", "NB")),
        plan=("Fundy Footpath", "NB", 220, 3, "Fundy Footpath, the whole thing"),
        gear=("backpacks", "tents", "sleeping-bags", "sleeping-pads", "stoves", "first-aid", "hiking-boots"),
        experience="new",
        style="day",
    ),
)
