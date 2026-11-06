"use client";

import { useEffect, useId, useState } from "react";
import { type IconKey } from "@/app/gear/icons";
import GearThumb from "@/components/GearThumb";
import ui from "@/components/ui.module.css";
import { listCategories, popularProducts, searchProducts, type GearCategory, type ProductSummary } from "@/lib/gearApi";
import { formatWeight } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import styles from "./QuickAddGear.module.css";

const PER_TAB = 12;

/**
 * "What's in your pack?": the most popular catalogue products by category,
 * as tappable cards, with search. The parent owns the selection and adds
 * it (onboarding's /welcome step and the gear page's "Quick-add gear" both
 * use this). Products already in the hiker's gear show as such.
 */
export default function QuickAddGear({
  owned,
  selected,
  onToggle,
}: {
  /** Product ids already in their gear. */
  owned: ReadonlySet<string>;
  /** Selected products, by id. */
  selected: ReadonlyMap<string, ProductSummary>;
  onToggle: (product: ProductSummary) => void;
}) {
  const searchId = useId();
  const [units] = useUnits();
  const [categories, setCategories] = useState<GearCategory[] | null>(null);
  const [tab, setTab] = useState<string | null>(null);
  const [byTab, setByTab] = useState<Record<string, ProductSummary[]>>({});
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ query: string; items: ProductSummary[] } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    listCategories(controller.signal)
      .then((list) => {
        const withProducts = list.filter((category) => category.subcategories.length > 0);
        setCategories(withProducts);
        setTab((current) => current ?? withProducts[0]?.slug ?? null);
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, []);

  const active = categories?.find((category) => category.slug === tab) ?? null;
  const loaded = tab ? byTab[tab] : undefined;
  useEffect(() => {
    if (!active || loaded) return;
    const controller = new AbortController();
    popularProducts(active.subcategories.map((sub) => sub.slug), PER_TAB, controller.signal)
      .then((items) => setByTab((current) => ({ ...current, [active.slug]: items })))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [active, loaded]);

  const trimmed = query.trim();
  useEffect(() => {
    if (trimmed.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchProducts({ q: trimmed, limit: PER_TAB }, controller.signal)
        .then((page) => setResults({ query: trimmed, items: page.items }))
        .catch(() => undefined);
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed]);

  const searching = trimmed.length >= 2;
  const items = searching ? (results?.query === trimmed ? results.items : null) : (loaded ?? null);

  if (failed && !categories) {
    return <p className={ui.error}>The gear catalogue didn&apos;t load. Check your connection and try again.</p>;
  }

  return (
    <div className={styles.quickAdd}>
      <label htmlFor={searchId}>
        <span className={ui.srOnly}>Search the gear catalogue</span>
        <input
          id={searchId}
          type="search"
          className={ui.input}
          placeholder="Search brands and products"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
        />
      </label>

      {!searching && (
        <div className={styles.tabs} role="tablist" aria-label="Categories">
          {(categories ?? []).map((category) => (
            <button
              key={category.slug}
              type="button"
              role="tab"
              aria-selected={category.slug === tab}
              className={styles.tab}
              onClick={() => setTab(category.slug)}
            >
              {category.name}
            </button>
          ))}
        </div>
      )}

      <div role={searching ? undefined : "tabpanel"} aria-label={searching ? "Search results" : active?.name} aria-busy={items === null}>
        {items === null ? (
          <div className={styles.grid}>
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className={`${ui.skeleton} ${styles.cardSkeleton}`} />
            ))}
          </div>
        ) : items.length === 0 ? (
          <p className={styles.empty}>{searching ? <>Nothing in the catalogue matches &ldquo;{trimmed}&rdquo;.</> : "No products here yet."}</p>
        ) : (
          <ul className={styles.grid}>
            {items.map((product) => {
              const have = owned.has(product.id);
              const on = have || selected.has(product.id);
              return (
                <li key={product.id}>
                  <button
                    type="button"
                    className={`${styles.card} ${on ? styles.on : ""}`}
                    aria-pressed={on}
                    disabled={have}
                    onClick={() => onToggle(product)}
                  >
                    <span className={styles.thumb}>
                      <GearThumb icon={product.category.icon_key as IconKey} productImage={product.image} alt="" size="md" />
                      <span className={styles.tick} aria-hidden="true">
                        <svg viewBox="0 0 24 24">
                          <path d="m5 12.5 4.2 4.2L19 7" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </span>
                    </span>
                    <span className={styles.brand}>{product.brand.name}</span>
                    <span className={styles.name}>{product.name}</span>
                    <span className={styles.meta}>
                      {have ? "In your gear" : product.weight_g != null ? formatWeight(product.weight_g, units) : product.category.name}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
