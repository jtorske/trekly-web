"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Flag, Pencil, Reply, Trash2 } from "lucide-react";
import AccountBadge from "@/components/AccountBadge";
import Avatar from "@/components/Avatar";
import MoreMenu, { type MoreMenuItem } from "@/components/MoreMenu";
import ReportDialog from "@/components/ReportDialog";
import ReviewNotice from "@/components/ReviewNotice";
import ui from "@/components/ui.module.css";
import {
  COMMENT_LIMIT,
  cleanComment,
  commentDeleteKey,
  replyPrefix,
  shortAgo,
  viewAllLabel,
  type ActivityComment,
  type ActivityPost,
} from "@/lib/activity";
import { addComment, deleteComment, editComment, getComments } from "@/lib/activityApi";
import { ApiError } from "@/lib/api";
import { publicProfilePath } from "@/lib/profilesApi";
import { displayName } from "@/lib/publicProfile";
import { toast } from "@/lib/toast";
import { removeWithUndo } from "@/lib/undo";
import { useHidden } from "@/lib/useHidden";
import styles from "./activity.module.css";

type PostPatch = (change: Partial<ActivityPost>) => void;

/**
 * A post's comments: the newest two under it, then "View all N comments",
 * which opens the whole list and the comment box right there (on the post's
 * own page they're open from the start). Replies sit under the comment they answer, one level
 * deep. Text is plain: line breaks stay, links aren't links.
 */
