"use client";

import { STATUS_MAP } from "./helpers";

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS_MAP[status] || STATUS_MAP.inactive;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "3px 9px", borderRadius: 99, fontSize: 11, fontWeight: 600,
      letterSpacing: "0.02em", border: `1px solid ${s.bd}`, background: s.bg, color: s.c,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: s.c, flexShrink: 0 }} />
      {s.label}
    </span>
  );
}
