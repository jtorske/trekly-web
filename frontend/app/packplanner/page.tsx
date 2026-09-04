"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Fraunces, Work_Sans } from "next/font/google";
import styles from "./page.module.css";
import { CompassMark, TrailMark } from "./icons";
import {
  generatePackingList,
  perPersonQty,
  type PackingCategory,
  type Season,
  type Terrain,
} from "./packingList";

const display = Fraunces({
  subsets: ["latin"],
  weight: ["500", "600"],
  style: ["normal", "italic"],
  variable: "--font-display",
});

const body = Work_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
});

const CALCULATE_DELAY_MS = 550;
const CATEGORY_ACCENTS = ["rust", "slate", "olive"] as const;

function ozToLbs(oz: number) {
  return Math.round((oz / 16) * 10) / 10;
}

interface TripValues {
  nights: number;
  location: string;
  season: Season;
  terrain: Terrain;
  groupSize: number;
  shareGear: boolean;
}

function Stepper({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className={styles.stepper}>
      <button
        type="button"
        className={styles.stepperButton}
        aria-label={`Decrease ${label}`}
        onClick={() => onChange(Math.max(min, value - 1))}
      >
        −
      </button>
      <input
        className={styles.stepperInput}
        type="number"
        min={min}
        max={max}
        value={value}
        aria-label={label}
        onChange={(event) =>
          onChange(Math.min(max, Math.max(min, Number(event.target.value) || min)))
        }
      />
      <button
        type="button"
        className={styles.stepperButton}
        aria-label={`Increase ${label}`}
        onClick={() => onChange(Math.min(max, value + 1))}
      >
        +
      </button>
    </div>
  );
}

function TripForm({
  initialNights,
  initialLocation,
  isLoading,
  onSubmit,
}: {
  initialNights: number;
  initialLocation: string;
  isLoading: boolean;
  onSubmit: (values: TripValues) => void;
}) {
  const [nights, setNights] = useState(initialNights);
  const [location, setLocation] = useState(initialLocation);
  const [season, setSeason] = useState<Season>("summer");
  const [terrain, setTerrain] = useState<Terrain>("moderate");
  const [groupSize, setGroupSize] = useState(1);
  const [shareGear, setShareGear] = useState(true);

  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({ nights, location, season, terrain, groupSize, shareGear });
      }}
    >
      <div className={styles.primaryBar}>
        <div className={styles.primaryField}>
          <label className={styles.primaryLabel} htmlFor="nights">
            Nights out
          </label>
          <Stepper label="nights" value={nights} min={1} max={30} onChange={setNights} />
        </div>

        <div className={styles.primaryDivider} aria-hidden="true" />

        <div className={`${styles.primaryField} ${styles.primaryFieldGrow}`}>
          <label className={styles.primaryLabel} htmlFor="location">
            Where to
          </label>
          <input
            id="location"
            className={styles.primaryInput}
            type="text"
            placeholder="Enchantments, WA"
            value={location}
            onChange={(event) => setLocation(event.target.value)}
          />
        </div>

        <div className={styles.primaryDivider} aria-hidden="true" />

        <div className={styles.primaryField}>
          <label className={styles.primaryLabel} htmlFor="season">
            Season
          </label>
          <select
            id="season"
            className={styles.primarySelect}
            value={season}
            onChange={(event) => setSeason(event.target.value as Season)}
          >
            <option value="spring">Spring</option>
            <option value="summer">Summer</option>
            <option value="fall">Fall</option>
            <option value="winter">Winter</option>
          </select>
        </div>

        <button className={styles.calculateButton} type="submit" disabled={isLoading}>
          {isLoading ? "Calculating…" : "Calculate"}
        </button>
      </div>

      <div className={styles.secondaryRow}>
        <div className={styles.secondaryField}>
          <label className={styles.secondaryLabel} htmlFor="terrain">
            Terrain
          </label>
          <select
            id="terrain"
            className={styles.secondarySelect}
            value={terrain}
            onChange={(event) => setTerrain(event.target.value as Terrain)}
          >
            <option value="easy">Easy</option>
            <option value="moderate">Moderate</option>
            <option value="strenuous">Strenuous</option>
          </select>
        </div>

        <div className={styles.secondaryField}>
          <label className={styles.secondaryLabel} htmlFor="groupSize">
            Group size
          </label>
          <Stepper
            label="group size"
            value={groupSize}
            min={1}
            max={20}
            onChange={setGroupSize}
          />
        </div>

        {groupSize > 1 && (
          <div className={styles.secondaryField}>
            <span className={styles.secondaryLabel}>Shared gear</span>
            <div className={styles.segmented} role="radiogroup" aria-label="Shared or individual gear">
              <button
                type="button"
                role="radio"
                aria-checked={shareGear}
                className={shareGear ? `${styles.segment} ${styles.segmentActive}` : styles.segment}
                onClick={() => setShareGear(true)}
              >
                We&apos;ll share
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={!shareGear}
                className={!shareGear ? `${styles.segment} ${styles.segmentActive}` : styles.segment}
                onClick={() => setShareGear(false)}
              >
                Carry our own
              </button>
            </div>
          </div>
        )}
      </div>
    </form>
  );
}

