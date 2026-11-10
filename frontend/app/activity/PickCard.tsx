import Link from "next/link";
import { Sparkles } from "lucide-react";
import TrailPhoto from "@/components/TrailPhoto";
import type { FeedPick } from "@/lib/activity";
import styles from "./activity.module.css";

/**
 * A "Trekly pick" between posts while the feed is quiet: a trail suggestion
 * from the catalogue, never anyone's post. Dashed and tinted, with no
 * author, avatar or high five, and labeled as a pick for screen readers too.
 */
export default function PickCard({ pick }: { pick: FeedPick }) {
  const { trail } = pick;
  return (
    <li className={styles.pickItem}>
      <Link href={`/trails?id=${encodeURIComponent(trail.id)}`} className={styles.pick}>
        <span className={styles.pickThumb}>
          <TrailPhoto photo={trail.photo} routeMap={trail.route_map} name={trail.name} variant="thumb" mini />
        </span>
        <span className={styles.pickText}>
          <span className={styles.pickEyebrow}>
            <Sparkles size={13} aria-hidden="true" />
            Trekly pick · {pick.title}
          </span>
          <span className={styles.pickTrail}>{trail.name}</span>
          <span className={styles.pickBody}>{pick.text}</span>
        </span>
      </Link>
    </li>
  );
}
