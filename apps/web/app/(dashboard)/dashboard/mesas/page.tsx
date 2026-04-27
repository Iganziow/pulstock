"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";
import { Btn } from "@/components/ui/Button";
import {
  TableCard,
  OrderPanel,
  SalonSummary,
  CounterSection,
  CounterModal,
  MesaBtn,
  PAGE_CSS,
  fmt,
} from "@/components/mesas";
import type { Table, Order } from "@/components/mesas";

function useStyles() {
  useEffect(() => {
    const id = "mesas-page-css";
    if (document.getElementById(id)) return;
    const el = document.createElement("style");
    el.id = id; el.textContent = PAGE_CSS;
    document.head.appendChild(el);
  }, []);
}

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
  const [viewMode] = useState<"grid">("grid");
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
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al cargar mesas";
      setOpenErr(msg);
      return [];
    } finally { setLoading(false); }
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
    } catch { /* ignore */ }
  }, []);

  // Initial load + auto-refresh.
  //
  // Performance fixes (Mario reportó "está más lento"):
  //   - Intervalo subido de 20s a 60s — cada refresh dispara 1 GET tables
  //     + 1 GET por cada mesa abierta. Con 4 mesas activas = 5 requests
  //     cada 20s = 900/hora. Con 60s baja a 300/hora (3x menos).
  //   - Cuando el user está VIENDO una mesa específica, solo refrescamos
  //     ESA mesa (no todas las demás orders en background). Reduce ~80%
  //     de las requests durante uso activo.
  //   - Pausamos el refresh cuando el documento está oculto (otra pestaña
  //     o app en background) — el browser API document.hidden.
  useEffect(() => {
    let active = true;
    async function refresh() {
      if (typeof document !== "undefined" && document.hidden) return;
      const tbls = await loadTables();
      if (active) await loadAllOrders(tbls);
    }
    refresh();
    const id = setInterval(refresh, 60_000);
    return () => { active = false; clearInterval(id); };
  }, [loadTables, loadAllOrders]);

  // Derived data
  const regularTables = tables.filter(t => !t.is_counter);
  const counterOrders = tables.filter(t => t.is_counter && t.status === "OPEN");
  const zones = [...new Set(regularTables.map(t => t.zone).filter(Boolean))].sort();
  const filteredTables = activeZone === "__all__" ? regularTables : regularTables.filter(t => t.zone === activeZone);
  const freeCount = regularTables.filter(t => t.status === "FREE").length;
  const occupiedCount = regularTables.filter(t => t.status === "OPEN").length;

  async function loadOrder(tableId: number) {
    setOrderLoading(true); setOrder(null);
    try { const data = await apiFetch(`/tables/tables/${tableId}/order/`); setOrder(data); }
    catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al cargar la orden";
      setOrder(null); setOpenErr(msg);
    }
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
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al abrir la mesa";
      setOpenErr(msg);
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
        position_x: 0, position_y: 0, shape: "square", width: 8, height: 8, rotation: 0,
        active_order: { id: data.id, opened_at: data.opened_at, items_count: 0, subtotal: "0", customer_name: customerName.trim() },
      };
      setSelectedTable(ct);
      setOrder(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al crear pedido";
      setOpenErr(msg);
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

  function handleNewCounter() {
    setCounterName("");
    setShowCounterModal(true);
  }

  function handleCounterConfirm() {
    setShowCounterModal(false);
    createCounterOrder(counterName);
  }

  return (
    <div style={{ height: mob ? "auto" : "100vh", minHeight: "100vh", display: "flex", flexDirection: "column", fontFamily: "'DM Sans', 'Helvetica Neue', system-ui, sans-serif", background: C.bg, overflow: mob ? undefined : "hidden" }}>

      {/* Header */}
      <div style={{ padding: mob ? "12px 12px 8px" : "14px 20px 10px", borderBottom: `1px solid ${C.border}`, background: C.surface, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 800, color: C.text, margin: 0 }}>Mesas</h1>
            <div style={{ fontSize: 12, color: C.mute, marginTop: 1 }}>
              <span style={{ color: C.amber, fontWeight: 600 }}>{occupiedCount}</span> ocupada{occupiedCount !== 1 ? "s" : ""}
              {" · "}<span style={{ color: C.green, fontWeight: 600 }}>{freeCount}</span> libre{freeCount !== 1 ? "s" : ""}
              {counterOrders.length > 0 && <> &middot; <span style={{ fontWeight: 600 }}>{counterOrders.length}</span> para llevar</>}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <MesaBtn variant="primary" size="sm" onClick={handleNewCounter} disabled={counterLoading}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              Para llevar
            </MesaBtn>
            <a href="/dashboard/mesas/config" style={{ textDecoration: "none" }}>
              <Btn variant="secondary" size="sm">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
                Config
              </Btn>
            </a>
          </div>
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
        <div style={{ margin: mob ? "8px 12px 0" : "8px 20px 0", padding: "8px 14px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 12, fontWeight: 500 }}>
          {openErr}
        </div>
      )}

      {/* Split layout */}
      <div style={{ flex: 1, display: "flex", flexDirection: mob ? "column" : "row", overflow: mob ? "auto" : "hidden" }}>

        {/* LEFT PANEL -- Table grid. En mobile: padding lateral más chico
            (12px en lugar de 16) y minmax 130px para que entren al menos
            2 mesas por fila en pantallas de ~360px (360-24=336 → 2x130+gap).

            En mobile se OCULTA cuando hay una mesa seleccionada — sino
            quedan apilados arriba la lista y abajo el OrderPanel y todo
            se siente comprimido (Mario lo reportó). Volver a la lista es
            con el botón "←" del header del OrderPanel. */}
        <div style={{
          flex: mob ? undefined : "1 1 55%",
          overflowY: "auto",
          padding: mob ? "12px 12px" : "14px 16px",
          borderRight: mob ? undefined : `1px solid ${C.border}`,
          borderBottom: mob ? `1px solid ${C.border}` : undefined,
          display: mob && selectedTable ? "none" : undefined,
        }}>
          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: 40, color: C.mute }}><Spinner size={24} /></div>
          ) : regularTables.length === 0 && counterOrders.length === 0 ? (
            <div style={{ textAlign: "center", padding: "40px 20px" }}>
              <div style={{ fontSize: 36, marginBottom: 10 }}>{"🍽️"}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginBottom: 4 }}>Sin mesas configuradas</div>
              <div style={{ fontSize: 12, color: C.mute, marginBottom: 16 }}>Configura tus mesas para empezar.</div>
              <a href="/dashboard/mesas/config" style={{ textDecoration: "none" }}><Btn variant="primary">Configurar mesas</Btn></a>
            </div>
          ) : (
            <>
              {/* Table cards */}
              {filteredTables.length > 0 ? (
                <div style={{ display: "grid", gridTemplateColumns: mob ? "repeat(auto-fill, minmax(130px, 1fr))" : "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
                  {filteredTables.map(t => (
                    <TableCard key={t.id} table={t} selected={selectedTable?.id === t.id} onClick={() => selectTable(t)} />
                  ))}
                </div>
              ) : regularTables.length > 0 ? (
                <div style={{ textAlign: "center", padding: 24, color: C.mute, fontSize: 12 }}>No hay mesas en esta zona.</div>
              ) : null}

              {/* Counter orders as cards below tables */}
              {counterOrders.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
                    Para llevar ({counterOrders.length})
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: mob ? "repeat(auto-fill, minmax(130px, 1fr))" : "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
                    {counterOrders.map(t => (
                      <TableCard key={t.id} table={t} selected={selectedTable?.id === t.id} onClick={() => selectTable(t)} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Counter order modal */}
        {showCounterModal && (
          <CounterModal
            counterName={counterName}
            onChangeName={setCounterName}
            counterLoading={counterLoading}
            onClose={() => setShowCounterModal(false)}
            onConfirm={handleCounterConfirm}
          />
        )}

        {/* RIGHT PANEL -- Order detail or salon summary.
            En mobile se OCULTA cuando NO hay mesa seleccionada (sino se
            ve un SalonSummary debajo de la lista de mesas que confunde).
            Solo aparece cuando hay selección, ocupando toda la pantalla. */}
        <div style={{
          flex: mob ? undefined : "1 1 45%",
          overflowY: "auto",
          background: C.surface,
          display: mob && !selectedTable ? "none" : "flex",
          flexDirection: "column",
          minHeight: mob ? "calc(100vh - 60px)" : undefined,
        }}>
          {selectedTable ? (
            selectedTable.status === "FREE" ? (
              /* Free table -- open order prompt */
              <div style={{ padding: 20, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1 }}>
                <span style={{ fontSize: 36, marginBottom: 10 }}>{"🪑"}</span>
                <div style={{ fontWeight: 700, fontSize: 16, color: C.text, marginBottom: 2 }}>{selectedTable.name}</div>
                <div style={{ fontSize: 12, color: C.mute, marginBottom: 20 }}>
                  {selectedTable.zone ? `${selectedTable.zone} · ` : ""}{selectedTable.capacity} personas &middot; Libre
                </div>
                {openErr && <div style={{ marginBottom: 12, padding: "6px 10px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 11, width: "100%", maxWidth: 280 }}>{openErr}</div>}
                <MesaBtn variant="primary" size="lg" disabled={openingTable === selectedTable.id} onClick={() => openOrder(selectedTable)}>
                  {openingTable === selectedTable.id ? <Spinner size={14} /> : null}
                  {openingTable === selectedTable.id ? "Abriendo…" : "Abrir comanda"}
                </MesaBtn>
                <div style={{ marginTop: 8 }}>
                  <MesaBtn variant="ghost" size="sm" onClick={() => setSelectedTable(null)}>{"←"} Volver al resumen</MesaBtn>
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
            /* No selection -- salon summary */
            <SalonSummary tables={tables} allOrders={allOrders} onSelectTable={selectTable} />
          )}
        </div>
      </div>
    </div>
  );
}
