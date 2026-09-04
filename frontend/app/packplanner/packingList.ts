export type Season = "spring" | "summer" | "fall" | "winter";
export type Terrain = "easy" | "moderate" | "strenuous";

export interface TripInputs {
  nights: number;
  location: string;
  season: Season;
  terrain: Terrain;
  groupSize: number;
}

export interface PackingItem {
  id: string;
  name: string;
  qty: number;
  weightOz: number;
  checked: boolean;
}

export interface PackingCategory {
  id: string;
  name: string;
  items: PackingItem[];
}

const slugify = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");

let itemCounter = 0;

const makeItem = (name: string, qty: number, weightOz: number): PackingItem => {
  itemCounter += 1;
  return {
    id: `${slugify(name)}-${itemCounter}`,
    name,
    qty: Math.max(1, Math.round(qty)),
    weightOz,
    checked: false,
  };
};

export function generatePackingList(input: TripInputs): PackingCategory[] {
  const { nights, season, terrain, groupSize } = input;
  const days = nights + 1;
  const isCold = season === "winter" || season === "fall";
  const isHot = season === "summer";
  const rugged = terrain === "strenuous";
  const group = Math.max(1, groupSize);

  const categories: Array<{ name: string; items: PackingItem[] }> = [
    {
      name: "Shelter",
      items: [
        makeItem("Tent", Math.max(1, Math.ceil(group / 2)), 80),
        makeItem("Tent footprint", 1, 6),
        makeItem("Guy lines & stakes", 1, 4),
      ],
    },
    {
      name: "Sleep",
      items: [
        makeItem("Sleeping bag", group, isCold ? 48 : isHot ? 24 : 32),
        makeItem("Sleeping pad", group, 16),
        makeItem("Pillow (or stuff sack)", group, 3),
      ],
    },
    {
      name: "Kitchen",
      items: [
        makeItem("Backpacking stove", Math.max(1, Math.ceil(group / 4)), 3),
        makeItem(
          "Fuel canister",
          Math.max(1, Math.ceil((days * group) / 6)),
          8,
        ),
        makeItem("Cookpot", Math.max(1, Math.ceil(group / 4)), 8),
        makeItem("Spork / utensil", group, 1),
        makeItem("Water filter", 1, 3),
        makeItem("Water bottles / bladder", group * 2, 4),
      ],
    },
    {
      name: "Food",
      items: [
        makeItem("Breakfast", days * group, 4),
        makeItem("Lunch", days * group, 5),
        makeItem("Dinner", days * group, 6),
        makeItem("Snacks", days * group * 2, 2),
      ],
    },
    {
      name: "Clothing",
      items: [
        makeItem("Moisture-wicking base layers", group * (isCold ? 2 : 1), 6),
        makeItem("Insulating layer", group, isCold ? 18 : 10),
        makeItem("Rain shell", group, 12),
        makeItem("Hiking pants / shorts", group, 8),
        makeItem("Wool socks", group * Math.max(2, nights), 2),
        ...(rugged ? [makeItem("Trekking poles", group, 16)] : []),
        makeItem(
          rugged ? "Trail boots" : "Trail runners",
          group,
          rugged ? 32 : 22,
        ),
        ...(isCold ? [makeItem("Gloves & beanie", group, 6)] : []),
        ...(isHot ? [makeItem("Sun hat", group, 3)] : []),
      ],
    },
    {
      name: "Navigation",
      items: [
        makeItem("Map", 1, 2),
        makeItem("Compass / GPS", 1, 3),
        makeItem("Headlamp", group, 3),
        makeItem("Backup batteries", group, 2),
      ],
    },
    {
      name: "First aid & safety",
      items: [
        makeItem("First aid kit", Math.max(1, Math.ceil(group / 4)), 8),
        makeItem("Emergency whistle", group, 1),
        makeItem("Multi-tool / knife", Math.max(1, Math.ceil(group / 2)), 3),
        makeItem("Sunscreen & bug spray", 1, 6),
      ],
    },
    {
      name: "Tools & extras",
      items: [
        makeItem("Backpack", group, 64),
        makeItem("Trash bag / pack liner", group, 1),
        makeItem("Repair kit / duct tape", 1, 2),
      ],
    },
  ];

  return categories.map((category) => ({
    id: slugify(category.name),
    name: category.name,
    items: category.items,
  }));
}
