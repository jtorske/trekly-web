"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { nextQuery } from "@/lib/authLogic";
import { announceFollow, followButton, followToast, onFollowChanged, type FollowState } from "@/lib/follows";
import { setFollow } from "@/lib/followsApi";
import { toast } from "@/lib/toast";
import styles from "./FollowButton.module.css";

/**
 * Follow, Request to follow, Following and Requested, all one button.
 * Pressing Following or Requested undoes it; leaving a private profile asks
 * first, since getting back in takes a new request. `state` null means the
 * viewer is signed out: the button then leads to sign-in. Every button for
 * the same person on the page stays in step.
 */
export default function FollowButton({
  username,
  name,
  state,
  isPrivate,
  size = "md",
  onChange,
}: {
  username: string;
  name: string;
  state: FollowState | null;
  isPrivate: boolean;
  size?: "sm" | "md";
  onChange?: (state: FollowState, followersCount: number) => void;
}) {
  const pathname = usePathname();
  const [current, setCurrent] = useState<{ from: FollowState | null; value: FollowState | null }>({
    from: state,
    value: state,
  });
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  // A new state from the parent (e.g. a reload) wins over what we had.
  const value = current.from === state ? current.value : state;

  useEffect(
    () =>
      onFollowChanged((who, follow) => {
        if (who === username) setCurrent({ from: state, value: follow });
      }),
    [username, state],
  );

  const sizeClass = size === "sm" ? styles.sm : "";
  if (value === null) {
    return (
      <Link href={`/login${nextQuery(pathname)}`} className={`${ui.primary} ${styles.button} ${sizeClass}`}>
        {isPrivate ? "Request to follow" : "Follow"}
      </Link>
    );
  }

  const { label, next } = followButton(value, isPrivate);

  const run = async () => {
    setConfirming(false);
    setBusy(true);
    try {
      const saved = await setFollow(username, next === "follow");
      setCurrent({ from: state, value: saved.follow });
      announceFollow(username, saved.follow);
      onChange?.(saved.follow, saved.followers_count);
      const message = followToast(value, saved.follow, name);
      if (message) toast.success(message);
    } catch (caught) {
      toast.failure(next === "follow" ? `follow ${name}` : value === "requested" ? "cancel the request" : `unfollow ${name}`, caught);
    } finally {
      setBusy(false);
    }
  };

  const press = () => {
    if (value === "following" && isPrivate) setConfirming(true);
    else void run();
  };

  return (
    <>
      <button
        type="button"
        className={`${value === "none" ? ui.primary : `${ui.secondary} ${styles.on}`} ${styles.button} ${sizeClass}`}
        onClick={press}
        disabled={busy}
        aria-pressed={value !== "none"}
        aria-label={value === "none" ? `${label}: ${name}` : `${label} ${name}. Press to ${value === "requested" ? "cancel the request" : "unfollow"}.`}
      >
        {label}
      </button>
      {confirming && (
        <Dialog
          title={`Unfollow ${name}?`}
          subtitle="Their profile is private. To see it again, you'll need to send a new request."
          onClose={() => setConfirming(false)}
          size="sm"
          footer={
            <>
              <button type="button" className={ui.ghost} onClick={() => setConfirming(false)}>
                Keep following
              </button>
              <button type="button" className={ui.danger} onClick={() => void run()}>
                Unfollow
              </button>
            </>
          }
        >
          {null}
        </Dialog>
      )}
    </>
  );
}
