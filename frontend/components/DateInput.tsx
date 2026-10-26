"use client";

import { useState, type InputHTMLAttributes } from "react";
import { isPlainDate } from "@/lib/stay";

/**
 * A date field that only reports complete YYYY-MM-DD dates within `min` and
 * `max`. While someone types, the browser reports in-between values (year
 * 0002, a 6-digit year) and doesn't enforce the bounds; those stay in the field without
 * reaching `onChange`, and leaving the field puts back the last good date so
 * what's shown is what's used.
 */
export default function DateInput({
  value,
  onChange,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange"> & {
  value: string;
  onChange: (value: string) => void;
}) {
  const [typing, setTyping] = useState<string | null>(null);
  return (
    <input
      {...props}
      type="date"
      value={typing ?? value}
      onChange={(event) => {
        const next = event.target.value;
        const tooEarly = typeof props.min === "string" && next < props.min;
        const tooLate = typeof props.max === "string" && next > props.max;
        if (isPlainDate(next) && !tooEarly && !tooLate) {
          setTyping(null);
          onChange(next);
        } else {
          setTyping(next);
        }
      }}
      onBlur={(event) => {
        setTyping(null);
        props.onBlur?.(event);
      }}
    />
  );
}
