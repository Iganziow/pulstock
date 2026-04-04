import { C } from "@/lib/theme";

export function StatCard({ label, value, icon, color }: { label: string; value: React.ReactNode; icon: string; color: string }) {
  return (
    <div className="sc" style={{
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: C.rMd, padding: "13px 16px",
      display: "flex", alignItems: "center", gap: 13, boxShadow: C.sh,
    }}>
      <div style={{
        width: 38, height: 38, borderRadius: C.r, flexShrink: 0,
        background: `${color}18`, border: `1px solid ${color}28`,
        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
      }}>{icon}</div>
      <div>
        <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.07em" }}>{label}</div>
        <div style={{ fontSize: 22, fontWeight: 800, color: C.text, lineHeight: 1.15, marginTop: 2, letterSpacing: "-0.03em" }}>{value}</div>
      </div>
    </div>
  );
}
