"use client";
import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";

const C = {
  bg: "#0F172A", card: "#1E293B", border: "#334155",
  text: "#F1F5F9", mute: "#94A3B8", accent: "#6366F1",
  green: "#22C55E", red: "#EF4444", yellow: "#F59E0B", white: "#FFFFFF",
};

const fCLP = (n: number) => "$" + n.toLocaleString("es-CL");
const INV_COLORS: Record<string, string> = { paid: C.green, pending: C.yellow, failed: C.red, voided: C.mute };
const INV_LABELS: Record<string, string> = { paid: "Pagada", pending: "Pendiente", failed: "Fallida", voided: "Anulada" };

type InvRow = {
  id: number; tenant_id: number; tenant_name: string; plan_name: string;
  status: string; amount_clp: number; period_start: string; period_end: string;
  paid_at: string | null; created_at: string;
};

export default function BillingPage() {
  const [invoices, setInvoices] = useState<InvRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "25" });
      if (statusFilter) params.set("status", statusFilter);
      const data = await apiFetch(`/superadmin/invoices/?${params}`);
      setInvoices(data.results);
      setTotal(data.total);
    } finally { setLoading(false); }
  }, [page, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const inputStyle: React.CSSProperties = {
    background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8,
    padding: "8px 12px", color: C.text, fontSize: 13, outline: "none",
  };

  // Totals
  const totalPaid = invoices.filter((i) => i.status === "paid").reduce((a, b) => a + b.amount_clp, 0);
  const totalPending = invoices.filter((i) => i.status === "pending").reduce((a, b) => a + b.amount_clp, 0);

  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Facturación</h1>
      <p style={{ color: C.mute, fontSize: 13, marginBottom: 20 }}>{total} facturas en total</p>

      {/* Summary cards */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: "14px 20px", flex: "1 1 180px" }}>
          <div style={{ fontSize: 11, color: C.mute, textTransform: "uppercase" }}>Pagadas (esta página)</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: C.green }}>{fCLP(totalPaid)}</div>
        </div>
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: "14px 20px", flex: "1 1 180px" }}>
          <div style={{ fontSize: 11, color: C.mute, textTransform: "uppercase" }}>Pendientes (esta página)</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: C.yellow }}>{fCLP(totalPending)}</div>
        </div>
      </div>

      {/* Filter */}
      <div style={{ marginBottom: 16 }}>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} style={inputStyle}>
          <option value="">Todos los estados</option>
          <option value="paid">Pagadas</option>
          <option value="pending">Pendientes</option>
          <option value="failed">Fallidas</option>
          <option value="voided">Anuladas</option>
        </select>
      </div>

      {/* Table */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: C.bg, borderBottom: `1px solid ${C.border}` }}>
              {["#", "Negocio", "Plan", "Período", "Monto", "Estado", "Fecha pago"].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", color: C.mute, fontWeight: 600, fontSize: 11, textTransform: "uppercase" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ padding: 30, textAlign: "center", color: C.mute }}>Cargando...</td></tr>
            ) : invoices.map((inv) => (
              <tr key={inv.id} style={{ borderBottom: `1px solid ${C.border}22` }}>
                <td style={{ padding: "10px 14px", color: C.mute }}>#{inv.id}</td>
                <td style={{ padding: "10px 14px", fontWeight: 600 }}>{inv.tenant_name}</td>
                <td style={{ padding: "10px 14px", color: C.mute }}>{inv.plan_name}</td>
                <td style={{ padding: "10px 14px", fontSize: 12 }}>{inv.period_start} → {inv.period_end}</td>
                <td style={{ padding: "10px 14px", fontWeight: 700 }}>{fCLP(inv.amount_clp)}</td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{
                    padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700,
                    background: (INV_COLORS[inv.status] || C.mute) + "20",
                    color: INV_COLORS[inv.status] || C.mute,
                  }}>
                    {INV_LABELS[inv.status] || inv.status}
                  </span>
                </td>
                <td style={{ padding: "10px 14px", color: C.mute, fontSize: 12 }}>
                  {inv.paid_at ? new Date(inv.paid_at).toLocaleDateString("es-CL") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
        <button disabled={page === 1} onClick={() => setPage(page - 1)} style={{ ...inputStyle, cursor: page > 1 ? "pointer" : "default", opacity: page === 1 ? 0.4 : 1 }}>
          Anterior
        </button>
        <span style={{ display: "flex", alignItems: "center", fontSize: 13, color: C.mute }}>Página {page}</span>
        <button disabled={invoices.length < 25} onClick={() => setPage(page + 1)} style={{ ...inputStyle, cursor: invoices.length >= 25 ? "pointer" : "default", opacity: invoices.length < 25 ? 0.4 : 1 }}>
          Siguiente
        </button>
      </div>
    </div>
  );
}