function EmptyState() {
  return (
    <div className={styles.placeholder}>
      <TrailMark className={styles.placeholderMark} />
      <p>Fill in your trip details to get a packing plan.</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className={styles.placeholder}>
      <CompassMark className={styles.spinner} spin />
      <p>Calculating your packing list…</p>
    </div>
  );
}

function SaveBanner() {
  return (
    <div className={styles.saveBanner}>
      <p>Sign up to save this list and track your gear.</p>
      <Link href="/signup" className={styles.saveBannerLink}>
        Sign up
      </Link>
    </div>
  );
}

function AddItemForm({
  categories,
  onAdd,
}: {
  categories: PackingCategory[];
  onAdd: (categoryId: string, name: string, qty: number) => void;
}) {
  const [name, setName] = useState("");
  const [qty, setQty] = useState(1);
  const [categoryId, setCategoryId] = useState(categories[0]?.id ?? "");

  return (
    <form
      className={styles.addItemForm}
      onSubmit={(event) => {
        event.preventDefault();
        if (!name.trim()) return;
        onAdd(categoryId, name.trim(), qty);
        setName("");
        setQty(1);
      }}
    >
      <input
        className={styles.addItemInput}
        type="text"
        placeholder="Add an item you already own…"
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <input
        className={styles.addItemQty}
        type="number"
        min={1}
        value={qty}
        onChange={(event) => setQty(Math.max(1, Number(event.target.value) || 1))}
        aria-label="Quantity"
      />
      <select
        className={styles.addItemSelect}
        value={categoryId}
        onChange={(event) => setCategoryId(event.target.value)}
        aria-label="Category"
      >
        {categories.map((category) => (
          <option key={category.id} value={category.id}>
            {category.name}
          </option>
        ))}
      </select>
      <button className={styles.addItemButton} type="submit">
        Add
      </button>
    </form>
  );
}

