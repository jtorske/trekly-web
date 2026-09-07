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
  /** Per-unit weight in pounds. Total = weightLb * qty, computed at render time. */
  weightLb: number;
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
  /** Optional summary line shown under the category title (e.g. trip-total calories). */
  summary?: string;
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
  weightLb: number,
  shared = false,
  reason?: string,
): PackingItem => {
  itemCounter += 1;
  return {
    id: `${slugify(name)}-${itemCounter}`,
    name,
    qty: Math.max(1, Math.round(qty)),
    weightLb,
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
  const { nights, terrain, groupSize, shareGear } = input;
  const rugged = terrain === "difficult" || terrain === "extreme";
  const group = Math.max(1, groupSize);
  const pooled = group > 1 && shareGear;

  const categories: Array<{ name: string; items: PackingItem[] }> = [
    {
      name: "Shelter",
      items: pooled
        ? [
            makeItem("Tent", Math.max(1, Math.ceil(group / 2)), 5, true),
            makeItem("Tent footprint", 1, 0.375, true),
            makeItem("Guy lines & stakes", 1, 0.25, true),
          ]
        : [
            makeItem("Tent", group, 5),
            makeItem("Tent footprint", group, 0.375),
            makeItem("Guy lines & stakes", group, 0.25),
          ],
    },
    {
      name: "Sleep",
      // Sleeping bag & pad are added by the caller from generatePackingList()
      // in gearRecommendation.ts, which picks a temperature-appropriate variant.
      items: [makeItem("Pillow (or stuff sack)", group, 0.1875)],
    },
    {
      name: "Kitchen",
      items: pooled
        ? [
            makeItem("Backpacking stove", Math.max(1, Math.ceil(group / 4)), 0.1875, true),
            makeItem(
              "Fuel canister",
              Math.max(1, Math.ceil(((nights + 1) * group) / 6)),
              0.5,
              true,
            ),
            makeItem("Cookpot", Math.max(1, Math.ceil(group / 4)), 0.5, true),
            makeItem("Spork / utensil", group, 0.0625),
            makeItem("Water filter", 1, 0.1875, true),
            makeItem("Water bottles / bladder", group * 2, 0.25),
          ]
        : [
            makeItem("Backpacking stove", group, 0.1875),
            makeItem("Fuel canister", Math.max(1, Math.ceil(((nights + 1) * group) / 3)), 0.5),
            makeItem("Cookpot", group, 0.5),
            makeItem("Spork / utensil", group, 0.0625),
            makeItem("Water filter", group, 0.1875),
            makeItem("Water bottles / bladder", group * 2, 0.25),
          ],
    },
    {
      name: "Clothing",
      // Base layer, insulated jacket, footwear & gloves are added by the
      // caller from generatePackingList() in gearRecommendation.ts, which
      // picks a temperature-appropriate variant for each.
      items: [
        makeItem("Rain shell", group, 0.75),
        makeItem("Hiking pants / shorts", group, 0.5),
        makeItem("Wool socks", group * Math.max(2, nights), 0.125),
        ...(rugged ? [makeItem("Trekking poles", group, 1)] : []),
      ],
    },
    {
      name: "Tools & extras",
      items: [
        makeItem("Backpack", group, 4),
        ...(pooled
          ? [makeItem("Multi-tool / knife", Math.max(1, Math.ceil(group / 2)), 0.1875, true)]
          : [makeItem("Multi-tool / knife", group, 0.1875)]),
        makeItem("Emergency whistle", group, 0.0625),
      ],
    },
  ];

  return categories.map((category) => ({
    id: slugify(category.name),
    name: category.name,
    items: category.items,
  }));
}
