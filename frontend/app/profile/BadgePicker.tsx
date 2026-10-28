"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, GripVertical, Search, X } from "lucide-react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import {
  MAX_FEATURED,
  badgeKey,
  badgeName,
  earnedBadgeGroups,
  moveBadge,
  toggleBadge,
  type FeaturedBadge,
  type FeaturedBadges,
} from "@/lib/featuredBadges";
import { saveFeaturedBadges } from "@/lib/featuredBadgesApi";
import type { HikeLog } from "@/lib/hikeLogsApi";
import { BadgeArt } from "./ProfileShell";
import styles from "./BadgePicker.module.css";

/**
 * Choose up to three earned badges to feature, and their order (drag, or
 * the up/down buttons). Opens on what the profile shows now. Saving none
 * goes back to the most recent badges. The API re-checks every choice.
 */
export default function BadgePicker({
  logs,
  current,
  onClose,
  onSaved,
}: {
  logs: HikeLog[];
  current: FeaturedBadge[];
  onClose: () => void;
  onSaved: (featured: FeaturedBadges) => void;
}) {
  const [selected, setSelected] = useState(current);
  const [query, setQuery] = useState("");
  const [dragging, setDragging] = useState<number | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const groups = earnedBadgeGroups(logs, query);
  const chosen = new Set(selected.map(badgeKey));
  const full = selected.length >= MAX_FEATURED;

  const toggle = (badge: FeaturedBadge) => {
    const isChosen = chosen.has(badgeKey(badge));
    setBlocked(!isChosen && full);
    setSelected((now) => toggleBadge(now, badge));
  };

  const move = (from: number, to: number) => setSelected((now) => moveBadge(now, from, to));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      onSaved(await saveFeaturedBadges(selected));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Your badges didn't save. Try again.");
      setSaving(false);
    }
  };

  return (
    <Dialog
      title="Featured badges"
      subtitle={`Choose up to ${MAX_FEATURED} badges you've earned to show on your profile.`}
      onClose={onClose}
      busy={saving}
      sheet
      footer={
        <>
          <button type="button" className={ui.ghost} onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="button" className={ui.primary} onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <div className={styles.picker}>
        <section aria-labelledby="featured-order">
          <div className={styles.orderHead}>
            <h3 id="featured-order" className={styles.heading}>
              Your featured badges
            </h3>
            <p className={styles.count} aria-live="polite">
              {selected.length} of {MAX_FEATURED} selected
            </p>
          </div>
          <ol className={styles.order}>
            {selected.map((badge, index) => {
              const name = badgeName(badge);
              return (
                <li
                  key={badgeKey(badge)}
                  className={`${styles.orderItem} ${dragging === index ? styles.dragging : ""}`}
                  draggable
                  onDragStart={(event) => {
                    setDragging(index);
                    event.dataTransfer.effectAllowed = "move";
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    if (dragging !== null && dragging !== index) {
                      move(dragging, index);
                      setDragging(index);
                    }
                  }}
                  onDragEnd={() => setDragging(null)}
                  onDrop={(event) => event.preventDefault()}
                >
                  <GripVertical className={styles.grip} size={18} aria-hidden="true" />
                  <span className={styles.position} aria-hidden="true">
                    {index + 1}
                  </span>
                  <BadgeArt badge={badge} className={styles.orderArt} />
                  <span className={styles.orderName}>{name}</span>
                  <span className={styles.orderButtons}>
                    <button
                      type="button"
                      className={styles.iconButton}
                      onClick={() => move(index, index - 1)}
                      disabled={index === 0}
                      aria-label={`Move ${name} up`}
                    >
                      <ChevronUp size={18} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className={styles.iconButton}
                      onClick={() => move(index, index + 1)}
                      disabled={index === selected.length - 1}
                      aria-label={`Move ${name} down`}
                    >
                      <ChevronDown size={18} aria-hidden="true" />
                    </button>
                    <button type="button" className={styles.iconButton} onClick={() => toggle(badge)} aria-label={`Remove ${name}`}>
                      <X size={18} aria-hidden="true" />
                    </button>
                  </span>
                </li>
              );
            })}
            {Array.from({ length: MAX_FEATURED - selected.length }, (_, index) => (
              <li key={`empty-${index}`} className={styles.orderEmpty} aria-hidden="true">
                Empty slot
              </li>
            ))}
          </ol>
          <p className={styles.hint} role={blocked ? "alert" : undefined}>
            {blocked
              ? `You can feature ${MAX_FEATURED}. Remove one to add another.`
              : selected.length === 0
                ? "Feature none to show your most recent badges."
                : "Drag to reorder, or use the arrows."}
          </p>
        </section>

        <section aria-labelledby="earned-badges">
          <h3 id="earned-badges" className={styles.heading}>
            Badges you&apos;ve earned
          </h3>
          <label className={styles.search}>
            <Search size={16} aria-hidden="true" />
            <span className={ui.srOnly}>Search your badges</span>
            <input
              className={ui.input}
              type="search"
              placeholder="Search by trail or park"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              data-autofocus
            />
          </label>
          {groups.length === 0 && (
            <p className={styles.none}>{query ? "No badges match that search." : "You haven't earned any badges yet."}</p>
          )}
          {groups.map((group) => (
            <div key={group.title} className={styles.group}>
              <h4 className={styles.groupTitle}>{group.title}</h4>
              <ul className={styles.grid}>
                {group.badges.map((badge) => {
                  const isChosen = chosen.has(badgeKey(badge));
                  const unavailable = full && !isChosen;
                  return (
                    <li key={badgeKey(badge)}>
                      <button
                        type="button"
                        className={`${styles.choice} ${isChosen ? styles.chosen : ""} ${unavailable ? styles.unavailable : ""}`}
                        aria-pressed={isChosen}
                        aria-disabled={unavailable || undefined}
                        onClick={() => toggle(badge)}
                      >
                        <BadgeArt badge={badge} className={styles.choiceArt} />
                        <span className={styles.choiceName}>{badgeName(badge)}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </section>

        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  );
}
