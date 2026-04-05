/**
 * Pulstock logo — shield with heartbeat pulse.
 * Gradient: #4F8EF5 (blue) → #7C3AED (violet)
 */
export function LogoIcon({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="shield-grad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#4F8EF5" />
          <stop offset="100%" stopColor="#7C3AED" />
        </linearGradient>
      </defs>
      {/* Shield shape */}
      <path
        d="M24 4 L42 12 C42 12 44 30 24 44 C4 30 6 12 6 12 Z"
        fill="url(#shield-grad)"
      />
      {/* Heartbeat / pulse line */}
      <polyline
        points="10,26 17,26 20,18 24,34 28,22 31,26 38,26"
        fill="none"
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function LogoFull({ height = 32 }: { height?: number }) {
  const iconSize = height;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <LogoIcon size={iconSize} />
      <span style={{
        fontSize: height * 0.56,
        fontWeight: 800,
        background: "linear-gradient(135deg, #4F8EF5, #7C3AED)",
        WebkitBackgroundClip: "text",
        WebkitTextFillColor: "transparent",
      }}>Pulstock</span>
    </div>
  );
}
