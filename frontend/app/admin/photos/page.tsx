"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import Link from "next/link";
import TrailPhoto, { PhotoCredit } from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { pageOf } from "@/lib/paging";
import { hasNewCandidates, hasNoCandidates, moveActive, reviewShortcut } from "@/lib/photoReview";
import { formatDistance } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import { PHOTO_ACCEPT, PHOTO_HINT, PREPARING_PHOTO, photoProblemMessage } from "@/lib/photoPrep";
import { preparePhoto, TRAIL_PHOTO_EDGE } from "@/lib/preparePhoto";
import {
  CONFIDENCE_LABELS,
  trailPhotosAdminApi as api,
  type PhotoCandidate,
  type ReviewTrail,
} from "@/lib/trailPhotosAdminApi";
import AdminFrame from "../AdminFrame";
import admin from "../admin.module.css";
import styles from "./page.module.css";

const TOPO = "topo";
// Only this many trails (about 50 preview images) render at once.
const PAGE_SIZE = 10;
const DECISION_LABELS = { approved: "Photo approved", rejected: "Topo fallback", uploaded: "Your photo" } as const;
type Filter = "todo" | "none" | "all";

function message(error: unknown): string {
  return error instanceof Error ? error.message : "That didn't work. Try again.";
}

function CandidateOption({
  candidate,
  number,
  name,
  checked,
  onSelect,
}: {
  candidate: PhotoCandidate;
  number: number;
  name: string;
  checked: boolean;
  onSelect: () => void;
}) {
  const [units] = useUnits();
  const from = candidate.distance_from === "route" ? "from the route" : "from trailhead";
  return (
    <label className={`${styles.option} ${checked ? styles.optionChecked : ""}`}>
      <input type="radio" name={name} checked={checked} onChange={onSelect} className={ui.srOnly} />
      {/* Previews are hotlinked from the source; only approved photos are copied to Storage.
          Lazy and async: a page of ten trails holds up to fifty of them. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className={styles.preview}
        src={candidate.preview_url}
        alt=""
        width={300}
        height={200}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
      />
      <span className={styles.labels}>
        {number <= 5 && (
          <kbd className={styles.key} aria-hidden="true">
            {number}
          </kbd>
        )}
        <span className={`${styles.confidence} ${styles[candidate.confidence]}`}>{CONFIDENCE_LABELS[candidate.confidence]}</span>
        {candidate.low_res && (
          <span className={`${styles.confidence} ${styles.lowRes}`} title="Below the 1600px minimum; the hero will be softer">
            Lower resolution
          </span>
        )}
      </span>
      {/* "Names Brazeau Lake" / "Regional"; distances show below in the viewer's units. */}
      {candidate.match && !/^\d/.test(candidate.match) && <span className={styles.match}>{candidate.match.replace(/: .*$/, "")}</span>}
      <span className={styles.optionTitle}>{candidate.title}</span>
      <span className={styles.optionMeta}>
        {candidate.photographer} · {candidate.license} · {candidate.origin ?? candidate.source}
      </span>
      <span className={styles.optionMeta}>
        {candidate.width}×{candidate.height}px
        {candidate.distance_m != null && ` · ${formatDistance(candidate.distance_m / 1000, units)} ${from}`}
        {" · "}
        <a href={candidate.source_url} target="_blank" rel="noopener noreferrer">
          Source
        </a>
      </span>
    </label>
  );
}

/** What the page's keyboard shortcuts call on the active trail. */
interface TrailReviewHandle {
  pick: (index: number) => void;
  noPhoto: () => void;
  /** Resolves true once the decision is saved. */
  save: () => Promise<boolean>;
}

const TrailReview = forwardRef<
  TrailReviewHandle,
  { item: ReviewTrail; active: boolean; onActivate: () => void; onChange: (next: ReviewTrail) => void }
