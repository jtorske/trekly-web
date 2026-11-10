"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { ImagePlus, Search, Trash2, X } from "lucide-react";
import AccountBadge from "@/components/AccountBadge";
import Avatar from "@/components/Avatar";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { officialPostsApi, type OfficialPhoto, type OfficialPost } from "@/lib/adminApi";
import { shortAgo } from "@/lib/activity";
import { PHOTO_ACCEPT, PHOTO_HINT, PREPARING_PHOTO, photoProblemMessage } from "@/lib/photoPrep";
import { preparePhoto, TRAIL_PHOTO_EDGE } from "@/lib/preparePhoto";
import { toast } from "@/lib/toast";
import { searchTrails, type TrailListItem } from "@/lib/trailsApi";
import AdminFrame from "../AdminFrame";
import ConfirmDialog from "../ConfirmDialog";
import { useAdminData } from "../useAdminData";
import styles from "../admin.module.css";
import page from "./page.module.css";

const MAX_BODY = 500;

/** Pick a trail by name; one at a time. */
function TrailPicker({ trail, onChange }: { trail: TrailListItem | null; onChange: (t: TrailListItem | null) => void }) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ query: string; trails: TrailListItem[] } | null>(null);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchTrails(term, controller.signal, { limit: 6 })
        .then((trails) => setResults({ query: term, trails }))
        .catch(() => undefined);
    }, 200);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query]);

  if (trail) {
    return (
      <div className={page.chosenTrail}>
        <span className={page.trailThumb}>
          <TrailPhoto photo={trail.photo} routeMap={trail.route_map} name={trail.name} variant="thumb" mini />
        </span>
        <span className={page.trailName}>
          {trail.name}
          <span className={styles.muted}> · {trail.park_name ?? trail.region}</span>
        </span>
        <button type="button" className={ui.ghost} onClick={() => onChange(null)} aria-label={`Remove ${trail.name}`}>
          <X size={16} aria-hidden="true" />
        </button>
      </div>
    );
  }
  const shown = results && results.query === query.trim() ? results.trails : [];
  return (
    <div className={page.picker}>
      <label htmlFor={id} className={ui.srOnly}>
        Link a trail (optional)
      </label>
      <span className={page.searchBox}>
        <Search size={16} aria-hidden="true" />
        <input
          id={id}
          className={ui.input}
          type="search"
          placeholder="Link a trail (optional)"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
        />
      </span>
      {shown.length > 0 && (
        <ul className={page.results}>
          {shown.map((option) => (
            <li key={option.id}>
              <button
                type="button"
                className={page.result}
                onClick={() => {
                  onChange(option);
                  setQuery("");
                }}
              >
                <span className={page.trailThumb}>
                  <TrailPhoto photo={option.photo} routeMap={option.route_map} name={option.name} variant="thumb" mini />
                </span>
                <span>
                  {option.name}
                  <span className={styles.muted}> · {option.park_name ?? option.region}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Composer({ onPosted }: { onPosted: () => void }) {
  const [body, setBody] = useState("");
  const [trail, setTrail] = useState<TrailListItem | null>(null);
  const [photo, setPhoto] = useState<OfficialPhoto | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const bodyId = useId();
  const length = body.trim().length;

  const pick = async (picked: File | undefined) => {
    if (!picked) return;
    setError(null);
    setPreparing(true);
    try {
      const file = await preparePhoto(picked, { maxEdge: TRAIL_PHOTO_EDGE, quality: 0.92 });
      const uploaded = await officialPostsApi.uploadPhoto(file);
      if (photo) void officialPostsApi.discardPhoto(photo.photo_path).catch(() => undefined);
      setPhoto(uploaded);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : photoProblemMessage(caught));
    } finally {
      setPreparing(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const dropPhoto = () => {
    if (photo) void officialPostsApi.discardPhoto(photo.photo_path).catch(() => undefined);
    setPhoto(null);
  };

  const post = async () => {
    setBusy(true);
    setError(null);
    try {
      await officialPostsApi.create({ body: body.trim(), trail_id: trail?.id ?? null, photo_path: photo?.photo_path ?? null });
      setBody("");
      setTrail(null);
      setPhoto(null);
      toast.success("Posted to the Activity feed as @trekly.");
      onPosted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That didn't post. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className={page.composer}
      onSubmit={(event) => {
        event.preventDefault();
        if (length > 0 && length <= MAX_BODY && !busy && !preparing) void post();
      }}
    >
      <label htmlFor={bodyId} className={page.label}>
        Post
      </label>
      <textarea
        id={bodyId}
        className={`${ui.input} ${page.body}`}
        rows={4}
        maxLength={MAX_BODY + 50}
        placeholder="A new feature, a featured trail, a seasonal tip…"
        value={body}
        onChange={(event) => setBody(event.target.value)}
        aria-describedby={`${bodyId}-count`}
      />
      <p id={`${bodyId}-count`} className={`${page.count} ${length > MAX_BODY ? page.over : ""}`}>
        {length} / {MAX_BODY}
      </p>

      <TrailPicker trail={trail} onChange={setTrail} />

      {photo ? (
        <div className={page.photoPreview}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={photo.photo_url} alt="The post's photo" />
          <button type="button" className={ui.secondary} onClick={dropPhoto}>
            <X size={16} aria-hidden="true" /> Remove photo
          </button>
        </div>
      ) : (
        <div className={page.photoRow}>
          <button
            type="button"
            className={ui.secondary}
            onClick={() => fileRef.current?.click()}
            disabled={preparing}
            aria-busy={preparing || undefined}
          >
            <ImagePlus size={16} aria-hidden="true" /> {preparing ? PREPARING_PHOTO : "Add a photo"}
          </button>
          <span className={styles.muted}>Optional. {PHOTO_HINT}. With a linked trail and no photo, the trail&apos;s photo shows.</span>
          <input
            ref={fileRef}
            type="file"
            accept={PHOTO_ACCEPT}
            className={ui.srOnly}
            tabIndex={-1}
            onChange={(event) => void pick(event.target.files?.[0])}
          />
        </div>
      )}

      {error && (
        <p className={ui.error} role="alert">
          {error}
        </p>
      )}
      <div className={page.submitRow}>
        <button type="submit" className={ui.primary} disabled={busy || preparing || length === 0 || length > MAX_BODY}>
          {busy ? "Posting…" : "Post as @trekly"}
        </button>
      </div>
    </form>
  );
}

function PostRow({ post, onDelete }: { post: OfficialPost; onDelete: () => void }) {
  return (
    <li className={page.post}>
      <div className={page.postText}>
        <p className={page.postBody}>{post.body}</p>
        <p className={styles.muted}>
          <time dateTime={post.created_at} title={new Date(post.created_at).toLocaleString("en-CA")}>
            {shortAgo(post.created_at)}
          </time>
          {post.trail && <> · {post.trail.name}</>}
          {post.photo_url && <> · photo</>}
          {post.hidden && <> · hidden by an admin</>}
        </p>
      </div>
      <button type="button" className={ui.ghost} onClick={onDelete} aria-label="Delete this post">
        <Trash2 size={16} aria-hidden="true" />
      </button>
    </li>
  );
}

function PostsBody() {
  const { state, reload } = useAdminData("official-posts", (signal) => officialPostsApi.list(signal));
  const [deleting, setDeleting] = useState<OfficialPost | null>(null);
  const data = state.data;

  if (!data) {
    if (state.status === "error") return <p className={ui.error} role="alert">{state.message}</p>;
    return <div className={`${ui.skeleton} ${styles.gateSkeleton}`} aria-busy="true" aria-label="Loading" />;
  }
  if (!data.account) {
    return (
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>The Trekly account isn&apos;t set up yet</h2>
        <p className={styles.muted}>
          Run <code>python -m scripts.official_account</code> in <code>backend/</code> to make @trekly, then post from here.
        </p>
      </section>
    );
  }

  return (
    <>
      <section className={styles.card} aria-labelledby="official-compose">
        <div className={page.as}>
          <Avatar path={data.account.avatar_path} name={data.account.display_name ?? "Trekly"} email={null} size={40} />
          <span>
            <span id="official-compose" className={page.asName}>
              Posting as {data.account.display_name ?? "Trekly"} <AccountBadge label="official" compact />
            </span>
            <span className={styles.muted}>
              Shows in everyone&apos;s Activity feed and on{" "}
              <Link href={`/u/${data.account.username}`}>@{data.account.username}</Link>.
            </span>
          </span>
        </div>
        <Composer onPosted={reload} />
      </section>

      <section className={styles.card} aria-labelledby="official-posts">
        <h2 id="official-posts" className={styles.cardTitle}>
          Posted ({data.posts.length})
        </h2>
        {data.posts.length === 0 ? (
          <p className={styles.muted}>Nothing yet.</p>
        ) : (
          <ul className={page.posts}>
            {data.posts.map((post) => (
              <PostRow key={post.id} post={post} onDelete={() => setDeleting(post)} />
            ))}
          </ul>
        )}
      </section>

      {deleting && (
        <ConfirmDialog
          confirmation={{
            title: "Delete this post?",
            body: "It leaves the Activity feed and @trekly's profile for everyone, with its high fives and photo.",
            confirm: "Delete post",
            reason: false,
            danger: true,
          }}
          onConfirm={async () => {
            await officialPostsApi.remove(deleting.id);
            reload();
          }}
          onClose={() => setDeleting(null)}
        />
      )}
    </>
  );
}

export default function AdminPostsPage() {
  return (
    <AdminFrame title="Trekly posts">
      <PostsBody />
    </AdminFrame>
  );
}
