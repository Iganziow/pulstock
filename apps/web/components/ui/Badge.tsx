import { C } from "@/lib/theme";

export type BadgeColor = "green" | "orange" | "gray" | "amber";

export function Badge({ color, children }: { color: BadgeColor; children: React.ReactNode }) {
  const m: Record<BadgeColor, { bg: string; bd: string; c: string }> = {
    green:  { bg: C.greenBg, bd: C.greenBd, c: C.green },
    orange: { bg: C.redBg,   bd: C.redBd,   c: C.red },
    gray:   { bg: "#F4F4F5", bd: C.border,  c: C.mid },
    amber:  { bg: C.amberBg, bd: C.amberBd, c: C.amber },
  };
  const s = m[color];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "3px 9px", borderRadius: 99, fontSize: 11, fontWeight: 600,
      letterSpacing: "0.02em", border: `1px solid ${s.bd}`, background: s.bg, color: s.c,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: s.c, flexShrink: 0 }} />
      {children}
    </span>
  );
}
