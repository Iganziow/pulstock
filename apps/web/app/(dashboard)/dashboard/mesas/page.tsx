"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";


const PAGE_CSS = `
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
@keyframes fadeIn{from{opacity:0;transform:scale(0.97)}to{opacity:1;transform:scale(1)}}
* { box-sizing: border-box; }
.mesa-card{transition:all 0.13s ease;cursor:pointer;}
.mesa-card:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,0.1);}
.summary-row{transition:background 0.12s ease;cursor:pointer;}
.summary-row:hover{background:#F4F4F5 !important;}
`;

function useStyles() {
  useEffect(() => {
    const id = "mesas-page-css";
    if (document.getElementById(id)) return;
    const el = document.createElement("style");
    el.id = id; el.textContent = PAGE_CSS;
    document.head.appendChild(el);
  }, []);
}

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}

// ─── Types ────────────────────────────────────────────────────────────────────
type TableStatus = "FREE" | "OPEN";
type TableActiveOrder = { id: number; opened_at: string; items_count: number; subtotal: string; customer_name?: string };
type Table = {
  id: number; name: string; capacity: number; status: TableStatus;
  is_active: boolean; zone: string; is_counter: boolean;
  active_order: TableActiveOrder | null;
};

type OrderLine = {
  id: number; product_id: number; product_name: string;
  qty: string; unit_price: string; line_total: string;
  note: string; added_at: string; added_by: string; is_paid: boolean;
  is_cancelled: boolean;
  cancel_reason?: string;
};
type Order = {
  id: number; table_id: number; table_name: string; status: string;
  opened_by: string; opened_at: string; closed_at: string | null;
  customer_name: string; note: string; warehouse_id: number;
  lines: OrderLine[];
  subtotal_unpaid: string;
};

type Product = { id: number; name: string; price: string; sku: string };

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmt(v: string | number) {
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? Math.round(n).toLocaleString("es-CL") : "0";
}
function fmtTime(iso: string) {
  return new Date(iso).toLocaleString("es-CL", { hour: "2-digit", minute: "2-digit" });
}
function timeAgo(iso: string) {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (diff < 1) return "ahora";
  if (diff < 60) return `${diff}m`;
  const h = Math.floor(diff / 60);
  return `${h}h${diff % 60 > 0 ? ` ${diff % 60}m` : ""}`;
}

function Spinner({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
      style={{ animation: "spin 0.7s linear infinite", flexShrink: 0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  );
}

function Btn({ children, onClick, variant = "secondary", disabled, full, size = "md" }: {
  children: React.ReactNode; onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost"; disabled?: boolean; full?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  const vs: Record<string, React.CSSProperties> = {
    primary:   { background: C.accent, color: "#fff", border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text, border: `1px solid ${C.borderMd}` },
    danger:    { background: C.redBg, color: C.red, border: `1px solid ${C.redBd}` },
    ghost:     { background: "transparent", color: C.mid, border: "1px solid transparent" },
  };
  const pad = size === "sm" ? "5px 10px" : size === "lg" ? "11px 22px" : "8px 16px";
  const fs = size === "sm" ? 12 : size === "lg" ? 15 : 13;
  return (
    <button onClick={onClick} disabled={disabled} style={{
      ...vs[variant], padding: pad, borderRadius: C.r, fontSize: fs, fontWeight: 600,
      cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
      display: "inline-flex", alignItems: "center", gap: 6,
      width: full ? "100%" : undefined, justifyContent: full ? "center" : undefined,
      transition: "all 0.13s ease", fontFamily: "inherit",
    }}>
      {children}
    </button>
  );
}

function Modal({ title, onClose, children, width = 500 }: {
  title: string; onClose: () => void; children: React.ReactNode; width?: number;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }} onClick={onClose}>
      <div style={{ background: C.surface, borderRadius: C.rMd, width: "100%", maxWidth: width, maxHeight: "90vh", overflowY: "auto", boxShadow: C.shMd, animation: "fadeIn 0.15s ease" }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: `1px solid ${C.border}` }}>
          <span style={{ fontWeight: 700, fontSize: 15, color: C.text }}>{title}</span>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 4, display: "flex", borderRadius: 4 }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div style={{ padding: "16px 18px" }}>{children}</div>
      </div>
    </div>
  );
}

