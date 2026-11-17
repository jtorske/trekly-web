import Link from "next/link";
import { Hourglass, ShieldAlert } from "lucide-react";
import { APPEAL_EMAIL, reviewMessage, type ReviewState } from "@/lib/moderation";
import styles from "./ReviewNotice.module.css";

/**
 * On the author's own content only: "Your post is being reviewed" while
 * moderation holds it, or that a moderator removed it. Nobody else sees the
 * content, or this notice.
 */
export default function ReviewNotice({
  state,
  what = "post",
  className,
}: {
  state: ReviewState;
  /** "post", "note", "photo", "bio", "profile photo"… */
  what?: string;
  className?: string;
}) {
  const Icon = state === "pending" ? Hourglass : ShieldAlert;
  return (
    <p className={`${styles.notice} ${state === "hidden" ? styles.hidden : ""} ${className ?? ""}`} role="status">
      <Icon size={15} aria-hidden="true" />
      <span>
        {reviewMessage(state, what)}{" "}
        {state === "hidden" ? (
          <>
            Think it&apos;s a mistake? Email <a href={`mailto:${APPEAL_EMAIL}`}>{APPEAL_EMAIL}</a>.
          </>
        ) : (
          <Link href="/guidelines">Community Guidelines</Link>
        )}
      </span>
    </p>
  );
}
