"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
  type TouchEvent,
} from "react";
import {
  Backpack,
  BookOpen,
  Compass,
  LogIn,
  UserPlus,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  LogOutRow,
  ProfileRow,
  ROW_ICONS,
  RowIcon,
  type AccountIdentity,
} from "./AccountMenu";
import {
  NAV_LINKS,
  PROFILE_HREF,
  currentMobileHref,
  isSwipeClose,
  mobileAccountLinks,
} from "@/lib/accountMenu";
import accountStyles from "./AccountMenu.module.css";
import styles from "./MobileMenu.module.css";

const NAV_ICONS: Record<string, LucideIcon> = {
  "/trail-list": Compass,
  "/gear": Backpack,
  "/journal": BookOpen,
};

const reducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * The phone menu (below 900px): one sheet that slides in from the right over
 * a dimmed backdrop. Signed in it holds the profile header, Navigation,
 * Account and Log out; signed out, Navigation plus Sign in and Sign up.
 *
 * Built on a modal <dialog>, so focus stays inside and the page behind is
 * inert. Closes on a backdrop tap, Escape, a swipe right or choosing an item;
 * page scroll is locked while open and focus returns to `returnFocusTo`.
 * Mount it to open it; `onClose` runs once the slide-out has finished.
 */
export default function MobileMenu({
  identity,
  pathname,
  search,
  returnTo,
  returnFocusTo,
  onClose,
}: {
  /** The signed-in account, or null when signed out. */
  identity: AccountIdentity | null;
  pathname: string;
  /** The query string when the menu opened, to tell profile tabs apart. */
  search: string;
  /** `?next=` for Sign in and Sign up. */
  returnTo: string;
  returnFocusTo: RefObject<HTMLElement | null>;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [closing, setClosing] = useState(false);
  const closingRef = useRef(false);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // Fallback for a slide-out whose animationend never fires (e.g. a
  // backgrounded tab). Cleared once closed, so it can't shut a reopened menu.
  const fallbackRef = useRef<number | undefined>(undefined);
  const finish = useCallback(() => {
    window.clearTimeout(fallbackRef.current);
    onCloseRef.current();
  }, []);
  useEffect(() => () => window.clearTimeout(fallbackRef.current), []);

  /** Slide out, then unmount (straight away with reduced motion). */
  const requestClose = useCallback(() => {
    if (closingRef.current) return;
    closingRef.current = true;
    if (reducedMotion()) {
      finish();
      return;
    }
    setClosing(true);
    fallbackRef.current = window.setTimeout(finish, 400);
  }, [finish]);

  useEffect(() => {
    const dialog = dialogRef.current;
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    root.style.overflow = "hidden";
    if (dialog && !dialog.open) {
      dialog.showModal();
      // Start on the first row (the profile header, or Explore) rather than
      // the close button.
      const marked = dialog.querySelector<HTMLElement>("[data-autofocus]");
      (marked?.matches("a, button")
        ? marked
        : marked?.querySelector<HTMLElement>("a, button")
      )?.focus();
    }
    const focusTarget = returnFocusTo.current;
    return () => {
      dialog?.close();
      root.style.overflow = previousOverflow;
      if (focusTarget?.isConnected) focusTarget.focus();
    };
  }, [returnFocusTo]);

  // Swipe right to close: the sheet follows the finger, then either slides
  // out or springs back. Vertical drags are left to scroll the sheet.
  const drag = useRef<{
    x: number;
    y: number;
    t: number;
    dx: number;
    horizontal: boolean | null;
  } | null>(null);
  const onTouchStart = (event: TouchEvent) => {
    const touch = event.touches[0];
    drag.current = {
      x: touch.clientX,
      y: touch.clientY,
      t: event.timeStamp,
      dx: 0,
      horizontal: null,
    };
  };
  const onTouchMove = (event: TouchEvent) => {
    const state = drag.current;
    const dialog = dialogRef.current;
    if (!state || !dialog) return;
    const touch = event.touches[0];
    const dx = touch.clientX - state.x;
    const dy = touch.clientY - state.y;
    if (state.horizontal === null && Math.hypot(dx, dy) > 8)
      state.horizontal = Math.abs(dx) > Math.abs(dy);
    if (!state.horizontal) return;
    state.dx = Math.max(0, dx);
    dialog.style.transition = "none";
    dialog.style.transform = `translateX(${state.dx}px)`;
  };
  const onTouchEnd = (event: TouchEvent) => {
    const state = drag.current;
    const dialog = dialogRef.current;
    drag.current = null;
    if (!state?.horizontal || !dialog) return;
    const touch = event.changedTouches[0];
    dialog.style.transition = "";
    if (
      isSwipeClose(state.dx, touch.clientY - state.y, event.timeStamp - state.t)
    ) {
      requestClose();
    } else {
      dialog.style.transform = "";
    }
  };

  const current = currentMobileHref(pathname, search);
  const currentProps = (href: string) =>
    current === href ? { "aria-current": "page" as const } : {};
  const row = accountStyles.row;

  return (
    <dialog
      ref={dialogRef}
      id="mobile-navigation"
      className={`${accountStyles.card} ${styles.sheet}`}
      data-closing={closing || undefined}
      aria-label="Menu"
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.preventDefault();
        requestClose();
      }}
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onClick={(event) => {
        // The sheet's content fills the dialog, so a click on the dialog
        // itself is a click on the backdrop.
        if (event.target === event.currentTarget) requestClose();
      }}
      onAnimationEnd={(event) => {
        if (closing && event.target === event.currentTarget) finish();
      }}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      onTouchCancel={() => {
        drag.current = null;
        if (dialogRef.current) dialogRef.current.style.transform = "";
      }}
    >
      <div className={styles.inner}>
        <div className={styles.top}>
          <button
            type="button"
            className={styles.close}
            aria-label="Close menu"
            onClick={requestClose}
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        {identity && (
          <div className={styles.profile} data-autofocus>
            <ProfileRow
              identity={identity}
              current={current === PROFILE_HREF}
              onChoose={requestClose}
            />
          </div>
        )}

        <nav className={styles.group} aria-labelledby="mobile-menu-nav">
          <h2 id="mobile-menu-nav" className={styles.label}>
            Navigation
          </h2>
          {NAV_LINKS.map((link, index) => (
            <Link
              key={link.href}
              href={link.href}
              className={row}
              {...currentProps(link.href)}
              {...(!identity && index === 0 ? { "data-autofocus": true } : {})}
              onClick={requestClose}
            >
              <RowIcon icon={NAV_ICONS[link.href]} />
              {link.label}
            </Link>
          ))}
        </nav>

        {identity ? (
          <>
            <nav className={styles.group} aria-labelledby="mobile-menu-account">
              <h2 id="mobile-menu-account" className={styles.label}>
                Account
              </h2>
              {mobileAccountLinks(identity.isAdmin === true).map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className={row}
                  {...currentProps(link.href)}
                  onClick={requestClose}
                >
                  <RowIcon icon={ROW_ICONS[link.href]} />
                  {link.label}
                </Link>
              ))}
            </nav>
            <div className={styles.bottom}>
              <LogOutRow />
            </div>
          </>
        ) : (
          <div className={`${styles.bottom} ${styles.auth}`}>
            <Link
              href={`/login${returnTo}`}
              className={`${row} ${styles.signIn}`}
              onClick={requestClose}
            >
              <RowIcon icon={LogIn} />
              Sign in
            </Link>
            <Link
              href={`/signup${returnTo}`}
              className={`${row} ${styles.signUp}`}
              onClick={requestClose}
            >
              <RowIcon icon={UserPlus} />
              Sign up
            </Link>
          </div>
        )}
      </div>
    </dialog>
  );
}