// ─── Table Card (compact) ─────────────────────────────────────────────────────
function TableCard({ table, selected, onClick }: { table: Table; selected: boolean; onClick: () => void }) {
  const occupied = table.status === "OPEN";
  const borderColor = selected ? C.accent : occupied ? C.amber : C.border;
  const bgColor = selected ? C.accentBg : occupied ? "#FFFDF5" : C.surface;
  return (
    <div className="mesa-card" onClick={onClick} style={{
      border: `2px solid ${borderColor}`, borderRadius: C.rMd, background: bgColor,
      padding: "12px 14px", position: "relative",
      boxShadow: selected ? `0 0 0 3px ${C.accentBd}` : C.sh,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {table.name}
        </span>
        <span style={{
          width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
          background: occupied ? C.amber : C.green,
          boxShadow: occupied ? `0 0 0 3px ${C.amberBd}` : `0 0 0 3px ${C.greenBd}`,
        }} />
      </div>
      {occupied && table.active_order ? (
        <>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>
            ${fmt(table.active_order.subtotal)}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
            <span style={{ fontSize: 11, color: C.amber, fontWeight: 600 }}>
              {table.active_order.items_count} ítem{table.active_order.items_count !== 1 ? "s" : ""}
            </span>
            <span style={{ fontSize: 11, color: C.mute }}>
              {timeAgo(table.active_order.opened_at)}
            </span>
          </div>
        </>
      ) : (
        <div style={{ fontSize: 11, color: C.mute }}>
          {table.capacity} pers. · Libre
        </div>
      )}
    </div>
  );
}

// ─── Payment Modal ─────────────────────────────────────────────────────────────
type PaymentRow = { method: string; amount: string };
const PAY_METHODS = [
  { value: "cash", label: "Efectivo" },
  { value: "debit", label: "Débito" },
  { value: "card", label: "Crédito" },
  { value: "transfer", label: "Transferencia" },
];

function PaymentModal({
  total, tableName, onConfirm, onClose, loading, unpaidLines, canConsumoInterno,
}: {
  total: number; tableName: string;
  onConfirm: (payments: PaymentRow[], tip: number, mode: "all" | "partial", lineIds: number[], saleType?: string) => void;
  onClose: () => void; loading: boolean; unpaidLines: OrderLine[]; canConsumoInterno?: boolean;
}) {
  const [rows, setRows] = useState<PaymentRow[]>([{ method: "cash", amount: "" }]);
  const [tipStr, setTipStr] = useState("");
  const [splitN, setSplitN] = useState("");
  const [checkoutMode, setCheckoutMode] = useState<"all" | "partial">("all");
  const [selLines, setSelLines] = useState<Set<number>>(new Set(unpaidLines.map(l => l.id)));
  const [isConsumoInterno, setIsConsumoInterno] = useState(false);

  const toggleLine = (id: number) => {
    setSelLines(prev => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
  };

  const lineSubtotal = checkoutMode === "partial"
    ? unpaidLines.filter(l => selLines.has(l.id)).reduce((s, l) => s + Number(l.line_total), 0)
    : total;
  const tip = Math.max(0, Number(tipStr) || 0);
  const grandTotal = lineSubtotal + tip;
  const totalPaid = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const change = Math.max(0, totalPaid - grandTotal);
  const pending = Math.max(0, grandTotal - totalPaid);
  const splitPer = splitN ? grandTotal / Math.max(1, Number(splitN)) : null;

  function addRow() {
    const used = new Set(rows.map(r => r.method));
    const next = PAY_METHODS.find(m => !used.has(m.value))?.value || "cash";
    setRows(prev => [...prev, { method: next, amount: "" }]);
  }
  function removeRow(i: number) { setRows(prev => prev.filter((_, j) => j !== i)); }
  function updateRow(i: number, field: keyof PaymentRow, val: string) {
    setRows(prev => prev.map((r, j) => j === i ? { ...r, [field]: val } : r));
  }
  function quickFill(i: number) {
    const rest = rows.reduce((s, r, j) => j !== i ? s + (Number(r.amount) || 0) : s, 0);
    const val = Math.max(0, Math.round(grandTotal - rest));
    if (val > 0) updateRow(i, "amount", String(val));
  }

  return (
    <Modal title={`Cobrar — ${tableName}`} onClose={onClose} width={520}>
      {/* Mode selector */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {(["all", "partial"] as const).map(m => (
          <button key={m} onClick={() => setCheckoutMode(m)} style={{
            flex: 1, padding: "8px", borderRadius: C.r, fontSize: 12, fontWeight: 600,
            border: `2px solid ${checkoutMode === m ? C.accent : C.border}`,
            background: checkoutMode === m ? C.accentBg : C.surface,
            color: checkoutMode === m ? C.accent : C.mid,
            cursor: "pointer", fontFamily: "inherit",
          }}>
            {m === "all" ? "Cobrar todo" : "Por ítems"}
          </button>
        ))}
      </div>

      {/* Partial: line selector */}
      {checkoutMode === "partial" && (
        <div style={{ marginBottom: 14, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", maxHeight: 180, overflowY: "auto" }}>
          {unpaidLines.map(l => (
            <label key={l.id} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
              borderBottom: `1px solid ${C.border}`, cursor: "pointer",
              background: selLines.has(l.id) ? C.accentBg : C.surface,
            }}>
              <input type="checkbox" checked={selLines.has(l.id)} onChange={() => toggleLine(l.id)}
                style={{ accentColor: C.accent, width: 15, height: 15, flexShrink: 0 }} />
              <span style={{ flex: 1, fontSize: 12, fontWeight: 600, color: C.text }}>{l.product_name}</span>
              <span style={{ fontWeight: 700, fontSize: 12, color: C.text }}>${fmt(l.line_total)}</span>
            </label>
          ))}
        </div>
      )}

      {/* Items list — always visible in "all" mode */}
      {checkoutMode === "all" && unpaidLines.length > 0 && (
        <div style={{
          marginBottom: 14, border: `1px solid ${isConsumoInterno ? "#F59E0B" : C.border}`,
          borderRadius: C.r, overflow: "hidden", maxHeight: 200, overflowY: "auto",
          background: isConsumoInterno ? "#FFFBEB" : C.surface,
        }}>
          <div style={{
            padding: "6px 10px", borderBottom: `1px solid ${isConsumoInterno ? "#F59E0B" : C.border}`,
            fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em",
            background: isConsumoInterno ? "#FEF3C7" : C.bg,
            color: isConsumoInterno ? "#92400E" : C.mute,
          }}>
            {isConsumoInterno ? "Items a registrar como consumo" : `${unpaidLines.length} producto(s)`}
          </div>
          {unpaidLines.map(l => (
            <div key={l.id} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
              borderBottom: `1px solid ${C.border}`,
            }}>
              <span style={{ flex: 1, fontSize: 12, fontWeight: 600, color: C.text }}>{l.product_name}</span>
              <span style={{ fontSize: 11, color: C.mid }}>{l.qty} × ${fmt(l.unit_price)}</span>
              <span style={{ fontWeight: 700, fontSize: 12, color: isConsumoInterno ? "#92400E" : C.text }}>${fmt(l.line_total)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Consumo interno toggle */}
      {canConsumoInterno && (
        <label style={{
          display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
          borderRadius: C.r, border: `1px solid ${isConsumoInterno ? "#F59E0B" : C.border}`,
          background: isConsumoInterno ? "#FFFBEB" : "transparent",
          cursor: "pointer", marginBottom: 12,
        }}>
          <input type="checkbox" checked={isConsumoInterno}
            onChange={e => setIsConsumoInterno(e.target.checked)}
            style={{ accentColor: "#D97706", width: 15, height: 15, flexShrink: 0 }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: isConsumoInterno ? "#D97706" : C.mid }}>
            Consumo interno (sin cobro)
          </span>
        </label>
      )}

      {/* Payment rows */}
      {!isConsumoInterno && <div style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em" }}>Forma de pago</span>
          {rows.length < PAY_METHODS.length && (
            <button onClick={addRow} style={{
              display: "flex", alignItems: "center", gap: 4, padding: "3px 10px", borderRadius: C.r,
              border: `1px dashed ${C.borderMd}`, background: "transparent", cursor: "pointer",
              fontSize: 11, fontWeight: 600, color: C.accent, fontFamily: "inherit",
            }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              Agregar
            </button>
          )}
        </div>
        {rows.map((row, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 6, marginBottom: 6,
            padding: "5px 8px", borderRadius: C.r,
            background: Number(row.amount) > 0 ? C.accentBg : "transparent",
            border: `1px solid ${Number(row.amount) > 0 ? C.accentBd : "transparent"}`,
          }}>
            <select value={row.method} onChange={e => updateRow(i, "method", e.target.value)}
              style={{
                padding: "6px 8px", border: `1px solid ${C.border}`, borderRadius: C.r,
                fontSize: 12, fontWeight: 600, fontFamily: "inherit", outline: "none",
                background: C.surface, color: C.text, cursor: "pointer", minWidth: 110,
              }}>
              {PAY_METHODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <input type="number" min="0" value={row.amount}
              onChange={e => updateRow(i, "amount", e.target.value)}
              placeholder="$0" style={{
                flex: 1, padding: "6px 10px",
                border: `1px solid ${Number(row.amount) > 0 ? C.accentBd : C.border}`,
                borderRadius: C.r, fontSize: 13, fontFamily: "inherit", outline: "none",
              }} />
            <button onClick={() => quickFill(i)} title="Completar"
              style={{ width: 28, height: 28, borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: C.accent, fontWeight: 700, fontSize: 13, fontFamily: "inherit", flexShrink: 0 }}>
              →
            </button>
            {rows.length > 1 && (
              <button onClick={() => removeRow(i)} style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex", flexShrink: 0 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            )}
          </div>
        ))}
      </div>}

      {/* Tip */}
      {!isConsumoInterno && (
      <div style={{ marginBottom: 14, padding: "10px 12px", borderRadius: C.r, border: `1px solid ${C.amberBd}`, background: C.amberBg }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: C.amber }}>Propina (opcional)</span>
        </div>
        <input type="number" min="0" value={tipStr} onChange={e => setTipStr(e.target.value)}
          placeholder="$0" style={{ width: "100%", padding: "6px 10px", border: `1px solid ${C.amberBd}`, borderRadius: C.r, fontSize: 13, fontFamily: "inherit", outline: "none", background: "#fff" }} />
      </div>
      )}

      {/* Summary */}
      <div style={{ background: C.bg, borderRadius: C.r, padding: "12px 14px", marginBottom: 14, border: `1px solid ${C.border}` }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.mid, marginBottom: 3 }}>
          <span>Subtotal</span><span>${fmt(lineSubtotal)}</span>
        </div>
        {tip > 0 && (
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.amber, marginBottom: 3 }}>
            <span>Propina</span><span>+${fmt(tip)}</span>
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 15, fontWeight: 800, color: C.text, borderTop: `1px solid ${C.border}`, paddingTop: 6, marginTop: 3 }}>
          <span>Total a cobrar</span><span>${fmt(grandTotal)}</span>
        </div>
        {!isConsumoInterno && totalPaid > 0 && (
          <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.mid, marginBottom: 2 }}>
              <span>Pagado</span><span>${fmt(totalPaid)}</span>
            </div>
            {change > 0 && <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700, color: C.green }}><span>Vuelto</span><span>${fmt(change)}</span></div>}
            {pending > 0 && <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700, color: C.red }}><span>Falta</span><span>${fmt(pending)}</span></div>}
            {pending === 0 && change === 0 && <div style={{ fontSize: 13, fontWeight: 700, color: C.green, textAlign: "center" }}>Pagado exacto</div>}
          </div>
        )}
      </div>

      {/* Split */}
      {!isConsumoInterno && (
      <div style={{ marginBottom: 14, display: "flex", gap: 8, alignItems: "center" }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: C.mid }}>Dividir en:</span>
        <input type="number" min="1" value={splitN} onChange={e => setSplitN(e.target.value)}
          placeholder="N" style={{ width: 50, padding: "5px 8px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, fontFamily: "inherit", outline: "none" }} />
        <span style={{ fontSize: 11, color: C.mute }}>pers.</span>
        {splitPer != null && <span style={{ fontSize: 13, fontWeight: 700, color: C.accent, marginLeft: "auto" }}>${fmt(splitPer)} c/u</span>}
      </div>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        <Btn variant="secondary" onClick={onClose}>Cancelar</Btn>
        <Btn variant={isConsumoInterno ? "danger" : "primary"} full size="lg"
          disabled={loading || grandTotal === 0 || (checkoutMode === "partial" && selLines.size === 0) || (!isConsumoInterno && totalPaid < grandTotal)}
          onClick={() => onConfirm(
            isConsumoInterno ? [] : rows.filter(r => Number(r.amount) > 0),
            isConsumoInterno ? 0 : tip,
            checkoutMode, [...selLines],
            isConsumoInterno ? "CONSUMO_INTERNO" : "VENTA",
          )}>
          {loading ? <Spinner size={14} /> : null}
          {loading ? "Procesando…" : isConsumoInterno ? "Registrar consumo" : `Cobrar $${fmt(grandTotal)}`}
        </Btn>
      </div>
    </Modal>
  );
}

// ─── Add Item Panel ────────────────────────────────────────────────────────────
function AddItemPanel({ orderId, onAdded }: { orderId: number; onAdded: () => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const [searching, setSearching] = useState(false);
  const [cart, setCart] = useState<{ product: Product; qty: number; unit_price: string; note: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const debounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await apiFetch(`/catalog/products/?q=${encodeURIComponent(q)}&is_active=true&page_size=15`);
        setResults(data?.results || data || []);
      } catch (e: any) { setErr(e?.message || "Error al buscar productos"); } finally { setSearching(false); }
    }, 280);
  }, [q]);

  function addToCart(p: Product) {
    setQ(""); setResults([]);
    setCart(prev => {
      const existing = prev.find(c => c.product.id === p.id);
      if (existing) return prev.map(c => c.product.id === p.id ? { ...c, qty: c.qty + 1 } : c);
      return [...prev, { product: p, qty: 1, unit_price: p.price || "0", note: "" }];
    });
  }

  async function save() {
    if (!cart.length) return;
    setSaving(true); setErr("");
    try {
      await apiFetch(`/tables/orders/${orderId}/add-lines/`, {
        method: "POST",
        body: JSON.stringify({ lines: cart.map(c => ({ product_id: c.product.id, qty: c.qty, unit_price: c.unit_price, note: c.note })) }),
      });
      setCart([]);
      onAdded();
    } catch (e: any) {
      setErr(e?.message || "Error al agregar");
    } finally { setSaving(false); }
  }

  return (
    <div>
      <div style={{ position: "relative", marginBottom: 10 }}>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar producto…" autoFocus
          style={{ width: "100%", padding: "8px 11px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, fontFamily: "inherit", outline: "none" }} />
        {searching && <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", color: C.mute }}><Spinner size={13} /></div>}
        {results.length > 0 && (
          <div style={{ position: "absolute", top: "100%", left: 0, right: 0, background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, boxShadow: C.shMd, zIndex: 10, maxHeight: 200, overflowY: "auto" }}>
            {results.map(p => (
              <div key={p.id} onClick={() => addToCart(p)} style={{ padding: "8px 12px", cursor: "pointer", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{p.name}</div>
                  <div style={{ fontSize: 10, color: C.mute }}>{p.sku}</div>
                </div>
                <div style={{ fontWeight: 700, fontSize: 12, color: C.accent }}>${fmt(p.price)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      {cart.length > 0 && (
        <div style={{ border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", marginBottom: 10 }}>
          {cart.map((c, i) => (
            <div key={c.product.id} style={{ padding: "8px 10px", borderBottom: i < cart.length - 1 ? `1px solid ${C.border}` : "none", display: "flex", gap: 6, alignItems: "center" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{c.product.name}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 4 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={c.note ? C.amber : C.mute} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                  <input value={c.note} onChange={e => setCart(prev => prev.map((x, j) => j === i ? { ...x, note: e.target.value } : x))}
                    placeholder="Comentario: sin cebolla, extra salsa..."
                    style={{
                      width: "100%", padding: "4px 8px",
                      border: `1px solid ${c.note ? C.amberBd : C.border}`,
                      borderRadius: C.r, fontSize: 11, fontFamily: "inherit", outline: "none",
                      background: c.note ? C.amberBg : C.surface,
                      color: c.note ? C.amber : C.text,
                    }} />
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
                <button onClick={() => setCart(prev => prev.map((x, j) => j === i ? { ...x, qty: Math.max(1, x.qty - 1) } : x))}
                  style={{ width: 22, height: 22, borderRadius: 4, border: `1px solid ${C.border}`, background: C.surface, cursor: "pointer", fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center" }}>−</button>
                <span style={{ width: 24, textAlign: "center", fontSize: 13, fontWeight: 700 }}>{c.qty}</span>
                <button onClick={() => setCart(prev => prev.map((x, j) => j === i ? { ...x, qty: x.qty + 1 } : x))}
                  style={{ width: 22, height: 22, borderRadius: 4, border: `1px solid ${C.border}`, background: C.surface, cursor: "pointer", fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center" }}>+</button>
              </div>
              <div style={{ fontWeight: 700, fontSize: 12, color: C.text, minWidth: 50, textAlign: "right" }}>${fmt(Number(c.unit_price) * c.qty)}</div>
              <button onClick={() => setCart(prev => prev.filter((_, j) => j !== i))}
                style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex" }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          ))}
        </div>
      )}
      {err && <div style={{ fontSize: 11, color: C.red, marginBottom: 6 }}>{err}</div>}
      {cart.length > 0 && (
        <Btn variant="primary" full disabled={saving} onClick={save}>
          {saving ? <Spinner size={13} /> : null}
          {saving ? "Agregando…" : `Agregar ${cart.length} ítem${cart.length !== 1 ? "s" : ""}`}
        </Btn>
      )}
    </div>
  );
}

// ─── Order Panel (right panel when table selected) ────────────────────────────
function OrderPanel({ order, tableName, isCounter, onRefresh, onClose, onOrderUpdate, canConsumoInterno }: {
  order: Order; tableName: string; isCounter: boolean; onRefresh: () => void; onClose: () => void; onOrderUpdate: (o: Order) => void; canConsumoInterno?: boolean;
}) {
  const [showAddItem, setShowAddItem] = useState(order.lines.length === 0);
  const [showPayment, setShowPayment] = useState(false);
  const [deletingLine, setDeletingLine] = useState<number | null>(null);
  const [confirmDeleteLine, setConfirmDeleteLine] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [payLoading, setPayLoading] = useState(false);
  const [payErr, setPayErr] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [cancelErr, setCancelErr] = useState("");

  async function cancelOrder() {
    if (!confirm("¿Cerrar esta mesa sin cobrar?")) return;
    setCancelling(true); setCancelErr("");
    try {
      await apiFetch(`/tables/orders/${order.id}/cancel/`, { method: "POST" });
      onClose();
      onRefresh();
    } catch (e: any) {
      setCancelErr(e?.message || "Error al cancelar");
    } finally { setCancelling(false); }
  }

  const unpaidLines = order.lines.filter(l => !l.is_paid && !l.is_cancelled);
  const cancelledLines = order.lines.filter(l => l.is_cancelled);
  const paidLines = order.lines.filter(l => l.is_paid);

  const [quickPayLine, setQuickPayLine] = useState<OrderLine | null>(null);

  async function handlePrintPreCuenta() {
    try {
      const { getDefaultPrinter, printBytes, printHTML } = await import("@/lib/printer");
      const { buildPreCuenta, buildPreCuentaHTML } = await import("@/lib/receipt-builder");
      const printer = getDefaultPrinter();
      const tenantData = await apiFetch("/core/settings/").catch(() => null);
      const data = {
        tableName: order.customer_name || tableName,
        lines: unpaidLines.map(l => ({ name: l.product_name, qty: parseFloat(l.qty), total: parseFloat(l.line_total) })),
        subtotal: parseFloat(order.subtotal_unpaid || "0"),
        date: new Date(),
        attendedBy: order.opened_by,
        tenant: tenantData ? { name: tenantData.name, rut: tenantData.rut, address: tenantData.address, receipt_header: tenantData.receipt_header } : undefined,
      };
      if (printer && printer.type === "system") {
        const { printSystemReceipt } = await import("@/lib/printer");
        printSystemReceipt(buildPreCuentaHTML(data), printer);
      } else if (printer) {
        const paperWidth = printer.paperWidth || 80;
        const bytes = buildPreCuenta(data, paperWidth);
        await printBytes(bytes, printer);
      } else {
        printHTML(buildPreCuentaHTML(data));
      }
    } catch (e: any) {
      setPayErr(e?.message || "Error al imprimir pre-cuenta");
    }
  }

  async function deleteLine(lineId: number) {
    if (!cancelReason.trim()) { setPayErr("Debes ingresar un motivo"); return; }
    setDeletingLine(lineId);
    try {
      const data = await apiFetch(`/tables/orders/${order.id}/lines/${lineId}/`, {
        method: "DELETE",
        body: JSON.stringify({ reason: cancelReason.trim() }),
      });
      onOrderUpdate(data);
      setConfirmDeleteLine(null);
      setCancelReason("");
    } catch (e: any) { setPayErr(e?.message || "Error al eliminar ítem"); } finally { setDeletingLine(null); }
  }

  const [lastSaleId, setLastSaleId] = useState<number | null>(null);

  async function handleCheckout(payments: PaymentRow[], tip: number, mode: "all" | "partial", lineIds: number[], saleType?: string) {
    setPayLoading(true); setPayErr("");
    try {
      const payArr = payments.map(r => ({ method: r.method, amount: Number(r.amount) }));
      const res = await apiFetch(`/tables/orders/${order.id}/checkout/`, {
        method: "POST",
        body: JSON.stringify({
          mode, line_ids: mode === "partial" ? lineIds : [],
          payments: payArr, tip: tip > 0 ? tip : undefined,
          sale_type: saleType || "VENTA",
        }),
      });
      setShowPayment(false);
      setLastSaleId(res?.sale_id || res?.id || null);
      setSuccessMsg("¡Cobro registrado!");
      setTimeout(() => setSuccessMsg(""), 6000);
      onRefresh();
    } catch (e: any) {
      setPayErr(e?.message || "Error al cobrar");
    } finally { setPayLoading(false); }
  }

  async function handlePrintReceipt(saleId: number) {
    try {
      const { getDefaultPrinter, printBytes, printHTML } = await import("@/lib/printer");
      const { buildReceipt, buildReceiptHTML } = await import("@/lib/receipt-builder");
      const [sale, tenant] = await Promise.all([
        apiFetch(`/sales/sales/${saleId}/`),
        apiFetch("/core/settings/").catch(() => null),
      ]);
      const printer = getDefaultPrinter();
      const receiptData = {
        saleNumber: sale.sale_number || sale.id,
        date: sale.created_at,
        lines: (sale.lines || []).map((l: any) => ({
          name: l.product?.name || "Producto",
          qty: l.qty,
          unitPrice: l.unit_price,
          total: l.line_total,
        })),
        subtotal: parseFloat(sale.subtotal || "0"),
        tip: parseFloat(sale.tip || "0"),
        total: parseFloat(sale.total || "0"),
        payments: (sale.payments || []).map((p: any) => ({ method: p.method, amount: p.amount })),
        tenant: tenant ? {
          name: tenant.name, rut: tenant.rut, address: tenant.address,
          receipt_header: tenant.receipt_header, receipt_footer: tenant.receipt_footer,
        } : undefined,
      };
      if (printer && printer.type === "system") {
        const { printSystemReceipt } = await import("@/lib/printer");
        printSystemReceipt(buildReceiptHTML(receiptData), printer);
      } else if (printer) {
        const bytes = buildReceipt(receiptData, printer.paperWidth || 80);
        await printBytes(bytes, printer);
      } else {
        printHTML(buildReceiptHTML(receiptData));
      }
    } catch (e: any) {
      setPayErr(e?.message || "Error al imprimir boleta");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 8 }}>
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex", borderRadius: 4 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <span style={{ fontSize: 16 }}>{isCounter ? "\uD83D\uDCE6" : "\uD83E\uDE91"}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 800, fontSize: 15, color: C.text }}>
            {order.customer_name || tableName}
          </div>
          <div style={{ fontSize: 10, color: C.mute }}>
            {order.customer_name && <>{tableName} · </>}
            {order.opened_by} · {fmtTime(order.opened_at)} · {timeAgo(order.opened_at)}
          </div>
        </div>
        {unpaidLines.length > 0 && (
          <button onClick={handlePrintPreCuenta} title="Imprimir pre-cuenta"
            style={{ background: "none", border: `1px solid ${C.border}`, borderRadius: 6, cursor: "pointer", padding: "4px 8px", display: "flex", alignItems: "center", gap: 4, color: C.mid, fontSize: 11, fontWeight: 600 }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>
            </svg>
            Pre-cuenta
          </button>
        )}
      </div>

      {successMsg && (
        <div style={{ margin: "8px 16px 0", padding: "6px 10px", borderRadius: C.r, background: C.greenBg, border: `1px solid ${C.greenBd}`, color: C.green, fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ flex: 1 }}>{successMsg}</span>
          {lastSaleId && (
            <button onClick={() => handlePrintReceipt(lastSaleId)}
              style={{ background: C.green, color: "#fff", border: "none", borderRadius: 4, padding: "3px 8px", fontSize: 10, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 4, whiteSpace: "nowrap" }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>
              </svg>
              Imprimir
            </button>
          )}
        </div>
      )}

      {/* Body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "10px 16px" }}>
        {/* Unpaid lines */}
        {unpaidLines.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
              Pendiente ({unpaidLines.length})
            </div>
            {unpaidLines.map(l => (
              <div key={l.id} style={{ borderBottom: `1px solid ${C.bg}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 0" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{l.product_name}</div>
                    {l.note && (
                      <div style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: C.amber, marginTop: 1, padding: "1px 6px", background: C.amberBg, borderRadius: 4, border: `1px solid ${C.amberBd}`, width: "fit-content" }}>
                        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                        {l.note}
                      </div>
                    )}
                    <div style={{ fontSize: 10, color: C.mute }}>{l.qty} × ${fmt(l.unit_price)}</div>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: 12, color: C.text, whiteSpace: "nowrap" }}>${fmt(l.line_total)}</div>
                  <button onClick={() => { setPayErr(""); setQuickPayLine(l); }} title="Cobrar ítem"
                    style={{ background: C.greenBg, border: `1px solid ${C.greenBd}`, borderRadius: 4, cursor: "pointer", color: C.green, padding: "2px 4px", display: "flex", alignItems: "center" }}>
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                  </button>
                  <button onClick={() => { setConfirmDeleteLine(l.id); setCancelReason(""); setPayErr(""); }} disabled={deletingLine === l.id}
                    style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex", opacity: deletingLine === l.id ? 0.4 : 1 }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
                  </button>
                </div>
                {confirmDeleteLine === l.id && (
                  <div style={{ padding: "6px 0 10px", display: "flex", flexDirection: "column", gap: 6 }}>
                    <input
                      value={cancelReason}
                      onChange={e => setCancelReason(e.target.value)}
                      placeholder="Motivo de cancelación (obligatorio)"
                      autoFocus
                      style={{
                        width: "100%", padding: "8px 10px", border: `1px solid ${C.redBd}`,
                        borderRadius: C.r, fontSize: 12, background: C.redBg, outline: "none",
                        fontFamily: "inherit", color: C.text,
                      }}
                    />
                    <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                      <button onClick={() => { setConfirmDeleteLine(null); setCancelReason(""); }}
                        style={{ padding: "4px 12px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: "pointer", fontSize: 11, fontWeight: 600, fontFamily: "inherit", color: C.mid }}>
                        Cancelar
                      </button>
                      <button onClick={() => deleteLine(l.id)} disabled={deletingLine === l.id || !cancelReason.trim()}
                        style={{ padding: "4px 12px", borderRadius: C.r, border: "none", background: C.red, cursor: cancelReason.trim() ? "pointer" : "not-allowed", fontSize: 11, fontWeight: 600, fontFamily: "inherit", color: "#fff", opacity: cancelReason.trim() ? 1 : 0.5 }}>
                        {deletingLine === l.id ? <Spinner size={10} /> : "Confirmar eliminación"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, paddingTop: 8, borderTop: `1px solid ${C.border}` }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: C.mid }}>Total pendiente</span>
              <span style={{ fontSize: 15, fontWeight: 800, color: C.text }}>${fmt(order.subtotal_unpaid)}</span>
            </div>
          </div>
        )}

        {/* Cancelled lines */}
        {cancelledLines.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.red, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
              Cancelado ({cancelledLines.length})
            </div>
            {cancelledLines.map(l => (
              <div key={l.id} style={{ padding: "4px 0" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, opacity: 0.5 }}>
                  <span style={{ flex: 1, fontSize: 11, color: C.red, textDecoration: "line-through" }}>{l.product_name}</span>
                  <span style={{ fontSize: 11, color: C.red, textDecoration: "line-through" }}>${fmt(l.line_total)}</span>
                </div>
                {l.cancel_reason && (
                  <div style={{ fontSize: 10, color: C.red, marginTop: 2, paddingLeft: 2, fontStyle: "italic", opacity: 0.7 }}>
                    Motivo: {l.cancel_reason}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Paid lines */}
        {paidLines.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
              Cobrado ({paidLines.length})
            </div>
            {paidLines.map(l => (
              <div key={l.id} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 0", opacity: 0.4 }}>
                <span style={{ flex: 1, fontSize: 11, color: C.mid, textDecoration: "line-through" }}>{l.product_name}</span>
                <span style={{ fontSize: 11, color: C.mute, textDecoration: "line-through" }}>${fmt(l.line_total)}</span>
              </div>
            ))}
          </div>
        )}

        {order.lines.length === 0 && (
          <div style={{ textAlign: "center", color: C.mute, fontSize: 12, padding: "20px 0" }}>Sin ítems — agrega productos.</div>
        )}

        {/* Add item toggle */}
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
          <button onClick={() => setShowAddItem(s => !s)} style={{
            background: "none", border: `1px dashed ${C.borderMd}`, borderRadius: C.r,
            width: "100%", padding: "8px", cursor: "pointer", color: C.mid, fontSize: 12,
            fontWeight: 600, fontFamily: "inherit", display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            {showAddItem ? "Cerrar" : "Agregar ítems"}
          </button>
          {showAddItem && <div style={{ marginTop: 10 }}><AddItemPanel orderId={order.id} onAdded={() => { setShowAddItem(false); onRefresh(); }} /></div>}
        </div>
      </div>

      {/* Footer */}
      {(payErr || cancelErr) && <div style={{ margin: "0 16px 6px", padding: "6px 10px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 11 }}>{payErr || cancelErr}</div>}
      <div style={{ padding: "10px 16px", borderTop: `1px solid ${C.border}`, display: "flex", gap: 8 }}>
        {unpaidLines.length === 0 && (
          <Btn variant="danger" disabled={cancelling} onClick={cancelOrder}>
            {cancelling ? <Spinner size={13} /> : null}
            Cerrar mesa
          </Btn>
        )}
        {unpaidLines.length > 0 && (
          <Btn variant="primary" full size="lg" onClick={() => { setPayErr(""); setShowPayment(true); }}>
            Cobrar ${fmt(order.subtotal_unpaid)}
          </Btn>
        )}
      </div>

      {showPayment && (
        <PaymentModal total={Number(order.subtotal_unpaid)} tableName={order.customer_name || tableName}
          unpaidLines={unpaidLines} onClose={() => setShowPayment(false)}
          loading={payLoading} onConfirm={handleCheckout} canConsumoInterno={canConsumoInterno} />
      )}
      {quickPayLine && (
        <PaymentModal total={Number(quickPayLine.line_total)} tableName={`${quickPayLine.product_name}`}
          unpaidLines={[quickPayLine]} onClose={() => setQuickPayLine(null)}
          loading={payLoading} onConfirm={(payments, tip, _mode, _lineIds) => {
            handleCheckout(payments, tip, "partial", [quickPayLine.id]);
            setQuickPayLine(null);
          }} />
      )}
    </div>
  );
}

// ─── Salon Summary (right panel when no table selected) ──────────────────────
function SalonSummary({ tables, allOrders, onSelectTable }: {
  tables: Table[];
  allOrders: Record<number, Order>;
  onSelectTable: (t: Table) => void;
}) {
  const openTables = tables.filter(t => t.status === "OPEN" && t.active_order);
  const totalSalon = openTables.reduce((s, t) => s + Number(t.active_order?.subtotal || 0), 0);

  return (
    <div style={{ padding: "16px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 16 }}>{"\uD83D\uDCCB"}</span>
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
          <div style={{ fontSize: 36, marginBottom: 10 }}>{"\uD83C\uDF7D\uFE0F"}</div>
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
                    <span style={{ fontSize: 14 }}>{t.is_counter ? "\uD83D\uDCE6" : "\uD83E\uDE91"}</span>
                    <span style={{ fontWeight: 700, fontSize: 13, color: C.text }}>
                      {(t.is_counter && t.active_order?.customer_name) ? t.active_order.customer_name : t.name}
                    </span>
                    {t.is_counter && t.active_order?.customer_name && <span style={{ fontSize: 10, color: C.mute }}>· {t.name}</span>}
                    {!t.is_counter && t.zone && <span style={{ fontSize: 10, color: C.mute }}>· {t.zone}</span>}
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
                        {l.product_name} ×{l.qty}{l.note ? " *" : ""}
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
                    {t.active_order?.items_count || 0} ítem{(t.active_order?.items_count || 0) !== 1 ? "s" : ""}
                  </div>
                ) : null}

                {/* Footer: time */}
                <div style={{ fontSize: 10, color: C.mute, display: "flex", alignItems: "center", gap: 4 }}>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  {t.active_order ? timeAgo(t.active_order.opened_at) : ""}
                  {t.active_order && <> · {t.active_order.items_count} ítem{t.active_order.items_count !== 1 ? "s" : ""}</>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function MesasPage() {
  useStyles();
  const mob = useIsMobile();

  const [tables, setTables] = useState<Table[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTable, setSelectedTable] = useState<Table | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [orderLoading, setOrderLoading] = useState(false);
  const [openingTable, setOpeningTable] = useState<number | null>(null);
  const [openErr, setOpenErr] = useState("");
  const [activeZone, setActiveZone] = useState<string>("__all__");
  const [counterLoading, setCounterLoading] = useState(false);
  const [allOrders, setAllOrders] = useState<Record<number, Order>>({});
  const [showCounterModal, setShowCounterModal] = useState(false);
  const [counterName, setCounterName] = useState("");
  const [userRole, setUserRole] = useState("");

  // Fetch user role for consumo interno permission
  useEffect(() => {
    apiFetch("/core/me/").then(d => setUserRole(d?.role || "")).catch(() => setUserRole(""));
  }, []);

  // Load all tables
  const loadTables = useCallback(async () => {
    try {
      const data = await apiFetch("/tables/tables/");
      setTables(data || []);
      return data || [];
    } catch (e: any) { setOpenErr(e?.message || "Error al cargar mesas"); return []; } finally { setLoading(false); }
  }, []);

  // Load all open orders (for summary panel)
  const loadAllOrders = useCallback(async (tbls: Table[]) => {
    const openTables = tbls.filter(t => t.status === "OPEN" && t.active_order);
    if (openTables.length === 0) { setAllOrders({}); return; }
    try {
      const orders = await Promise.all(
        openTables.map(t => apiFetch(`/tables/tables/${t.id}/order/`).catch(() => null))
      );
      const map: Record<number, Order> = {};
      openTables.forEach((t, i) => { if (orders[i]) map[t.id] = orders[i]; });
      setAllOrders(map);
    } catch {}
  }, []);

  // Initial load + auto-refresh
  useEffect(() => {
    let active = true;
    async function refresh() {
      const tbls = await loadTables();
      if (active) await loadAllOrders(tbls);
    }
    refresh();
    const id = setInterval(refresh, 20_000);
    return () => { active = false; clearInterval(id); };
  }, [loadTables, loadAllOrders]);

  // Separate regular and counter tables
  const regularTables = tables.filter(t => !t.is_counter);
  const counterOrders = tables.filter(t => t.is_counter && t.status === "OPEN");

  // Zones
  const zones = [...new Set(regularTables.map(t => t.zone).filter(Boolean))].sort();
  const filteredTables = activeZone === "__all__" ? regularTables : regularTables.filter(t => t.zone === activeZone);

  const freeCount = regularTables.filter(t => t.status === "FREE").length;
  const occupiedCount = regularTables.filter(t => t.status === "OPEN").length;

  async function loadOrder(tableId: number) {
    setOrderLoading(true); setOrder(null);
    try { const data = await apiFetch(`/tables/tables/${tableId}/order/`); setOrder(data); }
    catch (e: any) { setOrder(null); setOpenErr(e?.message || "Error al cargar la orden"); }
    finally { setOrderLoading(false); }
  }

  async function selectTable(table: Table) {
    setSelectedTable(table);
    setOpenErr("");
    if (table.status === "OPEN") { await loadOrder(table.id); } else { setOrder(null); }
  }

  async function openOrder(table: Table) {
    setOpeningTable(table.id); setOpenErr("");
    try {
      const data = await apiFetch(`/tables/tables/${table.id}/open/`, { method: "POST", body: JSON.stringify({}) });
      setOrder(data);
      const tbls = await loadTables();
      await loadAllOrders(tbls);
      setSelectedTable(t => t ? { ...t, status: "OPEN" } : t);
    } catch (e: any) {
      setOpenErr(e?.message || "Error al abrir la mesa");
    } finally { setOpeningTable(null); }
  }

  async function createCounterOrder(customerName: string) {
    setCounterLoading(true); setOpenErr("");
    try {
      const data = await apiFetch("/tables/counter-order/", {
        method: "POST",
        body: JSON.stringify({ customer_name: customerName.trim() }),
      });
      const tbls = await loadTables();
      await loadAllOrders(tbls);
      const ct: Table = {
        id: data.table_id, name: data.table_name, capacity: 1, status: "OPEN",
        is_active: true, zone: "", is_counter: true,
        active_order: { id: data.id, opened_at: data.opened_at, items_count: 0, subtotal: "0", customer_name: customerName.trim() },
      };
      setSelectedTable(ct);
      setOrder(data);
    } catch (e: any) {
      setOpenErr(e?.message || "Error al crear pedido");
    } finally { setCounterLoading(false); }
  }

  async function refreshOrder() {
    const tbls = await loadTables();
    await loadAllOrders(tbls);
    if (!selectedTable) return;
    const t = tbls.find((x: Table) => x.id === selectedTable.id);
    if (t) {
      setSelectedTable(t);
      if (t.status === "FREE") { setOrder(null); } else { await loadOrder(t.id); }
    } else {
      setSelectedTable(null); setOrder(null);
    }
  }

  const HEADER_H = 100;

  return (
    <div style={{ height: mob ? "auto" : "100vh", minHeight: "100vh", display: "flex", flexDirection: "column", fontFamily: "'DM Sans', 'Helvetica Neue', system-ui, sans-serif", background: C.bg, overflow: mob ? undefined : "hidden" }}>

      {/* ── Header ────────────────────────────────────────────────────── */}
      <div style={{ padding: "14px 20px 10px", borderBottom: `1px solid ${C.border}`, background: C.surface, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 800, color: C.text, margin: 0 }}>Mesas</h1>
            <div style={{ fontSize: 12, color: C.mute, marginTop: 1 }}>
              <span style={{ color: C.amber, fontWeight: 600 }}>{occupiedCount}</span> ocupada{occupiedCount !== 1 ? "s" : ""}
              {" · "}<span style={{ color: C.green, fontWeight: 600 }}>{freeCount}</span> libre{freeCount !== 1 ? "s" : ""}
              {counterOrders.length > 0 && <> · <span style={{ fontWeight: 600 }}>{counterOrders.length}</span> para llevar</>}
            </div>
          </div>
          <a href="/dashboard/mesas/config" style={{ textDecoration: "none" }}>
            <Btn variant="secondary" size="sm">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
              Config
            </Btn>
          </a>
        </div>

        {/* Zone tabs */}
        {zones.length > 0 && (
          <div style={{ display: "flex", gap: 4, overflowX: "auto" }}>
            <button onClick={() => setActiveZone("__all__")} style={{
              padding: "5px 14px", borderRadius: 99, fontSize: 12, fontWeight: 600,
              border: `1px solid ${activeZone === "__all__" ? C.accent : C.border}`,
              background: activeZone === "__all__" ? C.accent : C.surface,
              color: activeZone === "__all__" ? "#fff" : C.mid,
              cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
            }}>
              Todas
            </button>
            {zones.map(z => (
              <button key={z} onClick={() => setActiveZone(z)} style={{
                padding: "5px 14px", borderRadius: 99, fontSize: 12, fontWeight: 600,
                border: `1px solid ${activeZone === z ? C.accent : C.border}`,
                background: activeZone === z ? C.accent : C.surface,
                color: activeZone === z ? "#fff" : C.mid,
                cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
              }}>
                {z}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Error */}
      {openErr && (
        <div style={{ margin: "8px 20px 0", padding: "8px 14px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 12, fontWeight: 500 }}>
          {openErr}
        </div>
      )}

      {/* ── Split layout ──────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: "flex", flexDirection: mob ? "column" : "row", overflow: mob ? "auto" : "hidden" }}>

        {/* LEFT PANEL — Table grid */}
        <div style={{ flex: mob ? undefined : "1 1 55%", overflowY: "auto", padding: "14px 16px", borderRight: mob ? undefined : `1px solid ${C.border}`, borderBottom: mob ? `1px solid ${C.border}` : undefined }}>
          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: 40, color: C.mute }}><Spinner size={24} /></div>
          ) : regularTables.length === 0 && counterOrders.length === 0 ? (
            <div style={{ textAlign: "center", padding: "40px 20px" }}>
              <div style={{ fontSize: 36, marginBottom: 10 }}>{"\uD83C\uDF7D\uFE0F"}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginBottom: 4 }}>Sin mesas configuradas</div>
              <div style={{ fontSize: 12, color: C.mute, marginBottom: 16 }}>Configura tus mesas para empezar.</div>
              <a href="/dashboard/mesas/config" style={{ textDecoration: "none" }}><Btn variant="primary">Configurar mesas</Btn></a>
            </div>
          ) : (
            <>
              {/* Table grid */}
              {filteredTables.length > 0 ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
                  {filteredTables.map(t => (
                    <TableCard key={t.id} table={t} selected={selectedTable?.id === t.id} onClick={() => selectTable(t)} />
                  ))}
                </div>
              ) : regularTables.length > 0 ? (
                <div style={{ textAlign: "center", padding: 24, color: C.mute, fontSize: 12 }}>No hay mesas en esta zona.</div>
              ) : null}

              {/* Counter / Takeaway */}
              <div style={{ marginTop: 16, paddingTop: 14, borderTop: `1px solid ${C.border}` }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 14 }}>{"\uD83D\uDCE6"}</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Para llevar</span>
                    {counterOrders.length > 0 && (
                      <span style={{ padding: "1px 7px", borderRadius: 99, fontSize: 10, fontWeight: 700, background: C.amberBg, color: C.amber, border: `1px solid ${C.amberBd}` }}>
                        {counterOrders.length}
                      </span>
                    )}
                  </div>
                  <Btn variant="primary" size="sm" disabled={counterLoading} onClick={() => { setCounterName(""); setShowCounterModal(true); }}>
                    {counterLoading ? <Spinner size={12} /> : <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>}
                    Nuevo
                  </Btn>
                </div>

                {counterOrders.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {counterOrders.map(t => {
                      const isSel = selectedTable?.id === t.id;
                      return (
                        <div key={t.id} onClick={() => selectTable(t)} style={{
                          display: "flex", alignItems: "center", gap: 10,
                          padding: "10px 12px", borderRadius: C.r,
                          background: isSel ? C.accentBg : C.surface,
                          border: `1px solid ${isSel ? C.accent : C.border}`,
                          cursor: "pointer",
                        }}>
                          <span style={{ fontSize: 14 }}>{"\uD83D\uDCE6"}</span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>
                              {t.active_order?.customer_name || t.name}
                            </div>
                            <div style={{ fontSize: 10, color: C.mute }}>
                              {t.active_order?.customer_name && <span style={{ color: C.mid }}>{t.name} · </span>}
                              {t.active_order ? `${t.active_order.items_count} ítem${t.active_order.items_count !== 1 ? "s" : ""} · ${timeAgo(t.active_order.opened_at)}` : ""}
                            </div>
                          </div>
                          {t.active_order && Number(t.active_order.subtotal) > 0 && (
                            <span style={{ fontWeight: 800, fontSize: 13, color: C.text }}>${fmt(t.active_order.subtotal)}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div style={{ padding: 12, textAlign: "center", color: C.mute, fontSize: 11, background: C.surface, borderRadius: C.r, border: `1px solid ${C.border}` }}>
                    Sin pedidos para llevar activos.
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Counter order modal */}
        {showCounterModal && (
          <Modal title="Nuevo pedido para llevar" onClose={() => setShowCounterModal(false)} width={380}>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 6 }}>
                Nombre del cliente <span style={{ color: C.mute, fontWeight: 400 }}>(opcional)</span>
              </label>
              <input value={counterName} onChange={e => setCounterName(e.target.value)} placeholder="Ej: Juan, María..."
                autoFocus
                onKeyDown={e => { if (e.key === "Enter") { setShowCounterModal(false); createCounterOrder(counterName); } }}
                style={{ width: "100%", padding: "10px 12px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 14, fontFamily: "inherit", outline: "none" }} />
              <div style={{ fontSize: 11, color: C.mute, marginTop: 4 }}>
                Se mostrará en la comanda para identificar al cliente.
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <Btn variant="secondary" onClick={() => setShowCounterModal(false)}>Cancelar</Btn>
              <Btn variant="primary" full disabled={counterLoading} onClick={() => { setShowCounterModal(false); createCounterOrder(counterName); }}>
                {counterLoading ? <Spinner size={13} /> : null}
                Crear pedido
              </Btn>
            </div>
          </Modal>
        )}

        {/* RIGHT PANEL — Order detail or salon summary */}
        <div style={{ flex: mob ? undefined : "1 1 45%", overflowY: "auto", background: C.surface, display: "flex", flexDirection: "column", minHeight: mob ? 300 : undefined }}>
          {selectedTable ? (
            selectedTable.status === "FREE" ? (
              /* Free table — open order prompt */
              <div style={{ padding: 20, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1 }}>
                <span style={{ fontSize: 36, marginBottom: 10 }}>{"\uD83E\uDE91"}</span>
                <div style={{ fontWeight: 700, fontSize: 16, color: C.text, marginBottom: 2 }}>{selectedTable.name}</div>
                <div style={{ fontSize: 12, color: C.mute, marginBottom: 20 }}>
                  {selectedTable.zone ? `${selectedTable.zone} · ` : ""}{selectedTable.capacity} personas · Libre
                </div>
                {openErr && <div style={{ marginBottom: 12, padding: "6px 10px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 11, width: "100%", maxWidth: 280 }}>{openErr}</div>}
                <Btn variant="primary" size="lg" disabled={openingTable === selectedTable.id} onClick={() => openOrder(selectedTable)}>
                  {openingTable === selectedTable.id ? <Spinner size={14} /> : null}
                  {openingTable === selectedTable.id ? "Abriendo…" : "Abrir comanda"}
                </Btn>
                <div style={{ marginTop: 8 }}>
                  <Btn variant="ghost" size="sm" onClick={() => setSelectedTable(null)}>← Volver al resumen</Btn>
                </div>
              </div>
            ) : orderLoading ? (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", flex: 1 }}><Spinner size={22} /></div>
            ) : order ? (
              <OrderPanel order={order} tableName={selectedTable.name} isCounter={selectedTable.is_counter}
                onRefresh={refreshOrder} onClose={() => { setSelectedTable(null); setOrder(null); }}
                onOrderUpdate={(o) => setOrder(o)} canConsumoInterno={userRole === "owner" || userRole === "manager"} />
            ) : null
          ) : (
            /* No selection — salon summary */
            <SalonSummary tables={tables} allOrders={allOrders} onSelectTable={selectTable} />
          )}
        </div>
      </div>
    </div>
  );
}
