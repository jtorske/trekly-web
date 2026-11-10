/**
 * Accounts that aren't ordinary hikers (backend app/account_labels.py):
 * "official" is the Trekly team's own @trekly account, "demo" a made-up demo
 * hiker. The API puts the label on every author it returns, and the badge
 * shows wherever the name does, so neither can pass for a real hiker.
 */
export type AccountLabel = "official" | "demo";

export const ACCOUNT_BADGE_TEXT: Record<AccountLabel, string> = {
  official: "Trekly team",
  demo: "Demo account",
};

export const ACCOUNT_BADGE_HINT: Record<AccountLabel, string> = {
  official: "The official Trekly account, run by the Trekly team.",
  demo: "A made-up hiker that shows what Trekly looks like. Not a real person.",
};

/** The badge's words, or null for an ordinary account. */
export function accountBadge(label: AccountLabel | null | undefined): string | null {
  return label ? ACCOUNT_BADGE_TEXT[label] ?? null : null;
}

/** A name inside a sentence ("Maya (Demo account) high-fived this"), where a badge can't go. */
export function labeledName(name: string, label: AccountLabel | null | undefined): string {
  const badge = accountBadge(label);
  return badge ? `${name} (${badge})` : name;
}
