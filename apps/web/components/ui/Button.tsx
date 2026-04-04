import { C } from "@/lib/theme";

export type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "success";

export function Btn({ children, onClick, variant = "secondary", disabled, size = "md" }: {
  children: React.ReactNode; onClick?: () => void;
  variant?: BtnVariant; disabled?: boolean; size?: "sm" | "md";
}) {
  const vs: Record<BtnVariant, React.CSSProperties> = {
    primary:   { background: C.accent,  color: "#fff",  border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text,  border: `1px solid ${C.borderMd}` },
    ghost:     { background: "transparent", color: C.mid, border: "1px solid transparent" },
    danger:    { background: C.redBg,   color: C.red,   border: `1px solid ${C.redBd}` },
    success:   { background: C.greenBg, color: C.green, border: `1px solid ${C.greenBd}` },
  };
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="xb" style={{
      ...vs[variant], display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
      height: size === "sm" ? 32 : 38, padding: size === "sm" ? "0 12px" : "0 16px",
      borderRadius: C.r, fontSize: size === "sm" ? 12 : 13, fontWeight: 600,
      letterSpacing: "0.01em", whiteSpace: "nowrap",
    }}>
      {children}
    </button>
  );
}
