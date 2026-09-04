export type Season = "spring" | "summer" | "fall" | "winter";
export type Terrain = "easy" | "moderate" | "difficult" | "extreme";

export const TERRAIN_LABELS: Record<Terrain, string> = {
  easy: "Easy",
  moderate: "Moderate",
  difficult: "Difficult",
  extreme: "Extreme",
};

export interface TripInputs {
  nights: number;
  location: string;
  season: Season;
  terrain: Terrain;
  groupSize: number;
  shareGear: boolean;
}

export interface PackingItem {
  id: string;
  name: string;
  qty: number;
  weightOz: number;
  checked: boolean;
  /** Group-level item (one tent for everyone) vs. one each person carries. */
  shared: boolean;
  /** Short explanation shown under the item name, e.g. why this variant was picked. */
  reason?: string;
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

const makeItem = (
  name: string,
  qty: number,
  weightOz: number,
  shared = false,
  reason?: string,
): PackingItem => {
  itemCounter += 1;
  return {
    id: `${slugify(name)}-${itemCounter}`,
    name,
    qty: Math.max(1, Math.round(qty)),
    weightOz,
    checked: false,
    shared,
    reason,
  };
};

/** For a personal item, the amount a single person carries. */
export function perPersonQty(item: PackingItem, groupSize: number) {
  if (item.shared) return null;
  return Math.max(1, Math.round(item.qty / Math.max(1, groupSize)));
}

export function generatePackingList(input: TripInputs): PackingCategory[] {
  const { nights, season, terrain, groupSize, shareGear } = input;
  const days = nights + 1;
  const isHot = season === "summer";
  const rugged = terrain === "difficult" || terrain === "extreme";
  const group = Math.max(1, groupSize);
  const pooled = group > 1 && shareGear;

  const categories: Array<{ name: string; items: PackingItem[] }> = [
    {
      name: "Shelter",
      items: pooled
        ? [
            makeItem("Tent", Math.max(1, Math.ceil(group / 2)), 80, true),
            makeItem("Tent footprint", 1, 6, true),
            makeItem("Guy lines & stakes", 1, 4, true),
          ]
        : [
            makeItem("Tent", group, 80),
            makeItem("Tent footprint", group, 6),
            makeItem("Guy lines & stakes", group, 4),
          ],
    },
    {
      name: "Sleep",
      // Sleeping bag & pad are added by the caller from generatePackingList()
      // in gearRecommendation.ts, which picks a temperature-appropriate variant.
      items: [makeItem("Pillow (or stuff sack)", group, 3)],
    },
    {
      name: "Kitchen",
      items: pooled
        ? [
            makeItem("Backpacking stove", Math.max(1, Math.ceil(group / 4)), 3, true),
            makeItem(
              "Fuel canister",
              Math.max(1, Math.ceil((days * group) / 6)),
              8,
              true,
            ),
            makeItem("Cookpot", Math.max(1, Math.ceil(group / 4)), 8, true),
            makeItem("Spork / utensil", group, 1),
            makeItem("Water filter", 1, 3, true),
            makeItem("Water bottles / bladder", group * 2, 4),
          ]
        : [
            makeItem("Backpacking stove", group, 3),
            makeItem("Fuel canister", Math.max(1, Math.ceil((days * group) / 3)), 8),
            makeItem("Cookpot", group, 8),
            makeItem("Spork / utensil", group, 1),
            makeItem("Water filter", Math.max(1, Math.ceil(group / 2)), 3, true),
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
      // Base layer, insulated jacket, footwear & gloves are added by the
      // caller from generatePackingList() in gearRecommendation.ts, which
      // picks a temperature-appropriate variant for each.
      items: [
        makeItem("Rain shell", group, 12),
        makeItem("Hiking pants / shorts", group, 8),
        makeItem("Wool socks", group * Math.max(2, nights), 2),
        ...(rugged ? [makeItem("Trekking poles", group, 16)] : []),
        ...(isHot ? [makeItem("Sun hat", group, 3)] : []),
      ],
    },
    {
      name: "Navigation",
      items: [
        makeItem("Map", 1, 2, true),
        makeItem("Compass / GPS", 1, 3, true),
        makeItem("Headlamp", group, 3),
        makeItem("Backup batteries", group, 2),
      ],
    },
    {
      name: "First aid & safety",
      items: [
        makeItem("First aid kit", Math.max(1, Math.ceil(group / 4)), 8, true),
        makeItem("Emergency whistle", group, 1),
        makeItem("Multi-tool / knife", Math.max(1, Math.ceil(group / 2)), 3, true),
        makeItem("Sunscreen & bug spray", 1, 6, true),
      ],
    },
    {
      name: "Tools & extras",
      items: [
        makeItem("Backpack", group, 64),
        makeItem("Trash bag / pack liner", group, 1),
        makeItem("Repair kit / duct tape", 1, 2, true),
      ],
    },
  ];

  return categories.map((category) => ({
    id: slugify(category.name),
    name: category.name,
    items: category.items,
  }));
}
