"use client";

import DateInput from "@/components/DateInput";
import ui from "@/components/ui.module.css";
import { MAX_NIGHTS, MAX_PARTY, type Stay } from "@/lib/availabilityApi";
import styles from "./AlertDialogs.module.css";

/** First night, nights and people: the stay an alert watches. */
export default function StayFields({
  stay,
  today,
  onChange,
}: {
  stay: Stay;
  today: string;
  onChange: (stay: Stay) => void;
}) {
  return (
    <div className={styles.stayFields}>
      <label className={`${ui.field} ${styles.startField}`}>
        <span className={ui.label}>First night</span>
        <DateInput
          className={ui.input}
          value={stay.start}
          min={today}
          required
          onChange={(start) => onChange({ ...stay, start })}
        />
      </label>
      <label className={ui.field}>
        <span className={ui.label}>Nights</span>
        <select
          className={ui.input}
          value={stay.nights}
          onChange={(event) => onChange({ ...stay, nights: Number(event.target.value) })}
        >
          {Array.from({ length: MAX_NIGHTS }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <label className={ui.field}>
        <span className={ui.label}>People</span>
        <select
          className={ui.input}
          value={stay.party}
          onChange={(event) => onChange({ ...stay, party: Number(event.target.value) })}
        >
          {Array.from({ length: MAX_PARTY }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
