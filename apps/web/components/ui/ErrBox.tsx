import { C } from "@/lib/theme";

export function ErrBox({ msg, onClose }: { msg: string; onClose: () => void }) {
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 10,
      padding: "11px 14px", borderRadius: C.r,
      border: `1px solid ${C.redBd}`, background: C.redBg,
      color: C.red, fontSize: 13, fontWeight: 500,
    }}>
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2.5" strokeLinecap="round" style={{ marginTop: 1, flexShrink: 0 }}>
        <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <span style={{ flex: 1 }}>{msg}</span>
      <button onClick={onClose} className="ib" aria-label="Cerrar" style={{
        background: "none", border: "none", color: C.red, padding: 0, fontSize: 16, cursor: "pointer", lineHeight: 1,
      }}>✕</button>
    </div>
  );
}
