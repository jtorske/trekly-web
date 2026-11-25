"use client";

import { useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { getChatStatus } from "@/lib/guideChatApi";
import GuideChat from "./GuideChat";
import GuidePlanner, { GuideAvatar } from "./GuidePlanner";
import styles from "./GuidePlanner.module.css";

type Open = { kind: "closed" } | { kind: "checking" } | { kind: "chat" } | { kind: "form"; notice?: string };

/**
 * "Plan with Trekly Guide". Signed in and chat available (GET
 * /api/guide/chat/status): the chat. Otherwise, or whenever chat falls back,
 * the guided planner, with no error shown.
 */
export default function GuideLauncher({
  hint = "Answer a few quick questions and get trails picked for you.",
  className,
}: {
  hint?: string;
  className?: string;
}) {
  const { status } = useAuth();
  const [open, setOpen] = useState<Open>({ kind: "closed" });

  const start = async () => {
    if (status !== "signedIn") {
      setOpen({ kind: "form" });
      return;
    }
    setOpen({ kind: "checking" });
    try {
      const chat = await getChatStatus();
      setOpen(chat.available ? { kind: "chat" } : { kind: "form" });
    } catch {
      setOpen({ kind: "form" });
    }
  };
  const close = () => setOpen({ kind: "closed" });

  return (
    <>
      <button
        type="button"
        className={`${styles.launcher} ${className ?? ""}`}
        onClick={() => void start()}
        aria-haspopup="dialog"
        aria-busy={open.kind === "checking"}
        disabled={open.kind === "checking"}
      >
        <GuideAvatar />
        <span className={styles.launcherText}>
          <span className={styles.launcherTitle}>Plan with Trekly Guide</span>
          <span className={styles.launcherHint}>{open.kind === "checking" ? "Opening…" : hint}</span>
        </span>
        <span className={styles.launcherArrow} aria-hidden="true">
          →
        </span>
      </button>
      {open.kind === "chat" && <GuideChat onClose={close} onFallback={(notice) => setOpen({ kind: "form", notice })} />}
      {open.kind === "form" && <GuidePlanner onClose={close} intro={open.notice} />}
    </>
  );
}
