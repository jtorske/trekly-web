"use client";

import { useEffect, useId, useImperativeHandle, useMemo, useRef, useState, type Ref } from "react";
import Link from "next/link";
import { ImagePlus, Mountain, Search, X } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import DateInput from "@/components/DateInput";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import { activityBlocker, canShareHikes } from "@/lib/activity";
import { undatedLabel } from "@/lib/hikeDate";
import { HIKE_NOTE_MAX, type HikeLog, type HikeLogInput } from "@/lib/hikeLogsApi";
import { PHOTO_ACCEPT, PREPARING_PHOTO, photoProblemMessage } from "@/lib/photoPrep";
import { preparePhoto } from "@/lib/preparePhoto";
import { processPhoto } from "@/lib/processPhoto";
import { onPrivacyUpdated, getPrivacy, type PrivacySettings } from "@/lib/profilesApi";
import { formatHikeDate } from "@/lib/publicProfile";
import { localToday } from "@/lib/stay";
import { removeImages, uploadHikePhoto } from "@/lib/storage";
import { formProblem, toast } from "@/lib/toast";
import { searchTrails, type TrailListItem } from "@/lib/trailsApi";
import { sectionHref } from "@/app/settings/settingsSections";
import styles from "./activity.module.css";

export interface ComposerHandle {
  /** Opens the composer (on phones it starts collapsed) and puts the cursor in the trail search. */
  open: () => void;
}

const SEARCH_LIMIT = 8;

/**
 * "Log a hike" at the top of the feed: pick a trail, a date (today, or "I
 * don't remember"), an optional note and photo, and whether to share it.
 * Saving goes through the journal's own save (useHikeLogs → PUT
 * /api/me/hike-logs, add_hikes on the server), so stamps, milestones, points
 * and their toasts all update as anywhere else. A trail already in the
 * journal updates that entry, as the trail page's dialog would.
 */
