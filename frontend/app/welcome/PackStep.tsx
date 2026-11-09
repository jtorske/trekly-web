"use client";

import { useEffect, useId, useState } from "react";
import { Check, Plus } from "lucide-react";
import { type IconKey } from "@/app/gear/icons";
import GearThumb from "@/components/GearThumb";
import QuickAddGear from "@/components/history/QuickAddGear";
import ui from "@/components/ui.module.css";
import {
  BIG_THREE_CATEGORIES,
  BIG_THREE_SLOTS,
  PICKS_PER_SLOT,
  bigThreeDone,
  choose,
  nextOpenSlot,
  slotInfo,
  type BigThreeChoices,
  type BigThreeSlot,
  type SlotChoice,
} from "@/lib/bigThree";
import { listMyGear, popularProducts, searchProducts, type ProductSummary } from "@/lib/gearApi";
import { formatWeight } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import styles from "./PackStep.module.css";

export type PackChoices = BigThreeChoices<ProductSummary>;

/**
 * /welcome's "What's in your pack?": just the Big Three, one at a time, with
 * a small mat at the top that fills in as they pick. Each pick shows the six
 * most popular catalogue items, a search box and "I don't have one / not
 * sure", so every choice is one tap and moves on to the next. Afterwards,
 * "Add more gear" opens the full quick-add. The flow adds everything picked
 * when they continue (and the whole step can be skipped).
 */
