"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import RequireAuth from "@/components/RequireAuth";
import TrailPhoto, { PhotoCredit } from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { pageOf } from "@/lib/paging";
import { photoInputProblem } from "@/lib/journalPhoto";
import {
  CONFIDENCE_LABELS,
  trailPhotosAdminApi as api,
  type PhotoCandidate,
  type ReviewTrail,
} from "@/lib/trailPhotosAdminApi";
import profile from "@/app/profile/page.module.css";
import styles from "./page.module.css";

const TOPO = "topo";
// Only this many trails (about 30 preview images) render at once.
const PAGE_SIZE = 10;
const DECISION_LABELS = { approved: "Photo approved", rejected: "Topo fallback", uploaded: "Your photo" } as const;

function message(error: unknown): string {
  return error instanceof Error ? error.message : "That didn't work. Try again.";
}

function CandidateOption({
  candidate,
  name,
  checked,
  onSelect,
}: {
  candidate: PhotoCandidate;
  name: string;
  checked: boolean;
  onSelect: () => void;
}) {
  return (
    <label className={`${styles.option} ${checked ? styles.optionChecked : ""}`}>
      <input type="radio" name={name} checked={checked} onChange={onSelect} className={ui.srOnly} />
      {/* Previews are hotlinked from the source; only approved photos are copied to Storage. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className={styles.preview} src={candidate.preview_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
      <span className={styles.labels}>
        <span className={`${styles.confidence} ${styles[candidate.confidence]}`}>{CONFIDENCE_LABELS[candidate.confidence]}</span>
        {candidate.low_res && (
          <span className={`${styles.confidence} ${styles.lowRes}`} title="Below the 1600px minimum; the hero will be softer">
            Lower resolution
          </span>
        )}
      </span>
      <span className={styles.optionTitle}>{candidate.title}</span>
      <span className={styles.optionMeta}>
        {candidate.photographer} · {candidate.license} · {candidate.origin ?? candidate.source}
      </span>
      <span className={styles.optionMeta}>
        {candidate.width}×{candidate.height}px
        {candidate.distance_m != null && ` · ${(candidate.distance_m / 1000).toFixed(1)} km from trailhead`}
        {" · "}
        <a href={candidate.source_url} target="_blank" rel="noopener noreferrer">
          Source
        </a>
      </span>
    </label>
  );
}

function TrailReview({ item, onChange }: { item: ReviewTrail; onChange: (next: ReviewTrail) => void }) {
  const { trail } = item;
  const [choice, setChoice] = useState<string>(
    item.review?.decision === "approved" && item.review.candidate_id ? item.review.candidate_id : item.default_choice ?? TOPO,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (work: () => Promise<Partial<ReviewTrail>>) => {
    setBusy(true);
    setError(null);
    try {
      onChange({ ...item, ...(await work()) });
    } catch (problem) {
      setError(message(problem));
    } finally {
      setBusy(false);
    }
  };

  const save = () =>
    run(async () => {
      if (choice === TOPO) {
        await api.reject(trail.id);
        const keepsOwn = item.review?.decision === "uploaded";
        return {
          trail: { ...trail, photo: keepsOwn ? trail.photo : null },
          review: { decision: "rejected", candidate_id: null },
        };
      }
      const photo = await api.approve(trail.id, choice);
      return { trail: { ...trail, photo }, review: { decision: "approved", candidate_id: choice } };
    });

  const upload = (file: File | undefined) => {
    if (!file) return;
    const problem = photoInputProblem(file);
    if (problem) {
      setError(problem);
      return;
    }
    void run(async () => {
      const photo = await api.upload(trail.id, file);
      return { trail: { ...trail, photo }, review: { decision: "uploaded", candidate_id: null } };
    });
  };

  const remove = () =>
    run(async () => {
      await api.removePhoto(trail.id);
      return { trail: { ...trail, photo: null }, review: null };
    });

  return (
    <section className={styles.trail} aria-busy={busy}>
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
        </p>

        <fieldset className={styles.options} disabled={busy}>
          <legend className={ui.srOnly}>Photo for {trail.name}</legend>
          {item.candidates.map((candidate) => (
            <CandidateOption
              key={candidate.id}
              candidate={candidate}
              name={`photo-${trail.id}`}
              checked={choice === candidate.id}
              onSelect={() => setChoice(candidate.id)}
            />
          ))}
          <label className={`${styles.option} ${styles.topoOption} ${choice === TOPO ? styles.optionChecked : ""}`}>
            <input type="radio" name={`photo-${trail.id}`} checked={choice === TOPO} onChange={() => setChoice(TOPO)} className={ui.srOnly} />
            <span className={styles.optionTitle}>No photo</span>
            <span className={styles.optionMeta}>Reject these and show the topo background.</span>
          </label>
        </fieldset>
        {item.candidates.length === 0 && <p className={ui.hint}>The search found no usable candidates for this trail.</p>}

        <div className={styles.actions}>
          <button type="button" className={ui.primary} onClick={save} disabled={busy}>
            {busy ? "Saving…" : choice === TOPO ? "Use topo" : "Approve photo"}
          </button>
          <label className={ui.secondary}>
            Upload my own
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className={ui.srOnly}
              disabled={busy}
              onChange={(event) => {
                upload(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
          {trail.photo && (
            <button type="button" className={ui.ghost} onClick={remove} disabled={busy}>
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
}

function PhotoReview() {
  const [state, setState] = useState<
    { status: "loading" } | { status: "forbidden" } | { status: "error"; error: string } | { status: "ready"; trails: ReviewTrail[] }
  >({ status: "loading" });
  const [filter, setFilter] = useState<"todo" | "all">("todo");
  const [page, setPage] = useState(0);

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
  const filtered = useMemo(() => (filter === "todo" ? trails.filter((t) => !t.review) : trails), [trails, filter]);
  const shown = pageOf(filtered, page, PAGE_SIZE);
  const showFilter = (next: "todo" | "all") => {
    setFilter(next);
    setPage(0);
  };
  const goTo = (next: number) => {
    setPage(next);
    window.scrollTo({ top: 0 });
  };
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
    <main className={profile.page}>
      <div className={profile.wrap}>
        <h1 className={profile.name}>Trail photos</h1>
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
            <p className={profile.bio}>
              Pick the best photo for each trail, or reject them all to keep the topo background. Trails whose best
              candidate is only a regional shot or a keyword match start on &ldquo;No photo&rdquo;.
            </p>
            <div className={ui.segmented} role="group" aria-label="Show">
              <button type="button" aria-pressed={filter === "todo"} onClick={() => showFilter("todo")}>
                To review ({trails.filter((t) => !t.review).length})
              </button>
              <button type="button" aria-pressed={filter === "all"} onClick={() => showFilter("all")}>
                All ({trails.length})
              </button>
            </div>
            {filtered.length === 0 && <p className={ui.hint}>Nothing left to review.</p>}
            {pager}
            {shown.items.map((item) => (
              <TrailReview key={item.trail.id} item={item} onChange={update} />
            ))}
            {pager}
          </>
        )}
      </div>
    </main>
  );
}

export default function PhotoReviewPage() {
  return (
    <Suspense fallback={<main className={profile.page} />}>
      <RequireAuth fallback={<main className={profile.page} aria-busy="true" />}>
        <PhotoReview />
      </RequireAuth>
    </Suspense>
  );
}
