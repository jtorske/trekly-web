"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { CalendarClock, Check, ExternalLink, Pencil, Plus, Send, Trash2, X } from "lucide-react";
import ui from "@/components/ui.module.css";
import PostCard from "@/app/activity/PostCard";
import type { ActivityPost } from "@/lib/activity";
import { formatSourceDate } from "@/lib/activity";
import {
  treklyPostsApi,
  type TreklyDraft,
  type TreklyFact,
  type TreklyPostTypeInfo,
  type TreklyQueue,
  type TreklyQueueFilter,
} from "@/lib/adminApi";
import { toast } from "@/lib/toast";
import type { TrailListItem } from "@/lib/trailsApi";
import AdminFrame from "../AdminFrame";
import ConfirmDialog from "../ConfirmDialog";
import TrailPicker from "../TrailPicker";
import { useAdminData } from "../useAdminData";
import styles from "../admin.module.css";
import page from "./page.module.css";

const MAX_BODY = 500;
const MAX_FACT = 400;
const DAY_NAMES: Record<string, string> = {
  mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun",
};
const FILTERS: { value: TreklyQueueFilter; label: string }[] = [
  { value: "waiting", label: "Waiting" },
  { value: "published", label: "Published" },
  { value: "closed", label: "Rejected and expired" },
];
const WRITER_LABELS = { template: "Template", ai: "AI wording (fact-checked)", admin: "Edited by an admin" };
const STATUS_LABELS = {
  draft: "Draft",
  scheduled: "Approved",
  published: "Published",
  rejected: "Rejected",
  expired: "Expired",
};

function schedule(days: string[]): string {
  if (days.length === 7) return "Every day";
  return days.map((day) => DAY_NAMES[day] ?? day).join(", ");
}