export default function PackStep({
  choices,
  onChoices,
  extras,
  onToggleExtra,
}: {
  choices: PackChoices;
  onChoices: (next: PackChoices) => void;
  /** Extra products from "Add more gear", by id. */
  extras: ReadonlyMap<string, ProductSummary>;
  onToggleExtra: (product: ProductSummary) => void;
}) {
  const [units] = useUnits();
  const [slot, setSlot] = useState<BigThreeSlot | null>(() => nextOpenSlot(choices));
  const [moreOpen, setMoreOpen] = useState(extras.size > 0);
  const [owned, setOwned] = useState<Set<string>>(new Set());

  useEffect(() => {
    const controller = new AbortController();
    listMyGear(controller.signal)
      .then((gear) => setOwned(new Set(gear.items.flatMap((item) => (item.product ? [item.product.id] : [])))))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const pick = (target: BigThreeSlot, choice: SlotChoice<ProductSummary>) => {
    const next = choose(choices, target, choice);
    onChoices(next);
    // One tap moves on, unless that tap cleared the pick.
    if (next[target] !== undefined) setSlot(nextOpenSlot(next, target));
  };

  return (
    <div className={styles.pack}>
      <Mat choices={choices} current={slot} onSelect={setSlot} />

      {slot ? (
        <SlotPicker key={slot} slot={slot} choice={choices[slot]} owned={owned} units={units} onPick={(choice) => pick(slot, choice)} />
      ) : (
        <div className={styles.finished}>
          <p className={styles.finishedTitle}>
            <Check size={18} aria-hidden="true" /> Your Big Three are in.
          </p>
          <p className={ui.hint}>Tap any spot on the mat to change it. Press Done to add them to your gear.</p>
          {!moreOpen ? (
            <button type="button" className={styles.moreLink} onClick={() => setMoreOpen(true)}>
              <Plus size={16} aria-hidden="true" /> Add more gear
            </button>
          ) : (
            <section className={styles.more} aria-label="More gear">
              <h2 className={styles.moreTitle}>More gear (optional)</h2>
              <QuickAddGear owned={owned} selected={extras} onToggle={onToggleExtra} />
            </section>
          )}
        </div>
      )}
    </div>
  );
}

/** The four spots of the Big Three, filling in as they're picked; each opens its pick. */
function Mat({
  choices,
  current,
  onSelect,
}: {
  choices: PackChoices;
  current: BigThreeSlot | null;
  onSelect: (slot: BigThreeSlot) => void;
}) {
  const done = bigThreeDone(choices);
  return (
    <div className={styles.matWrap}>
      <ol className={styles.steps} aria-label="The Big Three">
        {BIG_THREE_CATEGORIES.map(({ category, title }) => {
          const slots = BIG_THREE_SLOTS.filter((info) => info.category === category);
          const answered = slots.every((info) => choices[info.slot] !== undefined);
          const here = current !== null && slotInfo(current).category === category;
          return (
            <li key={category} className={styles.stepName} data-here={here || undefined} data-done={answered || undefined}>
              {title}
            </li>
          );
        })}
      </ol>
      <ul className={styles.mat} aria-label={done ? "Your Big Three, all picked" : "Your Big Three so far"}>
        {BIG_THREE_SLOTS.map((info) => {
          const choice = choices[info.slot];
          const product = choice && choice !== "none" ? choice : null;
          const state = product ? "picked" : choice === "none" ? "none" : "empty";
          return (
            <li key={info.slot}>
              <button
                type="button"
                className={styles.spot}
                data-state={state}
                data-here={current === info.slot || undefined}
                onClick={() => onSelect(info.slot)}
                aria-label={`${info.label}: ${product ? product.name : choice === "none" ? "don't have one" : "not picked yet"}`}
              >
                <span className={styles.spotIcon}>
                  <GearThumb icon={(product?.category.icon_key as IconKey) ?? info.icon} productImage={product?.image} alt="" size="sm" />
                </span>
                <span className={styles.spotLabel}>{info.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** One pick: six popular products, search, and "I don't have one / not sure". */
function SlotPicker({
  slot,
  choice,
  owned,
  units,
  onPick,
}: {
  slot: BigThreeSlot;
  choice: SlotChoice<ProductSummary> | undefined;
  owned: ReadonlySet<string>;
  units: ReturnType<typeof useUnits>[0];
  onPick: (choice: SlotChoice<ProductSummary>) => void;
}) {
  const info = slotInfo(slot);
  const searchId = useId();
  const headingId = useId();
  const [popular, setPopular] = useState<ProductSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ query: string; items: ProductSummary[] } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    popularProducts(info.subcategories, PICKS_PER_SLOT, controller.signal)
      .then(setPopular)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [info.subcategories]);

  const trimmed = query.trim();
  useEffect(() => {
    if (trimmed.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchProducts({ q: trimmed, category: info.subcategories.join(","), limit: PICKS_PER_SLOT }, controller.signal)
        .then((page) => setResults({ query: trimmed, items: page.items }))
        .catch(() => undefined);
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed, info.subcategories]);

  const searching = trimmed.length >= 2;
  const items = searching ? (results?.query === trimmed ? results.items : null) : popular;
  const sleep = info.category === "sleep";
  const chosenId = choice && choice !== "none" ? choice.id : null;

  return (
    <section className={styles.slot} aria-labelledby={headingId}>
      <div className={styles.slotHead}>
        <h2 id={headingId} className={styles.slotTitle}>
          {sleep ? info.label : `Your ${info.label.toLowerCase()}`}
        </h2>
        {sleep && <span className={styles.slotPart}>Sleep system · {info.slot === "sleepBag" ? "1" : "2"} of 2</span>}
      </div>

      <label htmlFor={searchId}>
        <span className={ui.srOnly}>Search {info.searchNoun}</span>
        <input
          id={searchId}
          type="search"
          className={ui.input}
          placeholder={`Search ${info.searchNoun} by brand or model`}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
        />
      </label>

      {failed && !popular ? (
        <p className={ui.error}>The gear catalogue didn&apos;t load. You can skip this and add gear any time.</p>
      ) : (
        <ul className={styles.cards} aria-busy={items === null}>
          {items === null
            ? Array.from({ length: PICKS_PER_SLOT }, (_, i) => <li key={i} className={`${ui.skeleton} ${styles.cardSkeleton}`} />)
            : items.map((product) => {
                const have = owned.has(product.id);
                const on = chosenId === product.id;
                return (
                  <li key={product.id}>
                    <button
                      type="button"
                      className={styles.card}
                      aria-pressed={on}
                      data-on={on || undefined}
                      onClick={() => onPick(product)}
                    >
                      <GearThumb icon={product.category.icon_key as IconKey} productImage={product.image} alt="" size="lg" />
                      <span className={styles.cardBrand}>{product.brand.name}</span>
                      <span className={styles.cardName}>{product.name}</span>
                      <span className={styles.cardMeta}>
                        {have ? "Already in your gear" : product.weight_g != null ? formatWeight(product.weight_g, units) : product.category.name}
                      </span>
                    </button>
                  </li>
                );
              })}
          {items !== null && items.length === 0 && (
            <li className={styles.empty}>Nothing in the catalogue matches &ldquo;{trimmed}&rdquo;.</li>
          )}
        </ul>
      )}

      <button
        type="button"
        className={styles.none}
        aria-pressed={choice === "none"}
        data-on={choice === "none" || undefined}
        onClick={() => onPick("none")}
      >
        I don&apos;t have one / not sure
      </button>
    </section>
  );
}
