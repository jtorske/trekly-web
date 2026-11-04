"use client";

import { Flame } from "lucide-react";
import { streakAnimated } from "@/lib/useStreak";
import styles from "./StreakFlame.module.css";

/**
 * The visit streak's flame. With `grew` it plays a small flicker once
 * (a colour fade with reduced motion), then clears the flag so no other
 * flame repeats it. Decorative: the text beside it says the streak.
 */
export default function StreakFlame({ size, grew = false, className = "" }: { size: number; grew?: boolean; className?: string }) {
  return (
    <Flame
      size={size}
      aria-hidden="true"
      className={`${styles.flame} ${grew ? styles.grew : ""} ${className}`}
      onAnimationEnd={grew ? streakAnimated : undefined}
    />
  );
}
