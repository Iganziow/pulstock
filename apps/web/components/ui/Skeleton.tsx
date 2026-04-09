import { C } from "@/lib/theme";

/**
 * Skeleton loading placeholder — replaces Spinners for smoother loading UX.
 * Shimmer animation moves left-to-right to indicate loading.
 */

const shimmerKeyframes = `
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
`;

// Inject keyframes once
if (typeof document !== "undefined" && !document.getElementById("skeleton-css")) {
  const style = document.createElement("style");
  style.id = "skeleton-css";
  style.textContent = shimmerKeyframes;
  document.head.appendChild(style);
}

const shimmerBg = `linear-gradient(90deg, ${C.border}00 0%, ${C.border}80 50%, ${C.border}00 100%)`;

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
}

export function Skeleton({ width = "100%", height = 16, borderRadius = 6, style }: SkeletonProps) {
  return (
    <div style={{
      width, height, borderRadius,
      background: C.bg,
      backgroundImage: shimmerBg,
      backgroundSize: "200% 100%",
      animation: "shimmer 1.5s ease-in-out infinite",
      ...style,
    }} />
  );
}

/** Skeleton row for table/list loading */
export function SkeletonRow({ cols = 4 }: { cols?: number }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 12, padding: "14px 20px", borderBottom: `1px solid ${C.border}` }}>
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton key={i} height={14} width={i === 0 ? "80%" : "60%"} />
      ))}
    </div>
  );
}

/** Skeleton card for dashboard KPIs */
export function SkeletonCard() {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 10, padding: "16px 18px",
      display: "flex", alignItems: "center", gap: 14,
    }}>
      <Skeleton width={40} height={40} borderRadius={10} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
        <Skeleton width="40%" height={10} />
        <Skeleton width="60%" height={22} />
      </div>
    </div>
  );
}

/** Skeleton page — full loading state for a dashboard page */
export function SkeletonPage({ cards = 4, rows = 6 }: { cards?: number; rows?: number }) {
  return (
    <div style={{ display: "grid", gap: 16, padding: "28px 32px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <Skeleton width={180} height={24} />
          <Skeleton width={120} height={12} />
        </div>
        <Skeleton width={120} height={38} borderRadius={8} />
      </div>

      {/* Stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(160px, 1fr))`, gap: 10 }}>
        {Array.from({ length: cards }).map((_, i) => <SkeletonCard key={i} />)}
      </div>

      {/* Table */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", background: C.bg, borderBottom: `1px solid ${C.border}`, display: "flex", gap: 12 }}>
          <Skeleton width={200} height={32} borderRadius={8} />
          <Skeleton width={80} height={32} borderRadius={8} />
        </div>
        {Array.from({ length: rows }).map((_, i) => <SkeletonRow key={i} />)}
      </div>
    </div>
  );
}
