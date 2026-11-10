"use client";

import { useEffect, useId, useRef, useState } from "react";
import Avatar from "@/components/Avatar";
import { highFiversLine, type ActivityPost, type HighFivers } from "@/lib/activity";
import { getHighFivers } from "@/lib/activityApi";
import { displayName } from "@/lib/publicProfile";
import styles from "./activity.module.css";

/**
 * "3 high fives". Hovering, focusing or tapping it shows who: hikers with a
 * public profile by name, everyone else as "N others". Loaded on first open,
 * and again whenever the count changes.
 */
export default function HighFiveCount({
  post,
  signedIn,
  viewer,
}: {
  post: Pick<ActivityPost, "id" | "high_fives">;
  signedIn: boolean;
  viewer: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [loaded, setLoaded] = useState<{ count: number; data: HighFivers } | null>(null);
  const [failed, setFailed] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  const popId = useId();
  const count = post.high_fives;
  const fresh = loaded?.count === count ? loaded.data : null;

  useEffect(() => {
    if (!open || fresh || count === 0) return;
    const controller = new AbortController();
    getHighFivers(post.id, signedIn, controller.signal)
      .then((data) => setLoaded({ count, data }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [open, fresh, count, post.id, signedIn]);

  // A tap pins it open; tapping elsewhere or Escape closes it.
  useEffect(() => {
    if (!pinned) return;
    const away = (event: PointerEvent) => {
      if (!wrap.current?.contains(event.target as Node)) {
        setPinned(false);
        setOpen(false);
      }
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPinned(false);
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [pinned]);

  if (count === 0) return null;
  const label = `${count} high five${count === 1 ? "" : "s"}`;

  return (
    <span
      ref={wrap}
      className={styles.fiveWrap}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => !pinned && setOpen(false)}
    >
      <button
        type="button"
        className={styles.fiveCount}
        aria-expanded={open}
        aria-controls={popId}
        aria-label={`${label}. Show who`}
        onFocus={() => setOpen(true)}
        onBlur={(event) => {
          if (!pinned && !wrap.current?.contains(event.relatedTarget as Node)) setOpen(false);
        }}
        onClick={() => {
          setPinned(!pinned);
          setOpen(!pinned);
        }}
      >
        {label}
      </button>
      {open && (
        <span id={popId} role="status" className={styles.fivePop}>
          {fresh ? (
            <>
              {fresh.hikers.length > 0 && (
                <span className={styles.fiveFaces} aria-hidden="true">
                  {fresh.hikers.slice(0, 6).map((hiker) => (
                    <Avatar key={hiker.username} path={hiker.avatar_path} name={hiker.display_name ?? hiker.username} email={null} size={24} />
                  ))}
                </span>
              )}
              <span>{highFiversLine(fresh, (hiker) => (hiker.username === viewer ? "You" : displayName(hiker)))}</span>
            </>
          ) : failed ? (
            "Couldn't load who high-fived."
          ) : (
            "Loading…"
          )}
        </span>
      )}
    </span>
  );
}
