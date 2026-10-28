"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Backpack, Bell, LogOut, Settings, Tent, type LucideIcon } from "lucide-react";
import { useAuth } from "./AuthProvider";
import Avatar from "./Avatar";
import RankEmblem from "./RankEmblem";
import { useRank } from "@/lib/useRank";
import { ACCOUNT_LINKS, PROFILE_HREF, currentAccountHref } from "@/lib/accountMenu";
import styles from "./AccountMenu.module.css";

/** Decorative icons for the account rows, keyed by href; the labels name them. */
const ROW_ICONS: Record<string, LucideIcon> = {
  "/profile?tab=trips": Tent,
  "/gear": Backpack,
  "/alerts": Bell,
  "/settings": Settings,
};

function RowIcon({ icon: Icon }: { icon: LucideIcon | undefined }) {
  return Icon ? <Icon className={styles.icon} size={18} aria-hidden="true" /> : null;
}

export interface AccountIdentity {
  displayName: string | null;
  email: string | null;
  avatarPath: string | null | undefined;
}

/**
 * The account rows: a profile header row, the account pages, Contact support
 * and Log out. Shared by the avatar dropdown (as menu items) and the mobile
 * menu (as plain links), so both always list the same things.
 */
export function AccountRows({
  identity,
  current,
  asMenuItems,
  onChoose,
}: {
  identity: AccountIdentity;
  /** href of the row for the current page, from currentAccountHref. */
  current: string | null;
  asMenuItems: boolean;
  onChoose: () => void;
}) {
  const { signOut } = useAuth();
  const { rank } = useRank();
  const [signingOut, setSigningOut] = useState(false);
  const item = asMenuItems ? ({ role: "menuitem", tabIndex: -1 } as const) : {};
  const name = identity.displayName || identity.email || "Your account";
  const currentProps = (href: string) => (current === href ? { "aria-current": "page" as const } : {});

  return (
    <>
      <Link href={PROFILE_HREF} className={`${styles.row} ${styles.profileRow}`} {...item} {...currentProps(PROFILE_HREF)} onClick={onChoose}>
        <Avatar path={identity.avatarPath} name={identity.displayName} email={identity.email} size={40} />
        <span className={styles.profileText}>
          <span className={styles.name} title={name}>
            {name}
          </span>
          {rank && (
            <span className={styles.rank}>
              <RankEmblem level={rank.rank.level} className={styles.rankEmblem} />
              {rank.rank.title}
            </span>
          )}
          <span className={styles.showProfile}>Show profile</span>
        </span>
        <span className={styles.chevron} aria-hidden="true">
          ›
        </span>
      </Link>
      {ACCOUNT_LINKS.map((link) =>
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
      <button
        type="button"
        className={styles.row}
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
  onOpen,
}: {
  identity: AccountIdentity;
  triggerClassName: string;
  /** Lets the navbar close its mobile menu when this one opens. */
  onOpen?: () => void;
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
    onOpen?.();
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
          <AccountRows identity={identity} current={currentAccountHref(pathname, search)} asMenuItems onChoose={() => close(true)} />
        </div>
      )}
    </div>
  );
}
