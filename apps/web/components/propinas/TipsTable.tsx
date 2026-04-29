"use client";

/**
 * TipsTable — tabla detallada de propinas estilo Fudo.
 *
 * Mario lo pidió: "más que gráficos que a veces no dicen nada, una tabla
 * con los registros para que pueda ver fila por fila quién, cuándo, cuánto".
 * Cuando hay 1000 propinas en un mes, la tabla filtrable es mucho más útil
 * que un gráfico ilegible.
 *
 * Consume `/sales/tips-list/` (paginado, filtrable). Se puede embebir en
 * `/dashboard/propinas` y `/dashboard/caja` (tab Propinas).
 */

import { useEffect, useState, useMemo, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";

interface TipRow {
  sale_id: number;
  sale_number: number | null;
  created_at: string;
  table_name: string | null;
  cashier_id: number;
  cashier_name: string;
  payment_method: string;
  payment_method_label: string;
  total_sale: string;
  tip_amount: string;
  register_id: number | null;
  register_name: string | null;
  sale_type: string;
}

interface TipsListResponse {
  results: TipRow[];
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  totals: {
    total_tips: string;
    total_sales: string;
    count: number;
    avg_tip: string;
  };
  filters: Record<string, any>;
}

function fmtCLP(n: number | string): string {
  const num = typeof n === "string" ? parseFloat(n) : n;
  if (!Number.isFinite(num)) return "$0";
  return "$" + Math.round(num).toLocaleString("es-CL");
}

function fmtDateTime(iso: string): string {
  // "2026-04-29T00:21:48Z" → "29/04/26 00:21:48"
  try {
    const d = new Date(iso);
    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const yy = String(d.getFullYear()).slice(2);
    const HH = String(d.getHours()).padStart(2, "0");
    const MI = String(d.getMinutes()).padStart(2, "0");
    const SS = String(d.getSeconds()).padStart(2, "0");
    return `${dd}/${mm}/${yy} ${HH}:${MI}:${SS}`;
  } catch {
    return iso;
  }
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoISO(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

interface TipsTableProps {
  /** Si true, muestra el panel de filtros completo (default true). En CajaTipsTab puede ser false. */
  showFilters?: boolean;
  /** Default range en días al montar (default 1 = hoy) */
  defaultDaysRange?: number;
  /** Compact: padding chico, fonts un poco menores. Útil dentro del CajaTab. */
  compact?: boolean;
}

export function TipsTable({
  showFilters = true,
  defaultDaysRange = 1,
  compact = false,
}: TipsTableProps) {
  const [dateFrom, setDateFrom] = useState(daysAgoISO(defaultDaysRange - 1));
  const [dateTo, setDateTo] = useState(todayISO());
  const [cashierId, setCashierId] = useState<string>("");
  const [paymentMethod, setPaymentMethod] = useState<string>("");
  const [registerId, setRegisterId] = useState<string>("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const [data, setData] = useState<TipsListResponse | null>(null);
  const [cashiers, setCashiers] = useState<{ id: number; name: string }[]>([]);
  const [registers, setRegisters] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Cargar lista de cajeros y cajas para selectores (1 vez al montar)
  useEffect(() => {
    let cancelled = false;
    // Cajeros: derivamos de la lista de propinas (no hay endpoint ad-hoc).
    // Cajas: /caja/registers/
    apiFetch("/caja/registers/")
      .then((d: any) => { if (!cancelled && Array.isArray(d)) setRegisters(d.map((r: any) => ({ id: r.id, name: r.name }))); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const params = useMemo(() => {
    const u = new URLSearchParams();
    if (dateFrom) u.set("date_from", dateFrom);
    if (dateTo) u.set("date_to", dateTo);
    if (cashierId) u.set("cashier_id", cashierId);
    if (paymentMethod) u.set("payment_method", paymentMethod);
    if (registerId) u.set("register_id", registerId);
    u.set("page", String(page));
    u.set("page_size", String(pageSize));
    return u.toString();
  }, [dateFrom, dateTo, cashierId, paymentMethod, registerId, page, pageSize]);

  const load = useCallback(() => {
    setLoading(true);
    setErr(null);
    apiFetch(`/sales/tips-list/?${params}`)
      .then((d: any) => {
        setData(d as TipsListResponse);
        // Derivar cajeros únicos de la respuesta para el selector
        if (d?.results) {
          const seen = new Map<number, string>();
          for (const row of d.results) {
            if (row.cashier_id && !seen.has(row.cashier_id)) {
              seen.set(row.cashier_id, row.cashier_name);
            }
          }
          setCashiers(prev => {
            const merged = new Map(prev.map(c => [c.id, c.name]));
            for (const [id, name] of seen) merged.set(id, name);
            return Array.from(merged.entries()).map(([id, name]) => ({ id, name }));
          });
        }
      })
      .catch((e: any) => setErr(e?.message || "Error cargando propinas"))
      .finally(() => setLoading(false));
  }, [params]);

  useEffect(() => { load(); }, [load]);

  // Reset page cuando cambian filtros (excepto page mismo)
  useEffect(() => { setPage(1); }, [dateFrom, dateTo, cashierId, paymentMethod, registerId]);

  const padCell = compact ? "8px 10px" : "11px 14px";
  const fontHead = compact ? 11 : 12;
  const fontCell = compact ? 12 : 13;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {/* Filtros */}
      {showFilters && (
        <div style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 8,
          padding: "12px 14px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 10,
        }}>
          <FilterField label="Desde">
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={inputStyle} />
          </FilterField>
          <FilterField label="Hasta">
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={inputStyle} />
          </FilterField>
          <FilterField label="Garzón / Cajero">
            <select value={cashierId} onChange={e => setCashierId(e.target.value)} style={inputStyle}>
              <option value="">Todos</option>
              {cashiers.map(c => (
                <option key={c.id} value={String(c.id)}>{c.name}</option>
              ))}
            </select>
          </FilterField>
          <FilterField label="Medio de pago">
            <select value={paymentMethod} onChange={e => setPaymentMethod(e.target.value)} style={inputStyle}>
              <option value="">Todos</option>
              <option value="cash">Efectivo</option>
              <option value="debit">Tarj. Débito</option>
              <option value="card">Tarj. Crédito</option>
              <option value="transfer">Transferencia</option>
            </select>
          </FilterField>
          <FilterField label="Caja">
            <select value={registerId} onChange={e => setRegisterId(e.target.value)} style={inputStyle}>
              <option value="">Todas</option>
              {registers.map(r => (
                <option key={r.id} value={String(r.id)}>{r.name}</option>
              ))}
            </select>
          </FilterField>
        </div>
      )}

      {/* Header con totales */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "10px 14px",
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
      }}>
        <div style={{ fontSize: 13, color: C.mute }}>
          {data ? (
            <>
              Del <strong style={{ color: C.text }}>{dateFrom}</strong> al <strong style={{ color: C.text }}>{dateTo}</strong>
              {" · "}
              <span style={{ color: C.text, fontWeight: 600 }}>{data.count}</span> registros
            </>
          ) : (
            "Cargando..."
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 10, color: C.mute, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>Total propinas</div>
          <div style={{ fontSize: 22, fontWeight: 900, color: C.amber, fontVariantNumeric: "tabular-nums" }}>
            {data ? fmtCLP(data.totals.total_tips) : "$0"}
          </div>
        </div>
      </div>

      {err && (
        <div style={{ padding: "10px 14px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 8, color: C.red, fontSize: 13 }}>
          {err}
        </div>
      )}

      {/* Tabla */}
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        overflow: "hidden",
      }}>
        {loading && (
          <div style={{ padding: 30, display: "flex", justifyContent: "center" }}><Spinner /></div>
        )}
        {!loading && data && data.results.length === 0 && (
          <div style={{ padding: 30, textAlign: "center", color: C.mute, fontSize: 13 }}>
            No hay propinas para los filtros seleccionados.
          </div>
        )}
        {!loading && data && data.results.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720 }}>
              <thead>
                <tr style={{ background: C.bg, borderBottom: `1px solid ${C.border}` }}>
                  <Th compact={compact}>Fecha</Th>
                  <Th compact={compact} center>Mesa</Th>
                  <Th compact={compact}>Garzón / Cajero</Th>
                  <Th compact={compact}>Medio de pago</Th>
                  <Th compact={compact} right>Total Venta</Th>
                  <Th compact={compact} right>Propina</Th>
                </tr>
              </thead>
              <tbody>
                {data.results.map(row => (
                  <tr key={row.sale_id} style={{ borderBottom: `1px solid ${C.border}` }}>
                    <Td compact={compact} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: fontCell - 1, color: C.mid }}>
                      {fmtDateTime(row.created_at)}
                    </Td>
                    <Td compact={compact} center style={{ fontWeight: row.table_name ? 700 : 400, color: row.table_name ? C.text : C.mute }}>
                      {row.table_name || "—"}
                    </Td>
                    <Td compact={compact} style={{ fontWeight: 600 }}>{row.cashier_name}</Td>
                    <Td compact={compact}>
                      <PaymentBadge method={row.payment_method} label={row.payment_method_label} />
                    </Td>
                    <Td compact={compact} right style={{ fontVariantNumeric: "tabular-nums" }}>
                      {fmtCLP(row.total_sale)}
                    </Td>
                    <Td compact={compact} right style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, color: C.amber }}>
                      {fmtCLP(row.tip_amount)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Paginación */}
      {data && data.total_pages > 1 && (
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "8px 14px",
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 8,
        }}>
          <div style={{ fontSize: 12, color: C.mute }}>
            Página {data.page} de {data.total_pages} · {data.count} registros
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <PageBtn disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>← Anterior</PageBtn>
            <PageBtn disabled={page >= data.total_pages} onClick={() => setPage(p => p + 1)}>Siguiente →</PageBtn>
          </div>
        </div>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "7px 10px",
  border: `1px solid ${C.border}`,
  borderRadius: 6,
  fontSize: 12,
  fontFamily: "inherit",
  background: C.surface,
  color: C.text,
};

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 10, color: C.mute, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</span>
      {children}
    </div>
  );
}

function Th({ children, right, center, compact }: { children: React.ReactNode; right?: boolean; center?: boolean; compact?: boolean }) {
  return (
    <th style={{
      textAlign: right ? "right" : center ? "center" : "left",
      padding: compact ? "8px 10px" : "10px 14px",
      fontSize: compact ? 10 : 11,
      fontWeight: 700,
      color: C.mute,
      textTransform: "uppercase",
      letterSpacing: "0.06em",
    }}>{children}</th>
  );
}

function Td({ children, right, center, compact, style }: { children: React.ReactNode; right?: boolean; center?: boolean; compact?: boolean; style?: React.CSSProperties }) {
  return (
    <td style={{
      textAlign: right ? "right" : center ? "center" : "left",
      padding: compact ? "8px 10px" : "11px 14px",
      fontSize: compact ? 12 : 13,
      color: C.text,
      ...style,
    }}>{children}</td>
  );
}

function PaymentBadge({ method, label }: { method: string; label: string }) {
  const config: Record<string, { bg: string; color: string; bd: string }> = {
    cash:     { bg: "#ECFDF5", color: "#16A34A", bd: "#A7F3D0" },
    debit:    { bg: "#EEF2FF", color: "#4F46E5", bd: "#C7D2FE" },
    card:     { bg: "#FFFBEB", color: "#D97706", bd: "#FDE68A" },
    transfer: { bg: "#F0F9FF", color: "#0284C7", bd: "#BAE6FD" },
    mixed:    { bg: "#F4F4F5", color: "#71717A", bd: "#D4D4D8" },
  };
  const c = config[method] || config.mixed;
  return (
    <span style={{
      display: "inline-block",
      padding: "3px 8px",
      borderRadius: 4,
      background: c.bg,
      color: c.color,
      border: `1px solid ${c.bd}`,
      fontSize: 11,
      fontWeight: 600,
      whiteSpace: "nowrap",
    }}>
      {label}
    </span>
  );
}

function PageBtn({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "6px 12px",
        fontSize: 12,
        fontWeight: 600,
        border: `1px solid ${C.border}`,
        borderRadius: 6,
        background: disabled ? C.bg : C.surface,
        color: disabled ? C.mute : C.text,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {children}
    </button>
  );
}
