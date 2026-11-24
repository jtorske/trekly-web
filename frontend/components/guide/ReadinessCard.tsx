"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import ui from "@/components/ui.module.css";
import { nextQuery } from "@/lib/authLogic";
import { isoDate } from "@/lib/guide";
import { getReadiness, type Readiness, type ReadinessReason } from "@/lib/guideApi";
import { trailHref } from "@/lib/site";
import { GuideAvatar } from "./GuidePlanner";
import styles from "./ReadinessCard.module.css";

const LEVEL_LABELS: Record<ReadinessReason["level"], string> = {
  ready: "Fine",
  stretch: "A stretch",
  not_yet: "Not yet",
  info: "Note",
};

const VERDICT_LEADS: Record<Readiness["verdict"], string> = {
  ready: "This fits what you've done.",
  stretch: "Doable, but a step up for you.",
  not_yet: "Build up to this one first.",
};

/** Link-ify the avalanche.ca mention in a reason. */
function ReasonText({ text }: { text: string }) {
  const parts = text.split(/(https:\/\/avalanche\.ca)/);
  return (
    <>
      {parts.map((part, index) =>
        part === "https://avalanche.ca" ? (
          <a key={index} href={part} target="_blank" rel="noopener noreferrer" className={styles.link}>
            avalanche.ca
          </a>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}

function Result({ data }: { data: Readiness }) {
  // The estimate has its own line; a long-day warning stays in the list.
  const reasons = data.reasons
    .filter((reason) => !(reason.kind === "duration" && reason.level === "info"))
    .sort((a, b) => Number(a.level === "info") - Number(b.level === "info"));
  return (
    <>
      <div className={styles.verdictRow}>
        <span className={`${styles.verdict} ${styles[data.verdict]}`}>{data.label}</span>
        <span className={styles.lead}>{VERDICT_LEADS[data.verdict]}</span>
      </div>
      {data.est_label && (
        <p className={styles.estimate}>
          Estimated time for you: <strong>about {data.est_label}</strong> of moving time
          {data.pace_confidence === "low" ? " (standard pace)" : ` (your pace: ${data.pace_factor}×)`}
        </p>
      )}
      <ul className={styles.reasons}>
        {reasons.map((reason) => (
          <li key={reason.text} className={styles[`reason_${reason.level}`]}>
            <span className={ui.srOnly}>{LEVEL_LABELS[reason.level]}: </span>
            <ReasonText text={reason.text} />
          </li>
        ))}
      </ul>
      {data.build_up.length > 0 && (
        <div className={styles.buildUp}>
          <h3 className={styles.buildUpTitle}>Build up with these first</h3>
          <ul>
            {data.build_up.map((trail) => (
              <li key={trail.id}>
                <Link href={trailHref(trail)} className={styles.link}>
                  {trail.name}
                </Link>{" "}
                <span className={styles.muted}>{trail.region}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className={styles.footnote}>
        From your Trail Journal and Trekly&apos;s trail data. Conditions change: check the park before you go.
      </p>
    </>
  );
}

/**
 * "Am I ready?" on a trail page: a small card comparing the trail with the
 * signed-in hiker's history (GET /api/guide/readiness/{slug}). Visitors who
 * aren't signed in are asked to sign in.
 */
export default function ReadinessCard({ slug, onClose }: { slug: string; onClose: () => void }) {
  const { status } = useAuth();
  const dateId = useId();
  const headingId = useId();
  const today = isoDate(new Date());
  const [date, setDate] = useState(today);
  const [state, setState] = useState<{ key: string; data?: Readiness; error?: string } | null>(null);
  const key = `${slug}|${date}`;

  useEffect(() => {
    if (status !== "signedIn" || !date) return;
    const controller = new AbortController();
    getReadiness(slug, date === today ? null : date, controller.signal)
      .then((data) => setState({ key, data }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") {
          setState({ key, error: error instanceof Error ? error.message : "Couldn't check right now." });
        }
      });
    return () => controller.abort();
  }, [status, slug, date, today, key]);

  const current = state?.key === key ? state : null;

  return (
    <section className={styles.card} aria-labelledby={headingId}>
      <header className={styles.header}>
        <GuideAvatar size="sm" />
        <h2 id={headingId} className={styles.title}>
          Am I ready?
        </h2>
        <button type="button" className={styles.close} onClick={onClose} aria-label="Close Am I ready?">
          ×
        </button>
      </header>

      {status === "loading" && <div className={ui.skeleton} style={{ height: "5rem" }} aria-busy="true" />}
      {(status === "signedOut" || status === "unconfigured") && (
        <p className={styles.signIn}>
          <Link href={`/login${nextQuery(trailHref({ slug, id: slug }))}`} className={ui.primary}>
            Sign in
          </Link>
          <span>to check against your hiking history.</span>
        </p>
      )}
      {status === "signedIn" && (
        <>
          <label className={styles.dateRow} htmlFor={dateId}>
            <span>For</span>
            <input
              id={dateId}
              type="date"
              className={ui.input}
              value={date}
              min={today}
              onChange={(event) => setDate(event.target.value || today)}
            />
          </label>
          <div aria-live="polite">
            {!current && <div className={ui.skeleton} style={{ height: "6rem" }} aria-busy="true" aria-label="Checking" />}
            {current?.error && (
              <p className={ui.error} role="alert">
                {current.error}
              </p>
            )}
            {current?.data && <Result data={current.data} />}
          </div>
        </>
      )}
    </section>
  );
}
