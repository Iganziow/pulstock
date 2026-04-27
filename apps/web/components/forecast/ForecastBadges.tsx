"use client";

import { C } from "@/lib/theme";

export function Pill({ color, children }: { color: "red" | "amber" | "green" | "gray" | "accent"; children: React.ReactNode }) {
  const m: Record<string, { bg: string; bd: string; fg: string }> = {
    red: { bg: C.redBg, bd: C.redBd, fg: C.red },
    amber: { bg: C.amberBg, bd: C.amberBd, fg: C.amber },
    green: { bg: C.greenBg, bd: C.greenBd, fg: C.green },
    accent: { bg: C.accentBg, bd: C.accentBd, fg: C.accent },
    gray: { bg: C.bg, bd: "#D4D4D8", fg: C.mid },
  };
  const c = m[color] || m.gray;
  return <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 99, background: c.bg, border: `1px solid ${c.bd}`, color: c.fg, whiteSpace: "nowrap" }}>{children}</span>;
}

export function ForecastStatusBadge({ days }: { days: number | null }) {
  if (days === null) return <Pill color="green">Bien</Pill>;
  if (days === 0) return <Pill color="red">Sin stock</Pill>;
  if (days <= 3) return <Pill color="red">{days} día{days > 1 ? "s" : ""}</Pill>;
  if (days <= 7) return <Pill color="amber">{days} días</Pill>;
  if (days <= 14) return <Pill color="accent">{days} días</Pill>;
  return <Pill color="green">Bien</Pill>;
}

export function UrgencyBar({ days, style: s }: { days: number | null; style?: React.CSSProperties }) {
  let pct = 100;
  let color: string = C.green;
  if (days !== null) {
    if (days === 0) { pct = 100; color = C.red; }
    else if (days <= 3) { pct = 90; color = C.red; }
    else if (days <= 7) { pct = 60; color = C.amber; }
    else if (days <= 14) { pct = 35; color = C.accent; }
    else { pct = 10; color = C.green; }
  } else { pct = 5; }
  return (
    <div style={{ height: 4, borderRadius: 2, background: C.border, overflow: "hidden", width: "100%", ...s }}>
      <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 2, transition: "width .3s" }} />
    </div>
  );
}
