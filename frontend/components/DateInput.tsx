"use client";

import { useState, type InputHTMLAttributes } from "react";
import { isPlainDate } from "@/lib/stay";

/**
 * A date field that only reports complete YYYY-MM-DD dates on or after `min`.
 * While someone types, the browser reports in-between values (year 0002, a
 * 6-digit year) and doesn't enforce `min`; those stay in the field without
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
        if (isPlainDate(next) && !(typeof props.min === "string" && next < props.min)) {
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
