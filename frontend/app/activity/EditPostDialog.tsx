"use client";

import Dialog from "@/components/Dialog";
import HikeLogDialog from "@/components/HikeLogDialog";
import ui from "@/components/ui.module.css";
import type { ActivityPost } from "@/lib/activity";
import { useHikeLogs } from "@/lib/useHikeLogs";

/**
 * "Edit" on your own hike post: the hike's note, photo and date (or "I don't
 * remember"), in the journal's own dialog, saved through the journal's own
 * path, so moderation, badges, points and rank all follow. The trail stays.
 */
export default function EditPostDialog({
  post,
  onSaved,
  onClose,
}: {
  post: ActivityPost;
  /** After a save: reload the post. */
  onSaved: () => Promise<void> | void;
  onClose: () => void;
}) {
  const hikeLogs = useHikeLogs();
  const trail = post.hike?.trail;
  const entry = trail ? (hikeLogs.byTrail.get(trail.id) ?? null) : null;

  if (!trail || hikeLogs.loading || !entry) {
    return (
      <Dialog title="Edit post" subtitle={trail?.name} size="sm" onClose={onClose}>
        {hikeLogs.loading ? (
          <p className={ui.hint} role="status">
            Loading your hike…
          </p>
        ) : (
          <p className={ui.error}>
            {hikeLogs.error ?? "This hike isn't in your Trail Journal any more, so there's nothing to edit."}
          </p>
        )}
      </Dialog>
    );
  }
  return (
    <HikeLogDialog
      post
      trailName={trail.name}
      entry={entry}
      onSave={async (input) => {
        await hikeLogs.save(trail.id, input, "Post updated");
        await onSaved();
      }}
      onClose={onClose}
    />
  );
}