>(function TrailReview({ item, active, onActivate, onChange }, ref) {
  const { trail } = item;
  const [choice, setChoice] = useState<string>(
    item.review?.decision === "approved" && item.review.candidate_id ? item.review.candidate_id : item.default_choice ?? TOPO,
  );
  const [busy, setBusy] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (work: () => Promise<Partial<ReviewTrail>>): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      onChange({ ...item, ...(await work()) });
      return true;
    } catch (problem) {
      setError(message(problem));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const reviewed = (decision: "approved" | "rejected" | "uploaded", candidateId: string | null) => ({
    decision,
    candidate_id: candidateId,
    reviewed_at: new Date().toISOString(),
  });

  const save = () =>
    run(async () => {
      if (choice === TOPO) {
        await api.reject(trail.id);
        const keepsOwn = item.review?.decision === "uploaded";
        return { trail: { ...trail, photo: keepsOwn ? trail.photo : null }, review: reviewed("rejected", null) };
      }
      const photo = await api.approve(trail.id, choice);
      return { trail: { ...trail, photo }, review: reviewed("approved", choice) };
    });

  useImperativeHandle(ref, () => ({
    pick: (index) => {
      const candidate = item.candidates[index];
      if (candidate) setChoice(candidate.id);
    },
    noPhoto: () => setChoice(TOPO),
    save: () => (busy || preparing ? Promise.resolve(false) : save()),
  }));

  const upload = async (picked: File | undefined) => {
    if (!picked) return;
    setError(null);
    setPreparing(true);
    let file: File;
    try {
      // Upright and at most 3200px, so a 12 MB phone photo uploads quickly;
      // the API still checks it and makes the 1600px hero itself.
      file = await preparePhoto(picked, { maxEdge: TRAIL_PHOTO_EDGE, quality: 0.92 });
    } catch (caught) {
      setError(photoProblemMessage(caught));
      return;
    } finally {
      setPreparing(false);
    }
    void run(async () => {
      const photo = await api.upload(trail.id, file);
      return { trail: { ...trail, photo }, review: reviewed("uploaded", null) };
    });
  };

  const remove = () =>
    run(async () => {
      await api.removePhoto(trail.id);
      return { trail: { ...trail, photo: null }, review: null };
    });

  return (
    <section
      id={`review-${trail.id}`}
      className={`${styles.trail} ${active ? styles.trailActive : ""}`}
      aria-busy={busy || preparing}
      aria-current={active ? "true" : undefined}
      onPointerDown={onActivate}
      onFocus={onActivate}
    >
      <div className={styles.current}>
        <TrailPhoto photo={trail.photo} name={trail.name} variant="thumb" />
        <PhotoCredit photo={trail.photo} />
      </div>
      <div className={styles.body}>
        <h2 className={styles.trailName}>
          <Link href={`/trails?id=${encodeURIComponent(trail.id)}`}>{trail.name}</Link>
        </h2>
        <p className={styles.trailMeta}>
          #{trail.popularity_rank} · {trail.region}
          {item.review && <span className={ui.badge}>{DECISION_LABELS[item.review.decision]}</span>}
          {hasNewCandidates(item) && item.review && <span className={ui.badge}>New candidates</span>}
        </p>

        <fieldset className={styles.options} disabled={busy}>
          <legend className={ui.srOnly}>Photo for {trail.name}</legend>
          {item.candidates.map((candidate, index) => (
            <CandidateOption
              key={candidate.id}
              candidate={candidate}
              number={index + 1}
              name={`photo-${trail.id}`}
              checked={choice === candidate.id}
              onSelect={() => setChoice(candidate.id)}
            />
          ))}
          <label className={`${styles.option} ${styles.topoOption} ${choice === TOPO ? styles.optionChecked : ""}`}>
            <input type="radio" name={`photo-${trail.id}`} checked={choice === TOPO} onChange={() => setChoice(TOPO)} className={ui.srOnly} />
            <span className={styles.optionTitle}>
              <kbd className={styles.key} aria-hidden="true">
                N
              </kbd>{" "}
              No photo
            </span>
            <span className={styles.optionMeta}>Reject these and show the topo background.</span>
          </label>
        </fieldset>
        {item.candidates.length === 0 && <p className={ui.hint}>The search found no usable candidates for this trail.</p>}

        <div className={styles.actions}>
          <button type="button" className={ui.primary} onClick={() => void save()} disabled={busy}>
            {busy ? "Saving…" : choice === TOPO ? "Use topo" : "Approve photo"}
          </button>
          <label className={ui.secondary} title={PHOTO_HINT}>
            {preparing ? PREPARING_PHOTO : "Upload my own"}
            <input
              type="file"
              accept={PHOTO_ACCEPT}
              className={ui.srOnly}
              disabled={busy || preparing}
              onChange={(event) => {
                void upload(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
          {trail.photo && (
            <button type="button" className={ui.ghost} onClick={() => void remove()} disabled={busy}>
              Remove photo
            </button>
          )}
        </div>
        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  );
});

/** Keys typed into these are text, not shortcuts. Radios are fine: 1–5 replace their arrow keys. */
function typingIn(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  return target instanceof HTMLInputElement && target.type !== "radio";
}

function PhotoReview() {
  const [state, setState] = useState<
    { status: "loading" } | { status: "forbidden" } | { status: "error"; error: string } | { status: "ready"; trails: ReviewTrail[] }
  >({ status: "loading" });
  const [units] = useUnits();
  const [filter, setFilter] = useState<Filter>("todo");
  const [page, setPage] = useState(0);
  const [active, setActive] = useState(0);
  const handles = useRef(new Map<string, TrailReviewHandle>());
  // Bumped by the arrow keys only, so loading the page doesn't scroll.
  const [moved, setMoved] = useState(0);

  // The state starts as "loading"; Retry resets it before calling this.
  const load = useCallback(() => {
    api
      .isAdmin()
      .then(() => api.list())
      .then((trails) => setState({ status: "ready", trails }))
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 403) setState({ status: "forbidden" });
        else setState({ status: "error", error: message(error) });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const trails = useMemo(() => (state.status === "ready" ? state.trails : []), [state]);
  const counts = useMemo(
    () => ({ todo: trails.filter(hasNewCandidates).length, none: trails.filter(hasNoCandidates).length, all: trails.length }),
    [trails],
  );
  const filtered = useMemo(
    () => (filter === "todo" ? trails.filter(hasNewCandidates) : filter === "none" ? trails.filter(hasNoCandidates) : trails),
    [trails, filter],
  );
  const shown = pageOf(filtered, page, PAGE_SIZE);
  // A reviewed trail leaves "To review", so the same index is then the next one.
  const activeIndex = Math.min(active, Math.max(shown.items.length - 1, 0));
  const activeItem = shown.items[activeIndex];

  const showFilter = (next: Filter) => {
    setFilter(next);
    setPage(0);
    setActive(0);
  };
  const goTo = (next: number, index = 0) => {
    setPage(next);
    setActive(index);
    if (index === 0) window.scrollTo({ top: 0 });
  };
  const move = useCallback(
    (by: 1 | -1) => {
      const next = moveActive({ page: shown.page, index: activeIndex }, by, filtered.length, PAGE_SIZE);
      setPage(next.page);
      setActive(next.index);
      setMoved((n) => n + 1);
    },
    [shown.page, activeIndex, filtered.length],
  );

  const activeId = activeItem?.trail.id;
  useEffect(() => {
    // scroll-margin-top in the CSS keeps it clear of the admin header.
    if (moved && activeId) document.getElementById(`review-${activeId}`)?.scrollIntoView({ block: "start" });
  }, [moved, activeId]);

  useEffect(() => {
    if (state.status !== "ready") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || typingIn(event.target)) return;
      const shortcut = reviewShortcut(event.key);
      if (!shortcut) return;
      // Enter on a button or link keeps doing what it says.
      if (shortcut.kind === "save" && event.target instanceof Element && event.target.closest("button, a")) return;
      const handle = activeItem && handles.current.get(activeItem.trail.id);
      if (shortcut.kind === "move") {
        event.preventDefault();
        move(shortcut.by);
        return;
      }
      if (!handle) return;
      event.preventDefault();
      if (shortcut.kind === "pick") handle.pick(shortcut.index);
      else if (shortcut.kind === "none") handle.noPhoto();
      else
        void handle.save().then((saved) => {
          // In "To review" the saved trail drops out and the next one takes its place.
          if (saved && filter !== "todo") move(1);
        });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.status, activeItem, move, filter]);

  const pager = shown.pages > 1 && (
    <nav className={styles.pager} aria-label="Pages">
      <button type="button" className={ui.ghost} onClick={() => goTo(shown.page - 1)} disabled={shown.page === 0}>
        Previous
      </button>
      <span>
        Page {shown.page + 1} of {shown.pages}
      </span>
      <button type="button" className={ui.ghost} onClick={() => goTo(shown.page + 1)} disabled={shown.page === shown.pages - 1}>
        Next
      </button>
    </nav>
  );
  const update = (next: ReviewTrail) =>
    setState((current) =>
      current.status === "ready"
        ? { ...current, trails: current.trails.map((t) => (t.trail.id === next.trail.id ? next : t)) }
        : current,
    );

  return (
    <>
        {state.status === "loading" && <p className={ui.hint}>Loading…</p>}
        {state.status === "forbidden" && <p className={ui.notice}>This page is only for photo admins.</p>}
        {state.status === "error" && (
          <p className={ui.error} role="alert">
            {state.error}{" "}
            <button type="button" className={ui.ghost} onClick={() => {
                setState({ status: "loading" });
                load();
              }}
            >
              Retry
            </button>
          </p>
        )}
        {state.status === "ready" && (
          <>
            <p className={admin.muted}>
              Pick the best photo for each trail, or reject them all to keep the topo background.{" "}
              <strong>Strong</strong> names the trail or a landmark on it, or was taken within {formatDistance(1, units)} of the route;{" "}
              <strong>Likely</strong> within {formatDistance(3, units)};{" "}
              <strong>Weak</strong>{" "}is a park or region match only. Trails whose
              best candidate is weak start on &ldquo;No photo&rdquo;.
            </p>
            <p className={styles.shortcuts}>
              Keys: <kbd className={styles.key}>1</kbd>–<kbd className={styles.key}>5</kbd> pick ·{" "}
              <kbd className={styles.key}>N</kbd> no photo · <kbd className={styles.key}>Enter</kbd> approve ·{" "}
              <kbd className={styles.key}>←</kbd> <kbd className={styles.key}>→</kbd> previous / next trail
            </p>
            <div className={ui.segmented} role="group" aria-label="Show">
              <button type="button" aria-pressed={filter === "todo"} onClick={() => showFilter("todo")}>
                To review ({counts.todo})
              </button>
              <button type="button" aria-pressed={filter === "none"} onClick={() => showFilter("none")}>
                No candidates ({counts.none})
              </button>
              <button type="button" aria-pressed={filter === "all"} onClick={() => showFilter("all")}>
                All ({counts.all})
              </button>
            </div>
            {filtered.length === 0 && (
              <p className={ui.hint}>{filter === "todo" ? "Nothing left to review." : "No trails here."}</p>
            )}
            {pager}
            {shown.items.map((item, index) => (
              <TrailReview
                key={item.trail.id}
                ref={(handle) => {
                  if (handle) handles.current.set(item.trail.id, handle);
                  else handles.current.delete(item.trail.id);
                }}
                item={item}
                active={index === activeIndex}
                onActivate={() => setActive(index)}
                onChange={update}
              />
            ))}
            {pager}
          </>
        )}
    </>
  );
}

export default function PhotoReviewPage() {
  return (
    <AdminFrame title="Trail photos">
      <PhotoReview />
    </AdminFrame>
  );
}
