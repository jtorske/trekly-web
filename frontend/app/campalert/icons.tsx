export function SearchIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      aria-hidden="true"
    >
      <circle cx="10.5" cy="10.5" r="6.5" strokeWidth="1.8" />
      <path d="M19 19l-4.3-4.3" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function TrailPinIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      aria-hidden="true"
    >
      <path
        d="M12 21s7-6.3 7-12a7 7 0 1 0-14 0c0 5.7 7 12 7 12Z"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="9" r="2.4" strokeWidth="1.5" />
    </svg>
  );
}

export function CampsiteIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      aria-hidden="true"
    >
      <path d="M4 19 11 5l7 14" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M8.2 19 11 13l2.8 6" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function CheckBadgeIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9.5" strokeWidth="1.6" />
      <path d="M7.5 12.5 10.5 15.5 16.5 9" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
