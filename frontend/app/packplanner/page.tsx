"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import styles from "./page.module.css";
import {
  generatePackingList,
  type PackingCategory,
  type Season,
  type Terrain,
} from "./packingList";

const CALCULATE_DELAY_MS = 550;

function ozToLbs(oz: number) {
  return Math.round((oz / 16) * 10) / 10;
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
  onSubmit: (values: {
    nights: number;
    location: string;
    season: Season;
    terrain: Terrain;
    groupSize: number;
  }) => void;
}) {
  const [nights, setNights] = useState(initialNights);
  const [location, setLocation] = useState(initialLocation);
  const [season, setSeason] = useState<Season>("summer");
  const [terrain, setTerrain] = useState<Terrain>("moderate");
  const [groupSize, setGroupSize] = useState(1);

  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({ nights, location, season, terrain, groupSize });
      }}
    >
      <div className={styles.field}>
        <label className={styles.label} htmlFor="nights">
          Nights
        </label>
        <div className={styles.stepper}>
          <button
            type="button"
            className={styles.stepperButton}
            aria-label="Decrease nights"
            onClick={() => setNights((value) => Math.max(1, value - 1))}
          >
            −
          </button>
          <input
            id="nights"
            className={styles.stepperInput}
            type="number"
            min={1}
            max={30}
            value={nights}
            onChange={(event) =>
              setNights(Math.max(1, Number(event.target.value) || 1))
            }
          />
          <button
            type="button"
            className={styles.stepperButton}
            aria-label="Increase nights"
            onClick={() => setNights((value) => Math.min(30, value + 1))}
          >
            +
          </button>
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="location">
          Location / region
        </label>
        <input
          id="location"
          className={styles.input}
          type="text"
          placeholder="e.g. Enchantments, WA"
          value={location}
          onChange={(event) => setLocation(event.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="season">
          Season
        </label>
        <select
          id="season"
          className={styles.input}
          value={season}
          onChange={(event) => setSeason(event.target.value as Season)}
        >
          <option value="spring">Spring</option>
          <option value="summer">Summer</option>
          <option value="fall">Fall</option>
          <option value="winter">Winter</option>
        </select>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="terrain">
          Terrain / difficulty
        </label>
        <select
          id="terrain"
          className={styles.input}
          value={terrain}
          onChange={(event) => setTerrain(event.target.value as Terrain)}
        >
          <option value="easy">Easy</option>
          <option value="moderate">Moderate</option>
          <option value="strenuous">Strenuous</option>
        </select>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="groupSize">
          Group size
        </label>
        <div className={styles.stepper}>
          <button
            type="button"
            className={styles.stepperButton}
            aria-label="Decrease group size"
            onClick={() => setGroupSize((value) => Math.max(1, value - 1))}
          >
            −
          </button>
          <input
            id="groupSize"
            className={styles.stepperInput}
            type="number"
            min={1}
            max={20}
            value={groupSize}
            onChange={(event) =>
              setGroupSize(Math.max(1, Number(event.target.value) || 1))
            }
          />
          <button
            type="button"
            className={styles.stepperButton}
            aria-label="Increase group size"
            onClick={() => setGroupSize((value) => Math.min(20, value + 1))}
          >
            +
          </button>
        </div>
      </div>

      <button className={styles.calculateButton} type="submit" disabled={isLoading}>
        {isLoading ? "Calculating…" : "Calculate"}
      </button>
    </form>
  );
}

function EmptyState() {
  return (
    <div className={styles.placeholder}>
      <div className={styles.placeholderMark} aria-hidden="true" />
      <p>Fill in your trip details to get a packing plan.</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className={styles.placeholder}>
      <div className={styles.spinner} aria-hidden="true" />
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

  const totalWeightLbs = useMemo(() => {
    if (!categories) return 0;
    const totalOz = categories.reduce(
      (sum, category) =>
        sum + category.items.reduce((s, item) => s + item.qty * item.weightOz, 0),
      0,
    );
    return ozToLbs(totalOz);
  }, [categories]);

  const handleSubmit = (values: {
    nights: number;
    location: string;
    season: Season;
    terrain: Terrain;
    groupSize: number;
  }) => {
    setIsLoading(true);
    setCategories(null);
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
                  },
                ],
              }
            : category,
        ) ?? null,
    );
  };

  return (
    <main className={styles.page}>
      <div className={styles.intro}>
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
        {!isLoading && categories && (
          <>
            <SaveBanner />

            <div className={styles.resultsHeader}>
              <h2 className={styles.resultsTitle}>Your packing list</h2>
              <span className={styles.totalWeight}>
                Estimated total: {totalWeightLbs} lb
              </span>
            </div>

            <div className={styles.categoryGrid}>
              {categories.map((category) => (
                <section className={styles.category} key={category.id}>
                  <h3 className={styles.categoryTitle}>{category.name}</h3>
                  <ul className={styles.itemList}>
                    {category.items.map((item) => (
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
                          <span className={styles.itemQty}>×{item.qty}</span>
                          {item.weightOz > 0 && (
                            <span className={styles.itemWeight}>
                              {item.weightOz * item.qty} oz
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
                    ))}
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
    <Suspense fallback={<main className={styles.page} />}>
      <PackPlannerContent />
    </Suspense>
  );
}
