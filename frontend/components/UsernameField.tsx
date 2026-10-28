"use client";

import { useEffect, useRef, useState } from "react";
import { checkUsername, suggestUsername } from "@/lib/accountApi";
import { formatProblem, normalizeUsername, type UsernameStatus } from "@/lib/usernames";
import ui from "./ui.module.css";
import styles from "./UsernameField.module.css";

const CHECK_DELAY_MS = 300;
const SUGGEST_DELAY_MS = 400;

/**
 * Live availability for a username as it's typed: the format is checked
 * here, everything else (taken, reserved) by the API. "unchecked" means the
 * API couldn't be reached; the save itself is checked again server-side.
 */
export function useUsernameStatus(value: string, current?: string | null): UsernameStatus {
  const name = normalizeUsername(value);
  const problem = formatProblem(name);
  // The API would call the account's own username taken, so don't ask about it.
  const isCurrent = Boolean(current) && name === current;
  const [result, setResult] = useState<{ name: string; status: UsernameStatus } | null>(null);

  useEffect(() => {
    if (problem || isCurrent) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      checkUsername(name, controller.signal)
        .then((check) =>
          setResult({ name, status: { state: check.available ? "available" : "taken", message: check.message } }),
        )
        .catch((error: unknown) => {
          if ((error as { name?: string }).name === "AbortError") return;
          setResult({
            name,
            status: { state: "unchecked", message: "Couldn't check availability right now. We'll check when you continue." },
          });
        });
    }, CHECK_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [name, problem, isCurrent]);

  if (problem) return { state: name ? "invalid" : "empty", message: problem };
  if (isCurrent) return { state: "current", message: "This is your username." };
  if (result?.name === name) return result.status;
  return { state: "checking", message: "Checking availability…" };
}

/**
 * The username input: "@" prefix, live availability message, and a
 * pre-filled suggestion from `suggestFrom` (a display name or email) until
 * the person edits it themselves.
 */
export default function UsernameField({
  id,
  value,
  onChange,
  status,
  suggestFrom,
  showError,
  autoFocus,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  status: UsernameStatus;
  suggestFrom: string;
  /** Show "empty"/"invalid" as errors (after a submit attempt, or once typed in). */
  showError: boolean;
  autoFocus?: boolean;
}) {
  const [edited, setEdited] = useState(false);
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const hint = suggestFrom.trim();
    if (edited || !hint) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      suggestUsername(hint, controller.signal)
        .then((suggestion) => onChangeRef.current(suggestion.username))
        .catch(() => undefined); // No suggestion; they can still type one.
    }, SUGGEST_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [suggestFrom, edited]);

  const isError =
    status.state === "taken" || ((status.state === "invalid" || status.state === "empty") && (showError || edited));
  const messageId = `${id}-status`;
  const messageClass =
    status.state === "available" ? styles.available : isError ? ui.fieldError : ui.hint;

  return (
    <label className={ui.field} htmlFor={id}>
      <span className={ui.label}>Username</span>
      <span className={styles.inputWrap}>
        <span className={styles.at} aria-hidden="true">
          @
        </span>
        <input
          id={id}
          className={`${ui.input} ${styles.input}`}
          value={value}
          onChange={(event) => {
            setEdited(true);
            onChange(event.target.value.toLowerCase());
          }}
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={30}
          required
          autoFocus={autoFocus}
          aria-invalid={isError}
          aria-describedby={messageId}
        />
      </span>
      <span id={messageId} className={messageClass} aria-live="polite">
        {status.state === "available" && <span aria-hidden="true">✓ </span>}
        {status.state === "empty" && !isError ? "3–30 lowercase letters, numbers or underscores." : status.message}
      </span>
    </label>
  );
}