function PackPlannerContent() {
  const searchParams = useSearchParams();
  const initialNights = Number(searchParams.get("nights")) || 3;
  const initialLocation = searchParams.get("location") ?? "";

  const [isLoading, setIsLoading] = useState(false);
  const [categories, setCategories] = useState<PackingCategory[] | null>(null);
  const [trip, setTrip] = useState<TripValues | null>(null);
  const [view, setView] = useState<"combined" | "perPerson">("combined");

  const { combinedLbs, perPersonLbs } = useMemo(() => {
    if (!categories || !trip) return { combinedLbs: 0, perPersonLbs: 0 };
    let totalOz = 0;
    let perPersonOz = 0;
    for (const category of categories) {
      for (const item of category.items) {
        totalOz += item.qty * item.weightOz;
        perPersonOz += item.shared
          ? (item.qty * item.weightOz) / trip.groupSize
          : (perPersonQty(item, trip.groupSize) ?? 0) * item.weightOz;
      }
    }
    return { combinedLbs: ozToLbs(totalOz), perPersonLbs: ozToLbs(perPersonOz) };
  }, [categories, trip]);

  const handleSubmit = (values: TripValues) => {
    setIsLoading(true);
    setCategories(null);
    setTrip(values);
    window.setTimeout(() => {
      setCategories(generatePackingList(values));
      setIsLoading(false);
    }, CALCULATE_DELAY_MS);
  };

  const toggleItem = (categoryId: string, itemId: string) => {
    setCategories(
      (current) =>
        current?.map((category) =>
          category.id === categoryId
            ? {
                ...category,
                items: category.items.map((item) =>
                  item.id === itemId ? { ...item, checked: !item.checked } : item,
                ),
              }
            : category,
        ) ?? null,
    );
  };

  const removeItem = (categoryId: string, itemId: string) => {
    setCategories(
      (current) =>
        current?.map((category) =>
          category.id === categoryId
            ? { ...category, items: category.items.filter((item) => item.id !== itemId) }
            : category,
        ) ?? null,
    );
  };

  const addItem = (categoryId: string, name: string, qty: number) => {
    setCategories(
      (current) =>
        current?.map((category) =>
          category.id === categoryId
            ? {
                ...category,
                items: [
                  ...category.items,
                  {
                    id: `${categoryId}-custom-${Date.now()}`,
                    name,
                    qty,
                    weightOz: 0,
                    checked: false,
                    shared: false,
                  },
                ],
              }
            : category,
        ) ?? null,
    );
  };

  const showPerPerson = view === "perPerson" && (trip?.groupSize ?? 1) > 1;

  return (
    <main className={`${styles.page} ${display.variable} ${body.variable}`}>
      <div className={styles.texture} aria-hidden="true" />

      <div className={styles.intro}>
        <CompassMark className={styles.introCompass} />
        <h1 className={styles.title}>Pack planner</h1>
        <p className={styles.subtitle}>
          Tell us about your trip and get a categorized packing list to check
          off as you go.
        </p>
      </div>

      <TripForm
        initialNights={initialNights}
        initialLocation={initialLocation}
        isLoading={isLoading}
        onSubmit={handleSubmit}
      />

      <div className={styles.results}>
        {isLoading && <LoadingState />}
        {!isLoading && !categories && <EmptyState />}
        {!isLoading && categories && trip && (
          <>
            <SaveBanner />

            <div className={styles.resultsHeader}>
              <h2 className={styles.resultsTitle}>Your packing list</h2>

              <div className={styles.resultsControls}>
                {trip.groupSize > 1 && (
                  <div className={styles.segmented} role="radiogroup" aria-label="List view">
                    <button
                      type="button"
                      role="radio"
                      aria-checked={view === "combined"}
                      className={
                        view === "combined"
                          ? `${styles.segment} ${styles.segmentActive}`
                          : styles.segment
                      }
                      onClick={() => setView("combined")}
                    >
                      Whole group
                    </button>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={view === "perPerson"}
                      className={
                        view === "perPerson"
                          ? `${styles.segment} ${styles.segmentActive}`
                          : styles.segment
                      }
                      onClick={() => setView("perPerson")}
                    >
                      Per person
                    </button>
                  </div>
                )}
                <span className={styles.totalWeight}>
                  {showPerPerson ? "Per person" : "Total"}: {showPerPerson ? perPersonLbs : combinedLbs} lb
                </span>
              </div>
            </div>

            <div className={styles.categoryGrid}>
              {categories.map((category, index) => (
                <section
                  className={styles.category}
                  data-accent={CATEGORY_ACCENTS[index % CATEGORY_ACCENTS.length]}
                  key={category.id}
                >
                  <h3 className={styles.categoryTitle}>{category.name}</h3>
                  <ul className={styles.itemList}>
                    {category.items.map((item) => {
                      const displayQty = showPerPerson
                        ? item.shared
                          ? item.qty
                          : perPersonQty(item, trip.groupSize) ?? item.qty
                        : item.qty;
                      const displayWeight = showPerPerson
                        ? item.shared
                          ? item.weightOz * item.qty
                          : displayQty * item.weightOz
                        : item.weightOz * item.qty;

                      return (
                        <li className={styles.item} key={item.id}>
                          <label className={styles.itemLabel}>
                            <input
                              type="checkbox"
                              checked={item.checked}
                              onChange={() => toggleItem(category.id, item.id)}
                            />
                            <span
                              className={
                                item.checked
                                  ? `${styles.itemName} ${styles.itemChecked}`
                                  : styles.itemName
                              }
                            >
                              {item.name}
                            </span>
                          </label>
                          <div className={styles.itemMeta}>
                            {showPerPerson && item.shared && (
                              <span className={styles.sharedTag}>shared</span>
                            )}
                            <span className={styles.itemQty}>×{displayQty}</span>
                            {displayWeight > 0 && (
                              <span className={styles.itemWeight}>
                                {Math.round(displayWeight * 10) / 10} oz
                              </span>
                            )}
                            <button
                              type="button"
                              className={styles.itemRemove}
                              aria-label={`Remove ${item.name}`}
                              onClick={() => removeItem(category.id, item.id)}
                            >
                              ×
                            </button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
            </div>

            <AddItemForm categories={categories} onAdd={addItem} />
          </>
        )}
      </div>
    </main>
  );
}

export default function PackPlannerPage() {
  return (
    <Suspense fallback={<main className={`${styles.page} ${display.variable} ${body.variable}`} />}>
      <PackPlannerContent />
    </Suspense>
  );
}
