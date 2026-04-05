import { C } from "@/lib/theme";

export type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "success" | "amber" | "teal" | "sky" | "violet";
export type BtnSize = "sm" | "md" | "lg";

export function Btn({ children, onClick, variant = "secondary", disabled, size = "md", full }: {
  children: React.ReactNode; onClick?: () => void;
  variant?: BtnVariant; disabled?: boolean; size?: BtnSize; full?: boolean;
}) {
  const vs: Record<BtnVariant, React.CSSProperties> = {
    primary:   { background: C.accent,  color: "#fff",  border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text,  border: `1px solid ${C.borderMd}` },
    ghost:     { background: "transparent", color: C.mid, border: "1px solid transparent" },
    danger:    { background: C.redBg,   color: C.red,   border: `1px solid ${C.redBd}` },
    success:   { background: C.greenBg, color: C.green, border: `1px solid ${C.greenBd}` },
    amber:     { background: C.amberBg, color: C.amber, border: `1px solid ${C.amberBd}` },
    teal:      { background: C.tealBg,  color: C.teal,  border: `1px solid ${C.tealBd}` },
    sky:       { background: C.skyBg,   color: C.sky,   border: `1px solid ${C.skyBd}` },
    violet:    { background: "#F5F3FF", color: "#7C3AED", border: "1px solid #DDD6FE" },
  };
  const h = size === "lg" ? 46 : size === "sm" ? 32 : 38;
  const px = size === "lg" ? "0 20px" : size === "sm" ? "0 12px" : "0 16px";
  const fs = size === "lg" ? 15 : size === "sm" ? 12 : 13;
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="xb" style={{
      ...vs[variant], display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
      height: h, padding: px, width: full ? "100%" : undefined,
      borderRadius: C.r, fontSize: fs, fontWeight: 600,
      letterSpacing: "0.01em", whiteSpace: "nowrap",
    }}>
      {children}
    </button>
  );
}
