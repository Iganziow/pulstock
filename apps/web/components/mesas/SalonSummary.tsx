"use client";

import { C } from "@/lib/theme";
import { Table, Order } from "./types";
import { fmt, timeAgo } from "./helpers";

interface SalonSummaryProps {
  tables: Table[];
  allOrders: Record<number, Order>;
  onSelectTable: (t: Table) => void;
}

export function SalonSummary({ tables, allOrders, onSelectTable }: SalonSummaryProps) {
  const openTables = tables.filter(t => t.status === "OPEN" && t.active_order);
  const totalSalon = openTables.reduce((s, t) => s + Number(t.active_order?.subtotal || 0), 0);

  return (
    <div style={{ padding: "16px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 16 }}>{"📋"}</span>
          <span style={{ fontSize: 15, fontWeight: 800, color: C.text }}>Comandas activas</span>
          {openTables.length > 0 && (
            <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 700, background: C.amberBg, color: C.amber, border: `1px solid ${C.amberBd}` }}>
              {openTables.length}
            </span>
          )}
        </div>
        {totalSalon > 0 && (
          <div style={{ fontSize: 14, fontWeight: 800, color: C.text }}>Total: ${fmt(totalSalon)}</div>
        )}
      </div>

      {openTables.length === 0 ? (
        <div style={{ textAlign: "center", padding: "40px 20px" }}>
          <div style={{ fontSize: 36, marginBottom: 10 }}>{"🍽️"}</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginBottom: 4 }}>Sin comandas abiertas</div>
          <div style={{ fontSize: 12, color: C.mute }}>Selecciona una mesa para abrir una comanda.</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {openTables.map(t => {
            const order = allOrders[t.id];
            const unpaidLines = order ? order.lines.filter(l => !l.is_paid && !l.is_cancelled) : [];
            return (
              <div key={t.id} className="summary-row" onClick={() => onSelectTable(t)} style={{
                padding: "12px 14px", borderRadius: C.rMd,
                border: `1px solid ${C.border}`, background: C.surface,
                cursor: "pointer",
              }}>
                {/* Row header */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 14 }}>{t.is_counter ? "📦" : "🪑"}</span>
                    <span style={{ fontWeight: 700, fontSize: 13, color: C.text }}>
                      {(t.is_counter && t.active_order?.customer_name) ? t.active_order.customer_name : t.name}
                    </span>
                    {t.is_counter && t.active_order?.customer_name && <span style={{ fontSize: 10, color: C.mute }}>&middot; {t.name}</span>}
                    {!t.is_counter && t.zone && <span style={{ fontSize: 10, color: C.mute }}>&middot; {t.zone}</span>}
                  </div>
                  <span style={{ fontWeight: 800, fontSize: 14, color: C.text }}>
                    ${fmt(t.active_order?.subtotal || 0)}
                  </span>
                </div>

                {/* Products list */}
                {unpaidLines.length > 0 ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 4 }}>
                    {unpaidLines.slice(0, 5).map(l => (
                      <span key={l.id} style={{
                        fontSize: 11, padding: "2px 8px", borderRadius: 99,
                        background: l.note ? C.amberBg : C.bg, color: l.note ? C.amber : C.mid, fontWeight: 500,
                        border: `1px solid ${l.note ? C.amberBd : C.border}`,
                      }} title={l.note || undefined}>
                        {l.product_name} &times;{parseFloat(l.qty) % 1 === 0 ? Math.round(parseFloat(l.qty)) : parseFloat(l.qty)}{l.note ? " *" : ""}
                      </span>
                    ))}
                    {unpaidLines.length > 5 && (
                      <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 99, background: C.bg, color: C.mute }}>
                        +{unpaidLines.length - 5} más
                      </span>
                    )}
                  </div>
                ) : !order ? (
                  <div style={{ fontSize: 11, color: C.mute }}>
                    {t.active_order?.items_count || 0} item{(t.active_order?.items_count || 0) !== 1 ? "s" : ""}
                  </div>
                ) : null}

                {/* Footer: time */}
                <div style={{ fontSize: 10, color: C.mute, display: "flex", alignItems: "center", gap: 4 }}>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  {t.active_order ? timeAgo(t.active_order.opened_at) : ""}
                  {t.active_order && <> &middot; {t.active_order.items_count} item{t.active_order.items_count !== 1 ? "s" : ""}</>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
