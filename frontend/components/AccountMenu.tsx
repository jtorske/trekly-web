"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Backpack, Bell, BookOpen, LogOut, Settings, Shield, Tent, type LucideIcon } from "lucide-react";
import { useAuth } from "./AuthProvider";
import Avatar from "./Avatar";
import RankEmblem from "./RankEmblem";
import StreakFlame from "./StreakFlame";
import { useRank } from "@/lib/useRank";
import { useStreak } from "@/lib/useStreak";
import { showsStreak, streakLabel } from "@/lib/visitStreak";
import { ADMIN_LINK, PROFILE_HREF, accountLinks, currentAccountHref } from "@/lib/accountMenu";
import ui from "./ui.module.css";
import styles from "./AccountMenu.module.css";

/** Decorative icons for the account rows, keyed by href; the labels name them. */
export const ROW_ICONS: Record<string, LucideIcon> = {
  "/journal": BookOpen,
  "/gear": Backpack,
  "/profile?tab=trips": Tent,
  "/alerts": Bell,
  "/settings": Settings,
  [ADMIN_LINK.href]: Shield,
};

export function RowIcon({ icon: Icon }: { icon: LucideIcon | undefined }) {
  return Icon ? <Icon className={styles.icon} size={18} aria-hidden="true" /> : null;
}

export interface AccountIdentity {
  displayName: string | null;
  email: string | null;
  avatarPath: string | null | undefined;
  /** From the profile's is_admin; adds the Admin row. */
  isAdmin?: boolean;
}

type ItemProps = { role?: "menuitem"; tabIndex?: -1 };

/** The header row: avatar, name, rank, visit streak and "Show profile"; opens the profile. */
export function ProfileRow({
  identity,
  current,
  item = {},
  onChoose,
}: {
  identity: AccountIdentity;
  current: boolean;
  item?: ItemProps;
  onChoose: () => void;
}) {
  const { rank } = useRank();
  const { streak, grew } = useStreak();
  const name = identity.displayName || identity.email || "Your account";
  return (
    <Link href={PROFILE_HREF} className={`${styles.row} ${styles.profileRow}`} {...item} aria-current={current ? "page" : undefined} onClick={onChoose}>
      <Avatar path={identity.avatarPath} name={identity.displayName} email={identity.email} size={40} />
      <span className={styles.profileText}>
        <span className={styles.name} title={name}>
          {name}
        </span>
        {(rank || showsStreak(streak)) && (
          <span className={styles.rank}>
            {rank && (
              <span className={styles.rankName}>
                <RankEmblem level={rank.rank.level} className={styles.rankEmblem} />
                {rank.rank.title}
              </span>
            )}
            {showsStreak(streak) && (
              <span className={styles.streak} title={streakLabel(streak.current)}>
                <StreakFlame size={14} grew={grew} />
                {streak.current}
                <span className={ui.srOnly}>-day streak</span>
              </span>
            )}
          </span>
        )}
        <span className={styles.showProfile}>Show profile</span>
      </span>
      <span className={styles.chevron} aria-hidden="true">
        ›
      </span>
    </Link>
  );
}

/** Log out: signs out and goes to the landing page. */
export function LogOutRow({ item = {}, className = "" }: { item?: ItemProps; className?: string }) {
  const { signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);
  return (
    <button
      type="button"
      className={`${styles.row} ${className}`}
      {...item}
      disabled={signingOut}
      onClick={() => {
        setSigningOut(true);
        void signOut("/landing");
      }}
    >
      <RowIcon icon={LogOut} />
      {signingOut ? "Logging out…" : "Log out"}
    </button>
  );
}

/**
 * The avatar dropdown's rows: the profile header row, the account pages and
 * Log out. The mobile menu (MobileMenu.tsx) builds its groups from the same
 * pieces.
 */
export function AccountRows({
  identity,
  current,
  onChoose,
}: {
  identity: AccountIdentity;
  /** href of the row for the current page, from currentAccountHref. */
  current: string | null;
  onChoose: () => void;
}) {
  const item = { role: "menuitem", tabIndex: -1 } as const;
  const currentProps = (href: string) => (current === href ? { "aria-current": "page" as const } : {});

  return (
    <>
      <ProfileRow identity={identity} current={current === PROFILE_HREF} item={item} onChoose={onChoose} />
      {accountLinks(identity.isAdmin === true).map((link) =>
        link.href.startsWith("mailto:") ? (
          <a key={link.href} href={link.href} className={styles.row} {...item} onClick={onChoose}>
            <RowIcon icon={ROW_ICONS[link.href]} />
            {link.label}
          </a>
        ) : (
          <Link key={link.href} href={link.href} className={styles.row} {...item} {...currentProps(link.href)} onClick={onChoose}>
            <RowIcon icon={ROW_ICONS[link.href]} />
            {link.label}
          </Link>
        ),
      )}
      <LogOutRow item={item} />
    </>
  );
}

/**
 * The avatar button and its dropdown. Follows the WAI-ARIA menu button
 * pattern: Enter, Space or Down opens on the first item, Up on the last;
 * arrows, Home and End move; Escape or choosing an item closes and returns
 * focus to the avatar; Tab or a click outside just closes.
 */
export default function AccountMenu({
  identity,
  triggerClassName,
}: {
  identity: AccountIdentity;
  triggerClassName: string;
}) {
  const pathname = usePathname();
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [focusOnOpen, setFocusOnOpen] = useState<"first" | "last">("first");
  // The query string at the time of opening; the menu closes on navigation.
  const [search, setSearch] = useState("");

  const items = () => Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);

  const openMenu = (focus: "first" | "last") => {
    setSearch(window.location.search);
    setFocusOnOpen(focus);
    setOpen(true);
  };

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  };

  useEffect(() => {
    if (!open) return;
    const list = items();
    (focusOnOpen === "first" ? list[0] : list[list.length - 1])?.focus();

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !triggerRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open, focusOnOpen]);

  // Close if the route changes underneath (e.g. browser back).
  useEffect(() => {
    queueMicrotask(() => setOpen(false));
  }, [pathname]);

  const onTriggerKeyDown = (event: KeyboardEvent) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openMenu(event.key === "ArrowDown" ? "first" : "last");
    }
  };

  const onMenuKeyDown = (event: KeyboardEvent) => {
    const list = items();
    const index = list.indexOf(document.activeElement as HTMLElement);
    const move = (next: number) => {
      event.preventDefault();
      list[(next + list.length) % list.length]?.focus();
    };
    if (event.key === "ArrowDown") move(index + 1);
    else if (event.key === "ArrowUp") move(index - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(list.length - 1);
    else if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "Tab") close(false);
  };

  const accountLabel = `Account menu${identity.displayName ? ` for ${identity.displayName}` : ""}`;

  return (
    <div className={styles.wrapper}>
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.trigger} ${triggerClassName}`}
        aria-label={accountLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        title="Your account"
        onClick={() => (open ? close(false) : openMenu("first"))}
        onKeyDown={onTriggerKeyDown}
      >
        <Avatar path={identity.avatarPath} name={identity.displayName} email={identity.email} size={34} />
      </button>

      {open && (
        <div ref={menuRef} id={menuId} role="menu" aria-label={accountLabel} className={`${styles.card} ${styles.menu}`} onKeyDown={onMenuKeyDown}>
          <AccountRows identity={identity} current={currentAccountHref(pathname, search)} onChoose={() => close(true)} />
        </div>
      )}
    </div>
  );
}
