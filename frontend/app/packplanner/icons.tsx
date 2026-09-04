export function TrailMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 120 84"
      fill="none"
      stroke="currentColor"
      aria-hidden="true"
    >
      <path
        d="M4 68 L30 24 L44 46 L58 14 L78 68"
        strokeWidth="2.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <path d="M46 68h58" strokeWidth="2.2" strokeLinecap="round" />
      <path
        d="M64 68v-19l11-9 11 9v19"
        strokeWidth="2.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <path d="M75 40v10" strokeWidth="2.2" strokeLinecap="round" />
      <path
        d="M92 30c0 8-6 14-6 14s-6-6-6-14a6 6 0 0 1 12 0Z"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <circle cx="86" cy="30" r="1.6" fill="currentColor" stroke="none" />
      <path
        d="M8 76c4-2 8-2 12 0s8 2 12 0 8-2 12 0 8 2 12 0 8-2 12 0 8 2 12 0 8-2 12 0"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity="0.55"
      />
    </svg>
  );
}