export default function Comments({
  post,
  signedIn,
  signInHref,
  open,
  onOpen,
  onPost,
  focusKey,
}: {
  post: ActivityPost;
  signedIn: boolean;
  signInHref: string;
  /** Show every comment (the post's own page, or after "View all"). */
  open: boolean;
  onOpen: () => void;
  /** Changes to the post's count, preview or comments_off. */
  onPost: PostPatch;
  /** Bumped to move focus into the comment box (the footer's comment count). */
  focusKey?: number;
}) {
  const [list, setList] = useState<ActivityComment[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [replyTo, setReplyTo] = useState<ActivityComment | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [reporting, setReporting] = useState<ActivityComment | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const section = useRef<HTMLElement>(null);
  const boxId = useId();
  const isHidden = useHidden();
  const count = post.comment_count ?? 0;

  useEffect(() => {
    if (!open || list) return;
    const controller = new AbortController();
    getComments(post.id, signedIn, controller.signal)
      .then((data) => {
        setList(data.comments);
        onPost({ comment_count: data.count, comments_off: data.comments_off, can_comment: data.can_comment });
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setLoadFailed(true);
      });
    return () => controller.abort();
    // onPost changes every render; loading once per open is the point.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, list, post.id, signedIn]);

  useEffect(() => {
    // Into the box, or (no box: a guest, comments off) onto the comments themselves.
    if (focusKey) (box.current ?? section.current)?.focus();
  }, [focusKey]);

  const shown = (open && list ? list : (post.comments ?? [])).filter((c) => !isHidden(commentDeleteKey(c.id)));
  const more = open ? null : viewAllLabel(count, (post.comments ?? []).length);

  const startReply = (comment: ActivityComment) => {
    setReplyTo(comment);
    setText((current) => replyPrefix(comment.author.username, current));
    setProblem(null);
    requestAnimationFrame(() => {
      const el = box.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const body = cleanComment(text);
    if (!body) return;
    if (body.length > COMMENT_LIMIT) {
      setProblem(`Keep it under ${COMMENT_LIMIT} characters.`);
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const made = await addComment(post.id, body, replyTo?.id ?? null);
      setText("");
      setReplyTo(null);
      if (list) setList(insertComment(list, made));
      const preview = [...(post.comments ?? []), made].slice(-2);
      // A held comment counts for nobody else; it's still shown to its author.
      onPost({ comments: preview, comment_count: count + (made.review ? 0 : 1) });
      if (made.review) toast.info("Your comment is being reviewed. Only you can see it for now.");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status < 500) setProblem(caught.message);
      else toast.failure("post your comment", caught);
    } finally {
      setBusy(false);
    }
  };

  const remove = (comment: ActivityComment) => {
    const replies = (list ?? []).filter((c) => c.parent_id === comment.id).length;
    removeWithUndo({
      key: commentDeleteKey(comment.id),
      message: comment.mine ? "Comment deleted." : `Deleted ${displayName(comment.author)}'s comment.`,
      commit: () => deleteComment(comment.id),
      what: "delete the comment",
      onCommitted: () => {
        setList((current) => current && current.filter((c) => c.id !== comment.id && c.parent_id !== comment.id));
        onPost({
          comments: (post.comments ?? []).filter((c) => c.id !== comment.id && c.parent_id !== comment.id),
          comment_count: Math.max(0, count - 1 - replies),
        });
      },
    });
  };

  const replace = (updated: ActivityComment) => {
    setList((current) => current && current.map((c) => (c.id === updated.id ? updated : c)));
    onPost({ comments: (post.comments ?? []).map((c) => (c.id === updated.id ? updated : c)) });
  };

  const canWrite = Boolean(signedIn && post.can_comment && !post.comments_off);
  const replyName = replyTo ? displayName(replyTo.author) : null;

  // Closed (a feed card), only the preview shows; the box comes with "Comment" or "View all".
  if (!open && shown.length === 0) return null;

  return (
    <section ref={section} tabIndex={-1} className={styles.comments} aria-label={`Comments on ${displayName(post.author)}'s post`}>
      {shown.length > 0 && (
        <ul className={styles.commentList}>
          {shown.map((comment) => (
            <CommentRow
              key={comment.id}
              comment={comment}
              nested={open && comment.parent_id !== null}
              canReply={canWrite}
              signedIn={signedIn}
              onReply={() => startReply(comment)}
              onDelete={() => remove(comment)}
              onReport={() => setReporting(comment)}
              onEdited={replace}
            />
          ))}
        </ul>
      )}
      {more && (
        <button type="button" className={styles.viewAll} onClick={onOpen}>
          {more}
        </button>
      )}
      {open && !list && !loadFailed && count > shown.length && <p className={styles.commentHint}>Loading comments…</p>}
      {loadFailed && <p className={ui.error}>The comments didn&apos;t load. Try again in a moment.</p>}

      {!open ? null : post.comments_off ? (
        <p className={styles.commentHint}>Comments are off.</p>
      ) : !signedIn ? (
        <p className={styles.commentHint}>
          <Link href={signInHref} className={styles.inlineLink}>
            Sign in to comment
          </Link>
        </p>
      ) : canWrite ? (
        <form className={styles.commentForm} onSubmit={submit}>
          {replyTo && (
            <p className={styles.replying}>
              Replying to {replyName}{" "}
              <button
                type="button"
                className={styles.linkButton}
                onClick={() => {
                  setReplyTo(null);
                  setText((current) => current.replace(new RegExp(`^@${replyTo.author.username}\\s*`, "i"), ""));
                }}
              >
                Cancel
              </button>
            </p>
          )}
          <label htmlFor={boxId} className={ui.srOnly}>
            {replyTo ? `Reply to ${replyName}` : "Add a comment"}
          </label>
          <div className={styles.commentInputRow}>
            <textarea
              ref={box}
              id={boxId}
              className={styles.commentInput}
              rows={1}
              value={text}
              placeholder={replyTo ? `Reply to ${replyName}…` : "Add a comment…"}
              maxLength={COMMENT_LIMIT + 50}
              onChange={(event) => {
                setText(event.target.value);
                setProblem(null);
              }}
              onKeyDown={(event) => {
                // Enter posts; Shift+Enter starts a new line.
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              aria-describedby={problem ? `${boxId}-problem` : undefined}
              disabled={busy}
            />
            <button type="submit" className={styles.commentPost} disabled={busy || !cleanComment(text)}>
              {busy ? "Posting…" : "Post"}
            </button>
          </div>
          {text.length > COMMENT_LIMIT - 50 && (
            <span className={text.length > COMMENT_LIMIT ? ui.fieldError : ui.hint} aria-live="polite">
              {text.length}/{COMMENT_LIMIT}
            </span>
          )}
          {problem && (
            <span id={`${boxId}-problem`} className={ui.fieldError} role="alert">
              {problem}
            </span>
          )}
        </form>
      ) : null}

      {reporting && (
        <ReportDialog
          username={reporting.author.username}
          name={displayName(reporting.author)}
          commentId={reporting.id}
          onClose={() => setReporting(null)}
        />
      )}
    </section>
  );
}

/** Keeps the thread order: a reply goes after the last reply to its comment. */
function insertComment(list: ActivityComment[], made: ActivityComment): ActivityComment[] {
  if (!made.parent_id) return [...list, made];
  let at = list.findIndex((c) => c.id === made.parent_id);
  if (at < 0) return [...list, made];
  while (at + 1 < list.length && list[at + 1].parent_id === made.parent_id) at += 1;
  return [...list.slice(0, at + 1), made, ...list.slice(at + 1)];
}

function CommentRow({
  comment,
  nested,
  canReply,
  signedIn,
  onReply,
  onDelete,
  onReport,
  onEdited,
}: {
  comment: ActivityComment;
  nested: boolean;
  canReply: boolean;
  signedIn: boolean;
  onReply: () => void;
  onDelete: () => void;
  onReport: () => void;
  onEdited: (comment: ActivityComment) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(comment.body);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const editId = useId();
  const name = displayName(comment.author);
  const href = publicProfilePath(comment.author.username);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const body = cleanComment(draft);
    if (!body || body.length > COMMENT_LIMIT) {
      setProblem(body ? `Keep it under ${COMMENT_LIMIT} characters.` : "Write something, or delete the comment.");
      return;
    }
    setSaving(true);
    try {
      const updated = await editComment(comment.id, body);
      onEdited(updated);
      setEditing(false);
      if (updated.review) toast.info("Your comment is being reviewed. Only you can see it for now.");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status < 500) setProblem(caught.message);
      else toast.failure("save your comment", caught);
    } finally {
      setSaving(false);
    }
  };

  const items: MoreMenuItem[] = [];
  if (comment.mine)
    items.push({
      label: "Edit",
      icon: <Pencil size={15} aria-hidden="true" />,
      onSelect: () => {
        setDraft(comment.body);
        setProblem(null);
        setEditing(true);
      },
    });
  if (comment.can_delete)
    items.push({ label: "Delete", icon: <Trash2 size={15} aria-hidden="true" />, onSelect: onDelete, danger: true });
  if (signedIn && !comment.mine && comment.author.label !== "official")
    items.push({ label: "Report", icon: <Flag size={15} aria-hidden="true" />, onSelect: onReport });

  return (
    <li className={`${styles.comment} ${nested ? styles.commentReply : ""}`}>
      <Link href={href} className={styles.commentAvatar} aria-label={`${name}'s profile`}>
        <Avatar path={comment.author.avatar_path} name={comment.author.display_name ?? comment.author.username} email={null} size={30} />
      </Link>
      <div className={styles.commentMain}>
        <p className={styles.commentHead}>
          <Link href={href} className={styles.commentName}>
            {name}
          </Link>
          <AccountBadge label={comment.author.label} compact />
          <span className={styles.commentMeta}>
            <time dateTime={comment.created_at} title={new Date(comment.created_at).toLocaleString("en-CA")}>
              {shortAgo(comment.created_at)}
            </time>
            {comment.edited_at && (
              <>
                {" · "}
                <span title={`Edited ${new Date(comment.edited_at).toLocaleString("en-CA")}`}>Edited</span>
              </>
            )}
          </span>
        </p>
        {editing ? (
          <form className={styles.commentEdit} onSubmit={save}>
            <label htmlFor={editId} className={ui.srOnly}>
              Edit your comment
            </label>
            <textarea
              id={editId}
              className={styles.commentInput}
              rows={2}
              value={draft}
              autoFocus
              maxLength={COMMENT_LIMIT + 50}
              onChange={(event) => {
                setDraft(event.target.value);
                setProblem(null);
              }}
              onKeyDown={(event) => {
                if (event.key === "Escape") setEditing(false);
              }}
              disabled={saving}
            />
            {problem && (
              <span className={ui.fieldError} role="alert">
                {problem}
              </span>
            )}
            <span className={styles.commentEditActions}>
              <button type="button" className={ui.ghost} onClick={() => setEditing(false)} disabled={saving}>
                Cancel
              </button>
              <button type="submit" className={ui.primary} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </button>
            </span>
          </form>
        ) : (
          <p className={styles.commentBody}>{comment.body}</p>
        )}
        {comment.review && <ReviewNotice state={comment.review} what="comment" />}
        {!editing && (canReply || items.length > 0) && (
          <span className={styles.commentActions}>
            {canReply && !comment.review && (
              <button type="button" className={styles.commentAction} onClick={onReply}>
                <Reply size={14} aria-hidden="true" />
                Reply
              </button>
            )}
            <MoreMenu label={`More for ${name}'s comment`} items={items} size={16} />
          </span>
        )}
      </div>
    </li>
  );
}
