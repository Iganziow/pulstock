import { C } from "@/lib/theme";

export const iS: React.CSSProperties = {
  width: "100%", height: 38, padding: "0 12px",
  border: `1px solid ${C.border}`, borderRadius: C.r,
  background: C.surface, fontSize: 14, transition: C.ease,
};
export const tS: React.CSSProperties = { ...iS, height: "auto", minHeight: 90, padding: "10px 12px", resize: "vertical", lineHeight: 1.55 };
export const FL: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 5 };
export const G2: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 };

export function FLabel({ children, req }: { children: React.ReactNode; req?: boolean }) {
  return (
    <label style={{ fontSize: 11, fontWeight: 700, color: C.mid, letterSpacing: "0.06em", textTransform: "uppercase" }}>
      {children}{req && <span style={{ color: C.accent, marginLeft: 2 }}>*</span>}
    </label>
  );
}

export function Hint({ children }: { children: React.ReactNode }) {
  return <span style={{ fontSize: 11.5, color: C.mute }}>{children}</span>;
}

export function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <div onClick={() => onChange(!on)} style={{
      width: 38, height: 22, borderRadius: 11,
      background: on ? C.accent : C.borderMd,
      position: "relative", transition: C.ease, cursor: "pointer", flexShrink: 0,
    }}>
      <div style={{
        width: 16, height: 16, borderRadius: "50%", background: "#fff",
        position: "absolute", top: 3, left: on ? 19 : 3,
        transition: C.ease, boxShadow: "0 1px 3px rgba(0,0,0,0.22)",
      }} />
    </div>
  );
}
