"use client";

import { C } from "@/lib/theme";

export function SaleStatCard({ label, value, sub, color, icon }: {
  label: string; value: string; sub?: string;
  color: string; icon: React.ReactNode;
}) {
  return (
    <div style={{
      background:C.surface, border:`1px solid ${C.border}`,
      borderRadius:C.rMd, padding:"14px 18px", boxShadow:C.sh,
      display:"flex", flexDirection:"column", gap:8,
    }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
        <div style={{ fontSize:10.5, fontWeight:700, color:C.mute, textTransform:"uppercase", letterSpacing:"0.07em" }}>{label}</div>
        <div style={{ color, opacity:0.7 }}>{icon}</div>
      </div>
      <div style={{ fontSize:22, fontWeight:800, color, letterSpacing:"-0.03em", fontVariantNumeric:"tabular-nums" }}>{value}</div>
      {sub && <div style={{ fontSize:11, color:C.mute }}>{sub}</div>}
    </div>
  );
}
