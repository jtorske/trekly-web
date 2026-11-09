/**
 * /welcome's "What's in your pack?": the Big Three only (backpack, shelter
 * and sleep system), one category at a time, each pick one tap. The sleep
 * system is two small picks, a bag or quilt and a pad. Pure, so the order
 * and what gets added can be tested; the screen is app/welcome/PackStep.tsx.
 *
 * The catalogue subcategories match the "Big Three" in the milestones
 * (backend app/milestones_config.py CORE_SLOT_CATEGORIES).
 */

export type BigThreeSlot = "backpack" | "shelter" | "sleepBag" | "sleepPad";
export type BigThreeCategory = "backpack" | "shelter" | "sleep";

export interface SlotInfo {
  slot: BigThreeSlot;
  category: BigThreeCategory;
  /** The category heading. */
  title: string;
  /** This pick within its category (the sleep system has two). */
  label: string;
  /** What its search looks through ("Search sleeping bags and quilts"). */
  searchNoun: string;
  /** Catalogue subcategory slugs. */
  subcategories: string[];
  /** A gear icon key (app/gear/icons.tsx) for the empty mat tile. */
  icon: "backpack" | "tent" | "sleepingBag" | "sleepingPad";
}

export const BIG_THREE_SLOTS: SlotInfo[] = [
  { slot: "backpack", category: "backpack", title: "Backpack", label: "Backpack", searchNoun: "backpacks", subcategories: ["backpacks"], icon: "backpack" },
  {
    slot: "shelter",
    category: "shelter",
    title: "Shelter",
    label: "Tent, tarp or bivy",
    searchNoun: "tents, tarps and bivies",
    subcategories: ["tents", "tarps", "bivy-sacks"],
    icon: "tent",
  },
  {
    slot: "sleepBag",
    category: "sleep",
    title: "Sleep system",
    label: "Sleeping bag or quilt",
    searchNoun: "sleeping bags and quilts",
    subcategories: ["sleeping-bags", "quilts"],
    icon: "sleepingBag",
  },
  { slot: "sleepPad", category: "sleep", title: "Sleep system", label: "Sleeping pad", searchNoun: "sleeping pads", subcategories: ["sleeping-pads"], icon: "sleepingPad" },
];

export const BIG_THREE_CATEGORIES: { category: BigThreeCategory; title: string }[] = [
  { category: "backpack", title: "Backpack" },
  { category: "shelter", title: "Shelter" },
  { category: "sleep", title: "Sleep system" },
];

/** Popular products shown per pick. */
export const PICKS_PER_SLOT = 6;

/** A pick: a product (any shape with an id), or "none" for "I don't have one / not sure". */
export type SlotChoice<P extends { id: string }> = P | "none";
export type BigThreeChoices<P extends { id: string }> = Partial<Record<BigThreeSlot, SlotChoice<P>>>;

export const slotInfo = (slot: BigThreeSlot): SlotInfo => BIG_THREE_SLOTS.find((info) => info.slot === slot)!;

/** The first pick not answered yet, or null once all four are. */
export function nextOpenSlot<P extends { id: string }>(choices: BigThreeChoices<P>, after?: BigThreeSlot): BigThreeSlot | null {
  const order = BIG_THREE_SLOTS.map((info) => info.slot);
  const start = after ? order.indexOf(after) + 1 : 0;
  // After the one just answered, then from the top for any skipped earlier.
  for (const slot of [...order.slice(start), ...order.slice(0, start)]) {
    if (choices[slot] === undefined) return slot;
  }
  return null;
}

export function bigThreeDone<P extends { id: string }>(choices: BigThreeChoices<P>): boolean {
  return nextOpenSlot(choices) === null;
}

/** How many of the three categories are fully answered, for the step's progress line. */
export function categoriesDone<P extends { id: string }>(choices: BigThreeChoices<P>): number {
  return BIG_THREE_CATEGORIES.filter(({ category }) =>
    BIG_THREE_SLOTS.filter((info) => info.category === category).every((info) => choices[info.slot] !== undefined),
  ).length;
}

/** Set one pick; tapping the chosen product again clears it. */
export function choose<P extends { id: string }>(choices: BigThreeChoices<P>, slot: BigThreeSlot, choice: SlotChoice<P>): BigThreeChoices<P> {
  const current = choices[slot];
  const same = current === choice || (current !== undefined && current !== "none" && choice !== "none" && current.id === choice.id);
  const next = { ...choices };
  if (same) delete next[slot];
  else next[slot] = choice;
  return next;
}

/** The products to add to their gear: the Big Three picks, then any extras, once each. */
export function productsToAdd<P extends { id: string }>(choices: BigThreeChoices<P>, extras: Iterable<P> = []): P[] {
  const out = new Map<string, P>();
  for (const info of BIG_THREE_SLOTS) {
    const choice = choices[info.slot];
    if (choice && choice !== "none") out.set(choice.id, choice);
  }
  for (const product of extras) if (!out.has(product.id)) out.set(product.id, product);
  return [...out.values()];
}
