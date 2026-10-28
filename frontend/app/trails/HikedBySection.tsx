"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Flag } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import HikePhoto from "@/components/HikePhoto";
import ReportDialog from "@/components/ReportDialog";
import ui from "@/components/ui.module.css";
import { othersLabel, shortenNote, type CommunityHiker, type CommunityNote, type TrailHikers } from "@/lib/hikedBy";
import { getTrailHikers } from "@/lib/hikedByApi";
import { publicProfilePath } from "@/lib/profilesApi";
import { displayName, formatHikeDate } from "@/lib/publicProfile";
import { useProfile } from "@/lib/useProfile";
import styles from "./HikedBySection.module.css";

/**
 * "Hiked by": opted-in hikers who logged this trail, newest first, and up
 * to three of their trip notes. The API decides who appears; the section
 * stays hidden until it has someone to show.
 */
export default function HikedBySection({
  trailId,
  trailName,
  refreshKey,
  className,
}: {
  trailId: string;
  trailName: string;
  /** Changes when the viewer logs, edits or removes their own hike here. */
  refreshKey: string;
  className?: string;
}) {
  const [data, setData] = useState<{ trailId: string; hikers: TrailHikers } | null>(null);
  const [reporting, setReporting] = useState<CommunityNote | null>(null);
  const { user } = useAuth();
  const { profile: me } = useProfile();

  useEffect(() => {
    const controller = new AbortController();
    getTrailHikers(trailId, controller.signal)
      .then((hikers) => setData({ trailId, hikers }))
      // A side section: if it fails, the page simply goes without it.
      .catch(() => undefined);
    return () => controller.abort();
  }, [trailId, refreshKey]);

  const hikers = data?.trailId === trailId ? data.hikers : null;
  if (!hikers || hikers.hikers.length === 0) return null;

  const others = othersLabel(hikers.others);
  // Reporting needs an account, and nobody reports themselves.
  const canReport = (note: CommunityNote) => Boolean(user) && note.username !== me?.username;

  return (
    <section className={className} aria-labelledby="hiked-by-title">
      <h2 id="hiked-by-title" className={styles.title}>
        Hiked by
      </h2>
      <div className={styles.hikers}>
        <ul className={styles.avatars}>
          {hikers.hikers.map((hiker) => (
            <li key={hiker.username}>
              <HikerAvatar hiker={hiker} size={44} className={styles.avatarLink} />
            </li>
          ))}
        </ul>
        {others && <span className={styles.others}>{others}</span>}
      </div>

      {hikers.notes.length > 0 && (
        <>
          <h3 className={styles.notesTitle}>Trip notes</h3>
          <ul className={styles.notes}>
            {hikers.notes.map((note) => (
              <TripNote
                key={note.username}
                note={note}
                trailName={trailName}
                onReport={canReport(note) ? () => setReporting(note) : undefined}
              />
            ))}
          </ul>
        </>
      )}

      {reporting && (
        <ReportDialog
          username={reporting.username}
          name={displayName(reporting)}
          trailId={trailId}
          onClose={() => setReporting(null)}
        />
      )}
    </section>
  );
}

function HikerAvatar({ hiker, size, className }: { hiker: CommunityHiker; size: number; className: string }) {
  const name = displayName(hiker);
  return (
    <Link
      href={publicProfilePath(hiker.username)}
      className={className}
      aria-label={hiker.display_name ? `${name} (@${hiker.username})` : name}
      title={name}
    >
      <Avatar path={hiker.avatar_path} name={hiker.display_name ?? hiker.username} email={null} size={size} />
    </Link>
  );
}

function TripNote({ note, trailName, onReport }: { note: CommunityNote; trailName: string; onReport?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const short = shortenNote(note.note);
  const id = `trip-note-${note.username}`;

  return (
    <li className={styles.note}>
      <div className={styles.noteHeader}>
        <HikerAvatar hiker={note} size={36} className={styles.noteAvatar} />
        <div className={styles.noteWho}>
          <Link href={publicProfilePath(note.username)} className={styles.noteName}>
            {displayName(note)}
          </Link>
          {(note.display_name || note.hiked_on) && (
            <span className={styles.noteMeta}>
              {/* Without a display name, the name above is already the @username. */}
              {note.display_name && <span>@{note.username}</span>}
              {note.hiked_on && <time dateTime={note.hiked_on}>{formatHikeDate(note.hiked_on)}</time>}
            </span>
          )}
        </div>
        {onReport && (
          <button
            type="button"
            className={`${ui.ghost} ${styles.report}`}
            onClick={onReport}
            aria-label={`Report ${displayName(note)}'s trip note`}
          >
            <Flag size={14} aria-hidden="true" />
            Report
          </button>
        )}
      </div>
      <div className={styles.noteBody}>
        <div className={styles.noteText}>
          <p id={id}>{short && !expanded ? short : note.note}</p>
          {short && (
            <button
              type="button"
              className={styles.readMore}
              aria-expanded={expanded}
              aria-controls={id}
              onClick={() => setExpanded((open) => !open)}
            >
              {expanded ? "Show less" : "Read more"}
            </button>
          )}
        </div>
        {note.photo_path && (
          <HikePhoto
            path={note.photo_path}
            alt={`${displayName(note)}'s photo from ${trailName}`}
            className={styles.notePhoto}
          />
        )}
      </div>
    </li>
  );
}