function failure(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

/** The draft as it would look in the feed: the real post card, with nothing to click but the trail. */
function Preview({ draft, account }: { draft: TreklyDraft; account: NonNullable<TreklyQueue["account"]> }) {
  const post: ActivityPost = {
    id: draft.id,
    kind: "announcement",
    author: {
      username: account.username,
      display_name: account.display_name,
      avatar_path: account.avatar_path,
      label: "official",
      follow: null,
    },
    posted_at: draft.published_at,
    hike: null,
    announcement: {
      body: draft.body,
      trail: draft.trail,
      photo_url: null,
      source_url: draft.source_url,
      source_label: draft.source_label,
      source_date: draft.source_date,
    },
    milestone: null,
    rank: null,
    earned: [],
    high_fives: 0,
    high_fived: false,
    mine: false,
    // Hides the high five and report actions: this is only a preview.
    only_you: true,
  };
  return (
    <ul className={page.preview} aria-label="Preview">
      <PostCard post={post} signedIn={false} viewer={null} signInHref="/login" onChange={() => undefined} />
    </ul>
  );
}

function DraftItem({
  draft,
  account,
  today,
  onChanged,
}: {
  draft: TreklyDraft;
  account: NonNullable<TreklyQueue["account"]>;
  today: string;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(draft.body);
  const [day, setDay] = useState(draft.publish_on ?? today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"publish" | "reject" | null>(null);
  const bodyId = useId();
  const dayId = useId();
  const open = draft.status === "draft" || draft.status === "scheduled";
  const editable = open && draft.post_type !== "conditions";
  const length = body.trim().length;

  const act = async (work: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setError(null);
    try {
      await work();
      toast.success(done);
      setEditing(false);
      onChanged();
    } catch (caught) {
      setError(failure(caught, "That didn't work. Try again."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className={page.draft}>
      <div className={page.draftHead}>
        <span className={styles.pills}>
          <span className={draft.status === "scheduled" ? styles.pillDark : styles.pill}>
            {STATUS_LABELS[draft.status]}
            {draft.status === "scheduled" && draft.publish_on && <> for {formatSourceDate(draft.publish_on)}</>}
          </span>
          <span className={styles.pill}>{WRITER_LABELS[draft.writer]}</span>
        </span>
        <span className={styles.muted}>Drafted {formatSourceDate(draft.run_date)}</span>
      </div>

      {editing ? (
        <div className={page.editor}>
          <label htmlFor={bodyId} className={page.label}>
            Post text
          </label>
          <textarea
            id={bodyId}
            className={`${ui.input} ${page.body}`}
            rows={4}
            value={body}
            maxLength={MAX_BODY + 50}
            onChange={(event) => setBody(event.target.value)}
            aria-describedby={`${bodyId}-count`}
          />
          <p id={`${bodyId}-count`} className={`${page.count} ${length > MAX_BODY ? page.over : ""}`}>
            {length} / {MAX_BODY}
          </p>
          <details className={page.template}>
            <summary>The template&apos;s text</summary>
            <p>{draft.template_body}</p>
          </details>
          <div className={page.actions}>
            <button
              type="button"
              className={ui.primary}
              disabled={busy || length === 0 || length > MAX_BODY}
              onClick={() => void act(() => treklyPostsApi.edit(draft.id, body.trim()), "Draft saved.")}
            >
              <Check size={16} aria-hidden="true" /> Save
            </button>
            <button
              type="button"
              className={ui.secondary}
              disabled={busy}
              onClick={() => {
                setBody(draft.body);
                setEditing(false);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <Preview draft={draft} account={account} />
      )}

      {draft.ai_note && <p className={page.note}>{draft.ai_note}</p>}
      {draft.writer === "ai" && !editing && (
        <details className={page.template}>
          <summary>The template&apos;s text</summary>
          <p>{draft.template_body}</p>
        </details>
      )}
      {draft.post_type === "conditions" && open && (
        <p className={page.note}>
          Quoted word for word from the official bulletin, so it can&apos;t be edited. Check the{" "}
          {draft.source_url ? (
            <a href={draft.source_url} target="_blank" rel="noopener noreferrer">
              bulletin <ExternalLink size={12} aria-hidden="true" />
            </a>
          ) : (
            "bulletin"
          )}{" "}
          is still current before publishing.
        </p>
      )}
      {open && draft.blocked && <p className={page.blocked}>Can&apos;t publish now: {draft.blocked}</p>}

      {open && !editing && (
        <div className={page.actions}>
          <span className={page.scheduleField}>
            <label htmlFor={dayId} className={ui.srOnly}>
              Publish on
            </label>
            <input
              id={dayId}
              type="date"
              className={ui.input}
              value={day}
              min={today}
              onChange={(event) => setDay(event.target.value)}
            />
            <button
              type="button"
              className={ui.secondary}
              disabled={busy || !day}
              onClick={() =>
                void act(
                  () => treklyPostsApi.schedule(draft.id, day),
                  `Approved for ${formatSourceDate(day)}: it goes out with that day's run.`,
                )
              }
            >
              <CalendarClock size={16} aria-hidden="true" /> {draft.status === "scheduled" ? "Reschedule" : "Approve for"}
            </button>
          </span>
          <button type="button" className={ui.primary} disabled={busy || !!draft.blocked} onClick={() => setConfirm("publish")}>
            <Send size={16} aria-hidden="true" /> Publish now
          </button>
          {editable && (
            <button type="button" className={ui.secondary} disabled={busy} onClick={() => setEditing(true)}>
              <Pencil size={16} aria-hidden="true" /> Edit
            </button>
          )}
          {draft.status === "scheduled" && (
            <button
              type="button"
              className={ui.ghost}
              disabled={busy}
              onClick={() => void act(() => treklyPostsApi.schedule(draft.id, null), "Back to drafts.")}
            >
              Unapprove
            </button>
          )}
          <button type="button" className={ui.ghost} disabled={busy} onClick={() => setConfirm("reject")}>
            <X size={16} aria-hidden="true" /> Reject
          </button>
        </div>
      )}
      {error && (
        <p className={ui.error} role="alert">
          {error}
        </p>
      )}

      {confirm === "publish" && (
        <ConfirmDialog
          confirmation={{
            title: "Publish this post now?",
            body: "It goes straight to everyone's Activity feed and @trekly's profile. That uses today's @trekly post.",
            confirm: "Publish now",
            reason: false,
            danger: false,
          }}
          onConfirm={async () => {
            await treklyPostsApi.publish(draft.id);
            toast.success("Published as @trekly.");
            onChanged();
          }}
          onClose={() => setConfirm(null)}
        />
      )}
      {confirm === "reject" && (
        <ConfirmDialog
          confirmation={{
            title: "Reject this draft?",
            body: "It won't be posted. The generator won't draft the same thing again.",
            confirm: "Reject",
            reason: false,
            danger: true,
          }}
          onConfirm={async () => {
            await treklyPostsApi.reject(draft.id);
            onChanged();
          }}
          onClose={() => setConfirm(null)}
        />
      )}
    </li>
  );
}

function TypeRow({ type, onChanged }: { type: TreklyPostTypeInfo; onChanged: () => void }) {
  const id = useId();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const set = async (on: boolean) => {
    setBusy(true);
    try {
      await treklyPostsApi.setAutoPublish(type.post_type, on);
      toast.success(on ? `${type.label} posts now publish on their own.` : `${type.label} drafts now wait for review.`);
      onChanged();
    } catch (caught) {
      toast.failure("change auto-publish", caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className={page.type}>
      <label htmlFor={id} className={page.typeText}>
        <span className={page.typeName}>{type.label}</span>
        <span className={styles.muted}>
          {type.enabled ? schedule(type.days) : "Off in the config"}
          {type.ai && " · AI wording"}
        </span>
      </label>
      <span className={page.typeSwitch}>
        <span className={styles.muted} aria-hidden="true">
          {type.auto_publish_locked ? "Always reviewed" : "Auto-publish"}
        </span>
        <input
          id={id}
          type="checkbox"
          role="switch"
          className={page.switch}
          checked={type.auto_publish}
          disabled={busy || (type.auto_publish_locked && !type.auto_publish)}
          aria-label={
            type.auto_publish_locked
              ? `${type.label}: always reviewed before publishing`
              : `Auto-publish ${type.label}`
          }
          onChange={(event) => {
            if (event.target.checked) setConfirming(true);
            else void set(false);
          }}
        />
      </span>
      {confirming && (
        <ConfirmDialog
          confirmation={{
            title: `Auto-publish ${type.label.toLowerCase()}?`,
            body:
              type.post_type === "conditions"
                ? "Official bulletins will go out without anyone checking them first. They're quoted word for word, but you won't see them before hikers do."
                : "The daily run will publish these drafts without review (still at most one @trekly post a day). You can still edit or reject them while they wait.",
            confirm: "Turn on auto-publish",
            reason: false,
            danger: false,
          }}
          onConfirm={() => set(true)}
          onClose={() => setConfirming(false)}
        />
      )}
    </li>
  );
}

function FactForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial?: TreklyFact;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const [text, setText] = useState(initial?.text ?? "");
  const [url, setUrl] = useState(initial?.source_url ?? "");
  const [park, setPark] = useState(initial?.park_name ?? "");
  const [trail, setTrail] = useState<TrailListItem | null>(initial?.trail ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textId = useId();
  const urlId = useId();
  const parkId = useId();
  const length = text.trim().length;

  const save = async () => {
    setBusy(true);
    setError(null);
    const fact = { text: text.trim(), source_url: url.trim(), park_name: park.trim() || null, trail_id: trail?.id ?? null };
    try {
      if (initial) await treklyPostsApi.updateFact(initial.id, fact);
      else await treklyPostsApi.createFact(fact);
      toast.success(initial ? "Fact saved. Approve it again to use it." : "Fact added, waiting for approval.");
      if (!initial) {
        setText("");
        setUrl("");
        setPark("");
        setTrail(null);
      }
      onSaved();
    } catch (caught) {
      setError(failure(caught, "That didn't save. Try again."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className={page.factForm}
      onSubmit={(event) => {
        event.preventDefault();
        if (length > 0 && length <= MAX_FACT && url.trim() && !busy) void save();
      }}
    >
      <label htmlFor={textId} className={page.label}>
        Fact
      </label>
      <textarea
        id={textId}
        className={`${ui.input} ${page.body}`}
        rows={3}
        value={text}
        maxLength={MAX_FACT + 50}
        placeholder="One or two sentences, as they'll be posted."
        onChange={(event) => setText(event.target.value)}
      />
      <p className={`${page.count} ${length > MAX_FACT ? page.over : ""}`}>
        {length} / {MAX_FACT}
      </p>
      <label htmlFor={urlId} className={page.label}>
        Source link
      </label>
      <input
        id={urlId}
        className={ui.input}
        type="url"
        inputMode="url"
        placeholder="https://parks.canada.ca/…"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
      />
      <label htmlFor={parkId} className={page.label}>
        Park (optional)
      </label>
      <input id={parkId} className={ui.input} value={park} onChange={(event) => setPark(event.target.value)} />
      <TrailPicker trail={trail} onChange={setTrail} label="Trail (optional)" />
      {error && (
        <p className={ui.error} role="alert">
          {error}
        </p>
      )}
      <div className={page.actions}>
        <button type="submit" className={ui.primary} disabled={busy || length === 0 || length > MAX_FACT || !url.trim()}>
          {initial ? (
            <>
              <Check size={16} aria-hidden="true" /> Save
            </>
          ) : (
            <>
              <Plus size={16} aria-hidden="true" /> Add fact
            </>
          )}
        </button>
        {onCancel && (
          <button type="button" className={ui.secondary} onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

function FactItem({ fact, onChanged }: { fact: TreklyFact; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState(false);

  const approve = async (approved: boolean) => {
    setBusy(true);
    try {
      await treklyPostsApi.updateFact(fact.id, { approved });
      onChanged();
    } catch (caught) {
      toast.failure(approved ? "approve the fact" : "unapprove the fact", caught);
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <li className={page.fact}>
        <FactForm
          initial={fact}
          onSaved={() => {
            setEditing(false);
            onChanged();
          }}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }
  return (
    <li className={page.fact}>
      <p className={page.factText}>{fact.text}</p>
      <p className={styles.muted}>
        {[fact.trail?.name, fact.park_name].filter(Boolean).join(" · ") || "No trail or park"}
        {" · "}
        <a href={fact.source_url} target="_blank" rel="noopener noreferrer" className={page.factSource}>
          {new URL(fact.source_url).hostname.replace(/^www\./, "")}
          <ExternalLink size={12} aria-hidden="true" />
          <span className={ui.srOnly}> (opens in a new tab)</span>
        </a>
      </p>
      <div className={page.actions}>
        {fact.approved ? (
          <>
            <span className={styles.pillDark}>Approved</span>
            <button type="button" className={ui.ghost} disabled={busy} onClick={() => void approve(false)}>
              Unapprove
            </button>
          </>
        ) : (
          <>
            <span className={styles.pillWarn}>Needs review</span>
            <button type="button" className={ui.secondary} disabled={busy} onClick={() => void approve(true)}>
              <Check size={16} aria-hidden="true" /> Approve
            </button>
          </>
        )}
        <button type="button" className={ui.ghost} onClick={() => setEditing(true)}>
          <Pencil size={16} aria-hidden="true" /> Edit
        </button>
        <button type="button" className={ui.ghost} onClick={() => setDeleting(true)} aria-label="Delete this fact">
          <Trash2 size={16} aria-hidden="true" />
        </button>
      </div>
      {deleting && (
        <ConfirmDialog
          confirmation={{
            title: "Delete this fact?",
            body: "It leaves the fact bank. Posts already published with it stay.",
            confirm: "Delete fact",
            reason: false,
            danger: true,
          }}
          onConfirm={async () => {
            await treklyPostsApi.removeFact(fact.id);
            onChanged();
          }}
          onClose={() => setDeleting(false)}
        />
      )}
    </li>
  );
}

function FactBank() {
  const { state, reload } = useAdminData("trekly-facts", (signal) => treklyPostsApi.facts(signal));
  const [adding, setAdding] = useState(false);
  const facts = state.data;
  const waiting = facts?.filter((fact) => !fact.approved).length ?? 0;

  return (
    <section className={styles.card} aria-labelledby="fact-bank">
      <div className={styles.cardHead}>
        <h2 id="fact-bank" className={styles.cardTitle}>
          Fact bank
        </h2>
        {!adding && (
          <button type="button" className={ui.secondary} onClick={() => setAdding(true)}>
            <Plus size={16} aria-hidden="true" /> New fact
          </button>
        )}
      </div>
      <p className={`${styles.muted} ${page.intro}`}>
        Fun fact posts use approved facts only, word for word, each linking its source. Changing a fact&apos;s text or
        link un-approves it.
        {facts && ` ${facts.length - waiting} approved, ${waiting} waiting for review.`}
      </p>
      {adding && (
        <FactForm
          onSaved={() => {
            setAdding(false);
            reload();
          }}
          onCancel={() => setAdding(false)}
        />
      )}
      {!facts ? (
        state.status === "error" ? (
          <p className={ui.error} role="alert">
            {state.message}
          </p>
        ) : (
          <div className={`${ui.skeleton} ${page.skeleton}`} aria-busy="true" aria-label="Loading facts" />
        )
      ) : facts.length === 0 ? (
        <p className={styles.muted}>No facts yet.</p>
      ) : (
        <ul className={page.facts}>
          {facts.map((fact) => (
            <FactItem key={`${fact.id}:${fact.updated_at}`} fact={fact} onChanged={reload} />
          ))}
        </ul>
      )}
    </section>
  );
}

function QueueBody() {
  const [filter, setFilter] = useState<TreklyQueueFilter>("waiting");
  const { state, reload } = useAdminData(`trekly-queue:${filter}`, (signal) => treklyPostsApi.queue(filter, signal));
  const data = state.data;

  if (!data) {
    if (state.status === "error") return <p className={ui.error} role="alert">{state.message}</p>;
    return <div className={`${ui.skeleton} ${styles.gateSkeleton}`} aria-busy="true" aria-label="Loading" />;
  }
  const waiting = data.counts.draft + data.counts.scheduled;
  const counts: Record<TreklyQueueFilter, number> = {
    waiting,
    published: data.counts.published,
    closed: data.counts.rejected + data.counts.expired,
  };

  return (
    <>
      <section className={styles.card} aria-labelledby="queue-status">
        <h2 id="queue-status" className={styles.cardTitle}>
          Today
        </h2>
        <p className={page.status}>
          @trekly has posted {data.posts_today} of {data.max_posts_per_day} today ({formatSourceDate(data.today)}).
          {data.busy && " Hikers have been busy posting, so the daily run will skip today."}
        </p>
        <p className={styles.muted}>
          A run each morning drafts new posts from real trail data and publishes one: an approved draft first, else
          one of a type that auto-publishes. A post whose AI wording fails the fact check is skipped, never posted.
          When TREKLY_POSTS_DIGEST_TO is set, it emails a record of what went out. To write a post yourself, use{" "}
          <Link href="/admin/posts">Write a post</Link>.
        </p>
        {!data.account && (
          <p className={page.blocked}>
            The Trekly account isn&apos;t set up yet, so nothing can be published (run{" "}
            <code>python -m scripts.official_account</code> in <code>backend/</code>).
          </p>
        )}
      </section>

      <section className={styles.card} aria-labelledby="queue-types">
        <h2 id="queue-types" className={styles.cardTitle}>
          Post types
        </h2>
        <p className={styles.muted}>Schedules and auto-publish defaults live in backend/config/trekly_posts.toml: fun facts and conditions wait
          for review here, the rest publish on their own. The switches override the defaults.</p>
        <ul className={page.types}>
          {data.types.map((type) => (
            <TypeRow key={type.post_type} type={type} onChanged={reload} />
          ))}
        </ul>
      </section>

      <section className={styles.card} aria-labelledby="queue-drafts">
        <div className={styles.cardHead}>
          <h2 id="queue-drafts" className={styles.cardTitle}>
            Drafts
          </h2>
          <div className={`${ui.segmented} ${styles.filters}`} role="group" aria-label="Show">
            {FILTERS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={filter === option.value}
                onClick={() => setFilter(option.value)}
              >
                {option.label} ({counts[option.value]})
              </button>
            ))}
          </div>
        </div>
        {data.drafts.length === 0 ? (
          <p className={styles.muted}>
            {filter === "waiting" ? "Nothing waiting. The next run drafts more." : "Nothing here."}
          </p>
        ) : (
          <ul className={page.drafts}>
            {data.drafts.map((draft) => (
              <DraftItem
                key={`${draft.id}:${draft.status}:${draft.publish_on}:${draft.body}`}
                draft={draft}
                account={data.account ?? { username: "trekly", display_name: "Trekly", avatar_path: null }}
                today={data.today}
                onChanged={reload}
              />
            ))}
          </ul>
        )}
      </section>

      <FactBank />
    </>
  );
}

export default function TreklyPostsQueuePage() {
  return (
    <AdminFrame title="Post queue">
      <QueueBody />
    </AdminFrame>
  );
}
