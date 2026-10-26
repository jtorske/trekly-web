import type { Metadata } from "next";
import { Caveat } from "next/font/google";
import type { ReactNode } from "react";

// Handwriting for journal notes and polaroid captions; loaded only here.
const hand = Caveat({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-hand", display: "swap" });

export const metadata: Metadata = {
  title: "Trail Journal · Trekly",
  description: "Your private scrapbook of the trails you've hiked.",
};

export default function JournalLayout({ children }: { children: ReactNode }) {
  return <div className={`${hand.variable} flex flex-1 flex-col`}>{children}</div>;
}
