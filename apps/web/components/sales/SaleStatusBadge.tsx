"use client";

import { C } from "@/lib/theme";

export function SaleStatusBadge({ status }: { status: string }) {
  const s = (status || "").toUpperCase();
  const isVoid = s === "VOID";
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap:5,
      padding:"3px 9px", borderRadius:99, fontSize:11, fontWeight:700,
      border:`1px solid ${isVoid ? C.redBd : C.greenBd}`,
      background:isVoid ? C.redBg : C.greenBg,
      color:isVoid ? C.red : C.green,
      letterSpacing:"0.03em",
    }}>
      <span style={{ width:6, height:6, borderRadius:"50%", background:"currentColor", display:"inline-block" }}/>
      {isVoid ? "Anulada" : "Completada"}
    </span>
  );
}
