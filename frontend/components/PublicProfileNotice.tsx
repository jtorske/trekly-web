"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getPrivacy, onPrivacyUpdated, updatePrivacy } from "@/lib/profilesApi";
import { useProfile } from "@/lib/useProfile";
import ui from "./ui.module.css";
import styles from "./PublicProfileNotice.module.css";

/**
 * A one-off corner card for accounts from before public profiles: they stay
 * private, and this explains that profiles can now be public, once, until
 * dismissed. (Choosing a username is a required step of its own; see
 * UsernameGate.)
 */
/** Toasts stack above the card instead of covering it (see Toaster.module.css). */
function reserveToastSpace(card: HTMLElement | null) {
  if (!card) return;
  const root = document.documentElement;
  const observer = new ResizeObserver(() =>
    root.style.setProperty("--bottom-ui-offset", `calc(${card.offsetHeight}px + 0.5rem)`),
  );
  observer.observe(card);
  return () => {
    observer.disconnect();
    root.style.removeProperty("--bottom-ui-offset");
  };
}

export default function PublicProfileNotice() {
  const router = useRouter();
  const pathname = usePathname();
  const { profile } = useProfile();
  const [noticePending, setNoticePending] = useState(false);

  useEffect(() => {
    if (!profile?.username) return;
    const controller = new AbortController();
    getPrivacy(controller.signal)
      .then((settings) => setNoticePending(settings.public_notice_pending))
      .catch(() => undefined);
    return () => controller.abort();
  }, [profile?.username]);

  // A change in Settings → Privacy clears the notice on the server; drop it here too.
  useEffect(() => onPrivacyUpdated((settings) => setNoticePending(settings.public_notice_pending)), []);

  if (!profile?.username || !noticePending || pathname.startsWith("/auth")) return null;
  const dismiss = () => {
    setNoticePending(false);
    updatePrivacy({ public_notice_pending: false }).catch(() => undefined);
  };
  return (
    <aside className={styles.card} aria-labelledby="public-notice-title" ref={reserveToastSpace}>
      <h2 id="public-notice-title" className={styles.title}>
        Profiles can now be public
      </h2>
      <p className={styles.text}>
        Trekly profiles can be shared at a public address, showing only the sections you pick. Yours is still private,
        and stays that way until you change it.
      </p>
      <div className={styles.actions}>
        <button
          type="button"
          className={ui.primary}
          onClick={() => {
            dismiss();
            router.push("/settings/privacy");
          }}
        >
          Review privacy settings
        </button>
        <button type="button" className={ui.ghost} onClick={dismiss}>
          Dismiss
        </button>
      </div>
    </aside>
  );
}
