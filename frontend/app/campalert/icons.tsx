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

export function CompassMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 64 64"
      fill="none"
      stroke="currentColor"
      aria-hidden="true"
    >
      <circle cx="32" cy="32" r="27" strokeWidth="1.4" />
      <circle cx="32" cy="32" r="1.8" fill="currentColor" stroke="none" />
      <path d="M32 8v7M32 49v7M8 32h7M49 32h7" strokeWidth="1.4" strokeLinecap="round" />
      <path d="M32 16l6 17-6 15-6-15z" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M32 16l6 17-6-4-6 4z" fill="currentColor" stroke="none" />
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
