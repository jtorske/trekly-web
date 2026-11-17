"use client";

import { useState } from "react";
import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import ui from "@/components/ui.module.css";
import { formatDateTime, timeAgo, whoLabel } from "@/lib/adminView";
import { KIND_LABELS, REASON_LABELS, moderationApi, type ModerationItem } from "@/lib/moderationAdminApi";
import { toast } from "@/lib/toast";
import { trailHref } from "@/lib/site";
import ActionDialog, { type ModerationAction } from "./ActionDialog";
import styles from "../admin.module.css";
import page from "./page.module.css";

type ActionKey = "approve" | "hide" | "warn" | "suspend" | "ban" | "unlock";

const SCORES_SHOWN = 4;

function percent(score: number): string {
  return score >= 0.995 ? "99%+" : score < 0.01 ? "<1%" : `${Math.round(score * 100)}%`;
}

function actionFor(key: ActionKey, item: ModerationItem, author: string): ModerationAction {
  const what = KIND_LABELS[item.kind].toLowerCase();
  switch (key) {
    case "approve":
      return {
        title: "Approve this?",
        body:
          item.state === "visible"
            ? `It stays up, and its open reports are resolved.`
            : `The ${what} goes back up for everyone, and its open reports are resolved.`,
        confirm: "Approve",
        danger: false,
      };
    case "hide":
      return {
        title: `Hide this ${what}?`,
        body: item.child_safety
          ? "It stays hidden and kept. The author is NOT emailed (child-safety items never are)."
          : `Nobody but ${author} sees it. They're emailed the reason below and how to appeal.`,
        confirm: "Hide",
        danger: true,
        reason: { label: "Reason (emailed to the author)", placeholder: "e.g. Personal attack on another hiker" },
      };
    case "warn":
      return {
        title: `Warn ${author}?`,
        body: "They get an email with the reason below and how to appeal. Nothing else changes.",
        confirm: "Send warning",
        danger: false,
        reason: { label: "Reason (emailed to them)" },
      };
    case "suspend":
      return {
        title: `Suspend ${author}?`,
        body: "They can't sign in or post until it ends. They're emailed the reason and the end date.",
        confirm: "Suspend",
        danger: true,
        days: true,
        reason: { label: "Reason (emailed to them)" },
      };
    case "ban":
      return {
        title: `Ban ${author}?`,
        body: "They can't sign in or post again until you lift it. A session already open ends within the hour.",
        confirm: "Ban",
        danger: true,
        reason: { label: "Reason (only admins see it)" },
      };
    case "unlock":
      return {
        title: `Lift ${author}'s restriction?`,
        body: "They can sign in and post again. A profile hidden by the lock stays hidden until you unhide it on their page.",
        confirm: "Lift it",
        danger: false,
      };
  }
}

