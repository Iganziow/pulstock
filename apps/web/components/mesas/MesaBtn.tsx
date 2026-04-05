"use client";

import { C } from "@/lib/theme";

type MesaBtnVariant = "primary" | "secondary" | "danger" | "ghost";

interface MesaBtnProps {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: MesaBtnVariant;
  disabled?: boolean;
  full?: boolean;
  size?: "sm" | "md" | "lg";
}

export function MesaBtn({ children, onClick, variant = "secondary", disabled, full, size = "md" }: MesaBtnProps) {
  const vs: Record<MesaBtnVariant, React.CSSProperties> = {
    primary:   { background: C.accent, color: "#fff", border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text, border: `1px solid ${C.borderMd}` },
    danger:    { background: C.redBg, color: C.red, border: `1px solid ${C.redBd}` },
    ghost:     { background: "transparent", color: C.mid, border: "1px solid transparent" },
  };
  const pad = size === "sm" ? "5px 10px" : size === "lg" ? "11px 22px" : "8px 16px";
  const fs = size === "sm" ? 12 : size === "lg" ? 15 : 13;
  return (
    <button type="button" onClick={onClick} disabled={disabled} style={{
      ...vs[variant], padding: pad, borderRadius: C.r, fontSize: fs, fontWeight: 600,
      cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
      display: "inline-flex", alignItems: "center", gap: 6,
      width: full ? "100%" : undefined, justifyContent: full ? "center" : undefined,
      transition: "all 0.13s ease", fontFamily: "inherit",
    }}>
      {children}
    </button>
  );
}