export default function Composer({
  handle,
  logs,
  save,
  onPosted,
  signInHref,
}: {
  handle: Ref<ComposerHandle>;
  logs: Map<string, HikeLog>;
  save: (trailId: string, input: HikeLogInput) => Promise<unknown>;
  /** After a save, so the feed can show the new post. */
  onPosted: () => void;
  signInHref: string;
}) {
  const { status, user } = useAuth();
  const today = localToday();
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ query: string; trails: TrailListItem[] } | null>(null);
  const [trail, setTrail] = useState<TrailListItem | null>(null);
  const [date, setDate] = useState(today);
  const [undated, setUndated] = useState(false);
  const [note, setNote] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [privacy, setPrivacy] = useState<PrivacySettings | null>(null);
  const [shareChoice, setShareChoice] = useState<boolean | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLElement>(null);
  const searchId = useId();
  const listId = useId();
  const noteId = useId();
  const photoId = useId();
  const signedIn = status === "signedIn";

  const shareAllowed = privacy !== null && canShareHikes(privacy);
  const share = shareAllowed && (shareChoice ?? true);
  const existing = trail ? (logs.get(trail.id) ?? null) : null;

  useImperativeHandle(handle, () => ({
    open: () => {
      setExpanded(true);
      requestAnimationFrame(() => {
        rootRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
        searchRef.current?.focus({ preventScroll: true });
      });
    },
  }));

  // Their sharing setting decides the box; it follows changes made elsewhere.
  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    getPrivacy(controller.signal)
      .then(setPrivacy)
      .catch(() => undefined);
    const stop = onPrivacyUpdated(setPrivacy);
    return () => {
      controller.abort();
      stop();
    };
  }, [signedIn]);

  // Trail search, a moment after typing stops.
  const trimmed = query.trim();
  useEffect(() => {
    if (!trimmed || trail) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchTrails(trimmed, controller.signal, { limit: SEARCH_LIMIT })
        .then((trails) => setResults({ query: trimmed, trails: trails.filter((t) => !t.retired_at) }))
        .catch(() => undefined);
    }, 200);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed, trail]);
  const shown = trimmed && results?.query === trimmed ? results.trails : null;

  const preview = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo]);
  useEffect(() => (preview ? () => URL.revokeObjectURL(preview) : undefined), [preview]);

  const pick = (picked: TrailListItem) => {
    setTrail(picked);
    setQuery("");
    setResults(null);
    setError(null);
    // An entry already in the journal keeps its note unless they change it.
    setNote(logs.get(picked.id)?.note ?? "");
  };

  const reset = () => {
    setTrail(null);
    setQuery("");
    setDate(localToday());
    setUndated(false);
    setNote("");
    setPhoto(null);
    setShareChoice(null);
    setError(null);
  };

  const post = async () => {
    if (!user || !trail) return;
    setBusy(true);
    setError(null);
    let uploaded: string | null = null;
    try {
      if (photo) uploaded = await uploadHikePhoto(user.id, await processPhoto(photo));
      await save(trail.id, {
        hiked_on: undated ? null : date,
        note: note.trim() || null,
        photo_path: uploaded ?? existing?.photo_path ?? null,
        // Only sent when it can take effect, as in the trail page's dialog.
        ...(shareAllowed ? { share } : {}),
      });
      reset();
      setExpanded(false);
      onPosted();
    } catch (caught) {
      if (uploaded) await removeImages("hike-photos", [uploaded]).catch(() => undefined);
      const problem = formProblem(caught);
      if (problem) setError(problem);
      else toast.failure("log your hike", caught, () => void post());
    } finally {
      setBusy(false);
    }
  };

  if (status === "signedOut") {
    return (
      <section className={`${styles.composer} ${styles.composerGuest}`} aria-label="Log a hike">
        <Mountain size={20} aria-hidden="true" className={styles.composerIcon} />
        <p>
          <strong>Been out on the trail?</strong> Sign in to log your hikes, earn badges and share them here.
        </p>
        <Link href={signInHref} className={ui.primary}>
          Sign in
        </Link>
      </section>
    );
  }

  return (
    <section ref={rootRef} className={styles.composer} data-expanded={expanded} aria-labelledby={searchId}>
      {/* Phones and tablets: a bar that opens the composer. */}
      <button
        type="button"
        className={styles.composerBar}
        onClick={() => {
          setExpanded(true);
          requestAnimationFrame(() => searchRef.current?.focus());
        }}
      >
        <Mountain size={18} aria-hidden="true" />
        <span>Log a hike</span>
        <span className={styles.composerBarHint}>Where did you go?</span>
      </button>

      <div className={styles.composerBody}>
        <div className={styles.composerTop}>
          <h2 id={searchId} className={styles.composerTitle}>
            Log a hike
          </h2>
          {expanded && (
            <button type="button" className={styles.composerClose} onClick={() => setExpanded(false)} aria-label="Close">
              <X size={18} aria-hidden="true" />
            </button>
          )}
        </div>

        {trail ? (
          <div className={styles.picked}>
            <span className={styles.pickedThumb}>
              <TrailPhoto photo={trail.photo} name={trail.name} variant="thumb" mini />
            </span>
            <span className={styles.pickedText}>
              <span className={styles.trailName}>{trail.name}</span>
              <span className={styles.trailMeta}>{trail.park_name ?? trail.region}</span>
            </span>
            <button
              type="button"
              className={ui.ghost}
              onClick={() => {
                setTrail(null);
                requestAnimationFrame(() => searchRef.current?.focus());
              }}
              disabled={busy}
            >
              Change
            </button>
          </div>
        ) : (
          <div className={styles.search}>
            <Search size={17} aria-hidden="true" className={styles.searchIcon} />
            <input
              ref={searchRef}
              type="search"
              className={`${ui.input} ${styles.searchInput}`}
              placeholder="Which trail did you hike?"
              aria-label="Search for the trail you hiked"
              role="combobox"
              aria-expanded={Boolean(shown)}
              aria-controls={listId}
              aria-autocomplete="list"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && shown?.[0]) {
                  event.preventDefault();
                  pick(shown[0]);
                }
              }}
            />
            {shown && (
              <ul id={listId} role="listbox" className={styles.results}>
                {shown.length === 0 && <li className={styles.noResults}>No trails match “{trimmed}”.</li>}
                {shown.map((option) => (
                  <li key={option.id} role="option" aria-selected={false}>
                    <button type="button" className={styles.result} onClick={() => pick(option)}>
                      <span className={styles.resultThumb}>
                        <TrailPhoto photo={option.photo} name={option.name} variant="thumb" mini />
                      </span>
                      <span className={styles.pickedText}>
                        <span className={styles.resultName}>{option.name}</span>
                        <span className={styles.trailMeta}>
                          {option.park_name ?? option.region}
                          {logs.has(option.id) && " · in your journal"}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {trail && (
          <div className={styles.composerFields}>
            {existing && (
              <p className={ui.hint} role="status">
                Already in your journal
                {existing.hiked_on ? ` (${formatHikeDate(existing.hiked_on)})` : ""}. Posting updates that entry.
              </p>
            )}
            <div className={styles.composerRow}>
              <label className={ui.field}>
                <span className={ui.label}>Date hiked</span>
                <DateInput
                  className={ui.input}
                  value={undated ? "" : date}
                  onChange={setDate}
                  max={today}
                  min="1900-01-01"
                  required={!undated}
                  disabled={undated}
                />
              </label>
              <label className={styles.check}>
                <input type="checkbox" checked={undated} onChange={(event) => setUndated(event.target.checked)} />
                I don&apos;t remember
              </label>
            </div>
            {undated && (
              <span className={ui.hint}>
                It&apos;ll show as &ldquo;{undatedLabel(user?.created_at)}&rdquo;. Seasonal and date milestones need a date.
              </span>
            )}

            <label className={ui.field}>
              <span className={ui.label} id={noteId}>
                Note <span className={styles.optional}>(optional)</span>
              </span>
              <textarea
                aria-labelledby={noteId}
                className={`${ui.input} ${styles.composerNote}`}
                value={note}
                maxLength={HIKE_NOTE_MAX}
                rows={3}
                placeholder="Who you went with, what you saw…"
                onChange={(event) => setNote(event.target.value)}
              />
            </label>

            {preview && (
              <div className={styles.composerPhoto}>
                {/* eslint-disable-next-line @next/next/no-img-element -- blob URL */}
                <img src={preview} alt="Your photo, ready to post" />
                <button type="button" className={styles.composerPhotoRemove} onClick={() => setPhoto(null)} aria-label="Remove photo">
                  <X size={16} aria-hidden="true" />
                </button>
              </div>
            )}

            <div className={styles.shareField}>
              <label className={`${styles.check} ${!shareAllowed ? styles.checkOff : ""}`}>
                <input
                  type="checkbox"
                  checked={share}
                  disabled={!shareAllowed}
                  onChange={(event) => setShareChoice(event.target.checked)}
                />
                Share to Activity
              </label>
              <span className={ui.hint}>
                {privacy === null ? (
                  "Shows this hike, with your note and photo, on the Activity page."
                ) : shareAllowed ? (
                  <>
                    Shows this hike, with your note and photo
                    {privacy.hide_hike_dates ? ", without the date" : ""}. Badges it earns are shared too.
                  </>
                ) : (
                  <>
                    {activityBlocker(privacy) ?? "Your activity isn't shared in the feed, so this goes to your journal only."}{" "}
                    <Link href={sectionHref("privacy")} className={styles.inlineLink}>
                      Privacy settings
                    </Link>
                  </>
                )}
              </span>
            </div>

            {error && (
              <p className={ui.error} role="alert">
                {error}
              </p>
            )}
          </div>
        )}

        <div className={styles.composerFoot}>
          <label htmlFor={photoId} className={`${ui.ghost} ${styles.photoButton}`} aria-disabled={!trail || preparing}>
            <ImagePlus size={17} aria-hidden="true" />
            {preparing ? PREPARING_PHOTO : photo ? "Replace photo" : "Photo"}
          </label>
          <input
            id={photoId}
            type="file"
            accept={PHOTO_ACCEPT}
            className={ui.srOnly}
            disabled={!trail || preparing || busy}
            onChange={async (event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (!file) return;
              setError(null);
              setPreparing(true);
              try {
                setPhoto(await preparePhoto(file));
              } catch (caught) {
                setError(photoProblemMessage(caught));
              } finally {
                setPreparing(false);
              }
            }}
          />
          <span className={styles.spacer} />
          <button
            type="button"
            className={ui.primary}
            onClick={() => void post()}
            disabled={!trail || busy || preparing || (!undated && !date)}
          >
            {busy ? "Posting…" : share ? "Post hike" : "Add to journal"}
          </button>
        </div>
      </div>
    </section>
  );
}