/** One held, reported or decided item, with the one-click actions. */
export default function ModerationCard({ item, onChange }: { item: ModerationItem; onChange: () => void }) {
  const [acting, setActing] = useState<ActionKey | null>(null);
  const [allScores, setAllScores] = useState(false);
  const author = whoLabel(item.author);
  const scores = allScores ? item.scores : item.scores.slice(0, SCORES_SHOWN);

  const run = async (key: ActionKey, input: { reason: string; days: number }) => {
    const result =
      key === "approve"
        ? await moderationApi.approve(item.id)
        : key === "hide"
          ? await moderationApi.hide(item.id, input.reason)
          : key === "warn"
            ? await moderationApi.warn(item.author.id, input.reason)
            : key === "suspend"
              ? await moderationApi.suspend(item.author.id, input.days, input.reason)
              : key === "ban"
                ? await moderationApi.ban(item.author.id, input.reason)
                : await moderationApi.unlock(item.author.id);
    toast.success(result.message);
    onChange();
  };

  return (
    <li className={`${styles.listItem} ${item.child_safety ? page.childSafety : ""}`}>
      {item.child_safety && (
        <p className={page.alert} role="alert">
          <ShieldAlert size={16} aria-hidden="true" />
          <span>
            <strong>Possible child sexual abuse material.</strong>{" "}Hidden, kept and the account is locked. The photo
            isn&apos;t shown here. Follow the steps in the urgent email: report to{" "}
            <a href="https://www.cybertip.ca/en/report/" target="_blank" rel="noopener noreferrer">
              Cybertip.ca
            </a>
            , keep everything, and don&apos;t contact the account holder.
          </span>
        </p>
      )}
      <div className={styles.listRow}>
        <span>
          <strong>{KIND_LABELS[item.kind]}</strong>
          {" · "}
          <Link className={styles.link} href={`/admin/users/${item.author.id}`}>
            {author}
          </Link>
          {item.context && <span className={styles.muted}> · {item.context}</span>}
        </span>
        <span className={styles.pills}>
          {item.queue_reason && (
            <span className={item.queue_reason === "child_safety" ? styles.pillWarn : styles.pillDark}>
              {REASON_LABELS[item.queue_reason]}
            </span>
          )}
          {item.state !== "visible" && (
            <span className={styles.pillWarn}>{item.state === "held" ? "Held" : "Hidden"}</span>
          )}
          {item.open_reports > 0 && (
            <span className={styles.pill}>
              {item.open_reports} report{item.open_reports === 1 ? "" : "s"}
              {item.qualifying_reports !== item.open_reports ? ` (${item.qualifying_reports} counting)` : ""}
            </span>
          )}
        </span>
      </div>

      {item.text && <p className={styles.quote}>{item.text}</p>}
      {item.photo_url && (
        <a href={item.photo_url} target="_blank" rel="noopener noreferrer" className={page.photo}>
          {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL */}
          <img src={item.photo_url} alt={`${KIND_LABELS[item.kind]} under review`} />
        </a>
      )}
      {!item.photo_url && item.has_photo && !item.child_safety && (
        <span className={`${styles.small} ${styles.muted}`}>Has a photo (no preview available).</span>
      )}

      <div className={page.facts}>
        <span className={styles.small}>
          <span className={styles.muted}>Check:</span>{" "}
          {item.screening === "flagged"
            ? `flagged ${item.flagged_categories.join(", ")}`
            : item.screening === "passed"
              ? "passed"
              : item.screening === "unavailable"
                ? "didn't run (service down)"
                : "not checked"}
        </span>
        {scores.length > 0 && (
          <span className={page.scores}>
            {scores.map((score) => (
              <span key={score.category} className={score.score >= 0.5 ? page.scoreHigh : page.score}>
                {score.category} {percent(score.score)}
              </span>
            ))}
            {item.scores.length > SCORES_SHOWN && (
              <button type="button" className={page.more} onClick={() => setAllScores(!allScores)}>
                {allScores ? "Fewer" : `All ${item.scores.length}`}
              </button>
            )}
          </span>
        )}
        <span className={`${styles.small} ${styles.muted}`}>
          {item.author.restriction ? `Account ${item.author.restriction}` : "Account active"}
          {item.author.joined ? ` · joined ${timeAgo(item.author.joined)}` : ""}
          {item.author.email_confirmed === false ? " · email not confirmed" : ""}
          {item.author.previous_items > 0 ? ` · ${item.author.previous_items} earlier held or hidden` : ""}
        </span>
      </div>

      {item.reports.length > 0 && (
        <ul className={page.reports}>
          {item.reports.map((report) => (
            <li key={report.id} className={styles.small}>
              <span className={styles.pill}>{report.reason}</span>{" "}
              <Link className={styles.link} href={`/admin/users/${report.reporter.id}`}>
                {whoLabel(report.reporter)}
              </Link>{" "}
              <span className={styles.muted} title={formatDateTime(report.created_at)}>
                {timeAgo(report.created_at)}
                {!report.counts_toward_hide && " · doesn't count toward the auto-hide"}
                {report.status === "resolved" && " · resolved"}
              </span>
              {report.details && <span className={page.reportDetails}>{report.details}</span>}
            </li>
          ))}
        </ul>
      )}

      <span className={`${styles.muted} ${styles.small}`} title={formatDateTime(item.activity_at)}>
        Last activity {timeAgo(item.activity_at)}
        {item.decision && item.decided_by && (
          <>
            {" · "}
            {item.decision} by {whoLabel(item.decided_by)} {timeAgo(item.decided_at)}
            {item.decision_reason ? `: “${item.decision_reason}”` : ""}
          </>
        )}
      </span>

      <div className={styles.reportActions}>
        <button type="button" className={ui.primary} onClick={() => setActing("approve")}>
          Approve
        </button>
        {item.state !== "hidden" && (
          <button type="button" className={ui.danger} onClick={() => setActing("hide")}>
            Hide
          </button>
        )}
        {!item.child_safety && (
          <>
            <button type="button" className={ui.secondary} onClick={() => setActing("warn")}>
              Warn
            </button>
            {item.author.restriction === null && (
              <button type="button" className={ui.secondary} onClick={() => setActing("suspend")}>
                Suspend
              </button>
            )}
          </>
        )}
        {item.author.restriction === null ? (
          <button type="button" className={ui.ghost} onClick={() => setActing("ban")}>
            Ban
          </button>
        ) : (
          <button type="button" className={ui.ghost} onClick={() => setActing("unlock")}>
            Lift {item.author.restriction === "locked" ? "lock" : "suspension"}
          </button>
        )}
        {item.trail && (
          <Link className={styles.link} href={trailHref(item.trail)} target="_blank">
            View trail ↗
          </Link>
        )}
      </div>

      {acting && (
        <ActionDialog
          action={actionFor(acting, item, author)}
          onClose={() => setActing(null)}
          onConfirm={(input) => run(acting, input)}
        />
      )}
    </li>
  );
}
