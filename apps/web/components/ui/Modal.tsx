import { useEffect } from "react";
import { C } from "@/lib/theme";

export function Modal({ onClose, width = 560, accentColor, title, subtitle, footer, children }: {
  onClose: () => void; width?: number; accentColor?: string;
  title: React.ReactNode; subtitle?: React.ReactNode;
  footer: React.ReactNode; children: React.ReactNode;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="bd-in" onClick={onClose} style={{
      position: "fixed", inset: 0, zIndex: 60,
      background: "rgba(12,12,20,0.5)", backdropFilter: "blur(3px)",
      display: "grid", placeItems: "center", padding: 16,
    }}>
      <div className="m-in" onClick={(e) => e.stopPropagation()} style={{
        width: `min(${width}px, 96vw)`,
        background: C.surface, borderRadius: C.rLg,
        border: `1px solid ${C.border}`, boxShadow: C.shLg,
        overflow: "hidden", display: "flex", flexDirection: "column", maxHeight: "92vh",
      }}>
        <div style={{ height: 3, background: accentColor || C.accent, flexShrink: 0 }} />
        <div style={{
          padding: "18px 22px 15px", borderBottom: `1px solid ${C.border}`,
          display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexShrink: 0,
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text, letterSpacing: "-0.01em" }}>{title}</div>
            {subtitle && <div style={{ fontSize: 12, color: C.mute, marginTop: 3 }}>{subtitle}</div>}
          </div>
          <button onClick={onClose} className="ib" aria-label="Cerrar" style={{
            width: 30, height: 30, borderRadius: C.r, border: `1px solid ${C.border}`,
            background: C.surface, color: C.mid, fontSize: 14,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>✕</button>
        </div>
        <div style={{ padding: "20px 22px", overflowY: "auto", flex: 1 }}>{children}</div>
        <div style={{
          padding: "13px 22px", borderTop: `1px solid ${C.border}`,
          background: C.bg, display: "flex", justifyContent: "flex-end", gap: 8, flexShrink: 0,
        }}>{footer}</div>
      </div>
    </div>
  );
}
