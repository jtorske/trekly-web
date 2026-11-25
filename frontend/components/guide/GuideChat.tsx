"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import {
  MAX_MESSAGE_CHARS,
  STARTER_PROMPTS,
  clearHistory,
  loadHistory,
  requestTurns,
  saveHistory,
  shownTrailIds,
  type ChatCard,
  type ChatTurn,
  type ReadinessCardData,
} from "@/lib/guideChat";
import { sendChat } from "@/lib/guideChatApi";
import { trailHref } from "@/lib/site";
import { GuideSays, LinkedText, ResultCard, Typing, YouSaid } from "./GuidePlanner";
import styles from "./GuidePlanner.module.css";
import chat from "./GuideChat.module.css";

const VERDICT_CLASS: Record<ReadinessCardData["verdict"], string> = {
  ready: chat.ready,
  stretch: chat.stretch,
  not_yet: chat.notYet,
};

function ReadinessMini({ card }: { card: ReadinessCardData }) {
  const reasons = card.reasons.filter((r) => r.level !== "info").slice(0, 3);
  return (
    <li className={`${chat.readiness} ${styles.enter}`}>
      <div className={chat.readinessHead}>
        <span className={`${chat.verdict} ${VERDICT_CLASS[card.verdict]}`}>{card.label}</span>
        <Link href={trailHref({ slug: card.slug, id: card.slug })} className={styles.cardLink}>
          <strong>{card.name}</strong>
        </Link>
      </div>
      {card.est_label && <p className={styles.cardMeta}>About {card.est_label} of moving time for you</p>}
      {reasons.length > 0 && (
        <ul className={styles.reasons}>
          {reasons.map((r) => (
            <li key={r.text}>
              <LinkedText text={r.text} />
            </li>
          ))}
        </ul>
      )}
      {card.build_up.length > 0 && (
        <p className={styles.cardMeta}>
          Build up first:{" "}
          {card.build_up.map((t, i) => (
            <span key={t.slug}>
              {i > 0 && ", "}
              <Link href={trailHref({ slug: t.slug, id: t.slug })} className={styles.inlineLink}>
                {t.name}
              </Link>
            </span>
          ))}
        </p>
      )}
    </li>
  );
}

function Cards({ cards, returnTo }: { cards: ChatCard[]; returnTo: string }) {
  if (cards.length === 0) return null;
  return (
    <ul className={styles.cards} aria-label="Trails from Trekly Guide">
      {cards.map((card, index) =>
        card.type === "readiness" ? (
          <ReadinessMini key={`r-${card.slug}-${index}`} card={card} />
        ) : card.trail ? (
          <ResultCard key={`t-${card.trail.id}`} pick={{ ...card, trail: card.trail }} returnTo={returnTo} />
        ) : null,
      )}
    </ul>
  );
}

/**
 * Trekly Guide as a conversation. The model only picks which engine tools
 * to call and writes a short reply; the cards are real Trekly data. If chat
 * stops (kill switch, daily cap, provider trouble) `onFallback` swaps in the
 * guided planner with no error.
 */
export default function GuideChat({
  onClose,
  onFallback,
}: {
  onClose: () => void;
  onFallback: (notice?: string) => void;
}) {
  const pathname = usePathname() ?? "/";
  const inputId = useId();
  const [history, setHistory] = useState<ChatTurn[]>(() => loadHistory());
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => saveHistory(history), [history]);

  useEffect(() => {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ block: "end", behavior: still ? "auto" : "smooth" });
  }, [history.length, sending]);

  const send = async (text: string, base: ChatTurn[] = history) => {
    const message = text.trim().slice(0, MAX_MESSAGE_CHARS);
    if (!message || sending) return;
    const next: ChatTurn[] = [...base, { role: "user", content: message }];
    setHistory(next);
    setDraft("");
    setError(null);
    setSending(true);
    try {
      const reply = await sendChat({ messages: requestTurns(next), shown_trail_ids: shownTrailIds(next) });
      setRemaining(reply.remaining_today);
      if (reply.mode === "fallback_to_form") {
        onFallback(reply.text || undefined);
        return;
      }
      setHistory([
        ...next,
        { role: "assistant", content: reply.text, cards: reply.cards, quickReplies: reply.quick_replies },
      ]);
    } catch (caught) {
      // A network or server error: keep their message so they can retry.
      setError(caught instanceof Error ? caught.message : "That didn't go through.");
    } finally {
      setSending(false);
      inputRef.current?.focus({ preventScroll: true });
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(draft);
  };

  const restart = () => {
    clearHistory();
    setHistory([]);
    setError(null);
  };

  const last = history[history.length - 1];
  const chips = sending ? [] : history.length === 0 ? STARTER_PROMPTS : last?.role === "assistant" ? (last.quickReplies ?? []) : [];

  const footer = (
    <div className={styles.composer}>
      {chips.length > 0 && (
        <div className={styles.chips} role="group" aria-label="Suggested replies">
          {chips.map((chip) => (
            <button key={chip} type="button" className={styles.chip} onClick={() => void send(chip)}>
              {chip}
            </button>
          ))}
        </div>
      )}
      <form className={chat.form} onSubmit={submit}>
        <label htmlFor={inputId} className={ui.srOnly}>
          Message Trekly Guide
        </label>
        <textarea
          id={inputId}
          ref={inputRef}
          className={`${ui.input} ${chat.input}`}
          rows={1}
          maxLength={MAX_MESSAGE_CHARS}
          placeholder="Ask about trails, trips or gear"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(draft);
            }
          }}
          data-autofocus
        />
        <button type="submit" className={ui.primary} disabled={sending || !draft.trim()}>
          Send
        </button>
      </form>
      <div className={chat.meta}>
        <span>
          {remaining !== null ? `${remaining} messages left today. ` : ""}
          Don&apos;t share personal details. Chats aren&apos;t saved by Trekly.
        </span>
        {history.length > 0 && (
          <button type="button" className={styles.linkButton} onClick={restart}>
            New chat
          </button>
        )}
      </div>
    </div>
  );

  return (
    <Dialog title="Trekly Guide" subtitle="Ask about trails, trips and gear" onClose={onClose} sheet size="md" footer={footer}>
      <div className={styles.planner}>
        <div className={styles.log} role="log" aria-live="polite" aria-label="Conversation with Trekly Guide">
          <GuideSays>
            Hi! Tell me what you&apos;re after, like &ldquo;an easy hike near Canmore this weekend&rdquo; or
            &ldquo;am I ready for Iceline?&rdquo;. I use your Trail Journal unless it&apos;s off in Settings.
          </GuideSays>
          {history.map((turn, index) =>
            turn.role === "user" ? (
              <YouSaid key={index}>{turn.content}</YouSaid>
            ) : (
              <div key={index} className={styles.pair}>
                <GuideSays>
                  <LinkedText text={turn.content} />
                </GuideSays>
                <Cards cards={turn.cards ?? []} returnTo={pathname} />
              </div>
            ),
          )}
          {sending && <Typing />}
          {error && (
            <GuideSays>
              <span className={styles.error}>{error}</span>{" "}
              <button
                type="button"
                className={styles.linkButton}
                onClick={() => {
                  const lastUser = history[history.length - 1];
                  if (lastUser?.role !== "user") return;
                  void send(lastUser.content, history.slice(0, -1));
                }}
              >
                Try again
              </button>
            </GuideSays>
          )}
          <div ref={endRef} />
        </div>
      </div>
    </Dialog>
  );
}
