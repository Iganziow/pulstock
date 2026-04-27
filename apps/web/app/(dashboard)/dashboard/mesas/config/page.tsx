"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";


const PAGE_CSS = `
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
@keyframes fadeIn{from{opacity:0;transform:scale(0.97)}to{opacity:1;transform:scale(1)}}
*{box-sizing:border-box;}
`;

function useStyles() {
  useEffect(() => {
    const id = "mesas-config-css";
    if (document.getElementById(id)) return;
    const el = document.createElement("style");
    el.id = id; el.textContent = PAGE_CSS;
    document.head.appendChild(el);
  }, []);
}

// ─── Types ────────────────────────────────────────────────────────────────────
import type { Table } from "@/components/mesas/types";
// NOTE: FloorPlanEditor (vista "Distribuir mesas") existe pero no se expone en
// producción. Es una herramienta interna nuestra para probar layouts visuales.
// Mario y los clientes usan la vista de cards (Lista de mesas), que es más
// simple y funciona en cualquier dispositivo.
import { humanizeError } from "@/lib/errors";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function Btn({ children, onClick, variant = "secondary", disabled, size = "md" }: {
  children: React.ReactNode; onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost"; disabled?: boolean; size?: "sm" | "md";
}) {
  const vs = {
    primary:   { background: C.accent, color: "#fff", border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text, border: `1px solid ${C.borderMd}` },
    danger:    { background: C.redBg, color: C.red, border: `1px solid ${C.redBd}` },
    ghost:     { background: "transparent", color: C.mid, border: "1px solid transparent" },
  }[variant];
  const pad = size === "sm" ? "5px 12px" : "9px 18px";
  const fs = size === "sm" ? 12 : 14;
  return (
    <button onClick={onClick} disabled={disabled} style={{
      ...vs, padding: pad, borderRadius: C.r, fontSize: fs, fontWeight: 600,
      cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
      display: "inline-flex", alignItems: "center", gap: 6,
      transition: "all 0.13s ease", fontFamily: "inherit",
    }}>
      {children}
    </button>
  );
}

function Modal({ title, onClose, children, width = 400 }: {
  title: string; onClose: () => void; children: React.ReactNode; width?: number;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: C.surface, borderRadius: C.rMd, width: "100%", maxWidth: width, boxShadow: C.shMd, animation: "fadeIn 0.18s ease" }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: `1px solid ${C.border}` }}>
          <span style={{ fontWeight: 700, fontSize: 16, color: C.text }}>{title}</span>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 4, display: "flex" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div style={{ padding: "20px" }}>{children}</div>
      </div>
    </div>
  );
}

// ─── Table Form Modal ──────────────────────────────────────────────────────────
function TableFormModal({
  table, onClose, onSaved,
}: {
  table?: Table; // undefined = create mode
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!table;
  const [name, setName] = useState(table?.name || "");
  const [capacity, setCapacity] = useState(String(table?.capacity || 4));
  const [zone, setZone] = useState(table?.zone || "");
  const [shape, setShape] = useState<"round" | "square" | "rect">(table?.shape || "square");
  const [isCounter, setIsCounter] = useState(table?.is_counter || false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [err, setErr] = useState("");

  async function save() {
    if (!name.trim()) { setErr("El nombre es requerido"); return; }
    setSaving(true); setErr("");
    const body = { name: name.trim(), capacity: Number(capacity) || 4, zone: zone.trim(), is_counter: isCounter, shape };
    try {
      if (isEdit) {
        await apiFetch(`/tables/tables/${table!.id}/`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        await apiFetch("/tables/tables/", { method: "POST", body: JSON.stringify(body) });
      }
      onSaved();
      onClose();
    } catch (e: any) {
      setErr(humanizeError(e, "Error al guardar"));
    } finally { setSaving(false); }
  }

  return (
    <Modal title={isEdit ? `Editar: ${table!.name}` : "Nueva mesa"} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: C.mid, display: "block", marginBottom: 4 }}>Nombre</label>
          <input
            value={name} onChange={e => setName(e.target.value)} autoFocus
            onKeyDown={e => e.key === "Enter" && save()}
            placeholder="Mesa 1, Barra, Terraza…"
            style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 14, fontFamily: "inherit", outline: "none" }}
          />
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: C.mid, display: "block", marginBottom: 4 }}>Capacidad (personas)</label>
            <input
              type="number" min="1" value={capacity} onChange={e => setCapacity(e.target.value)}
              style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 14, fontFamily: "inherit", outline: "none" }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: C.mid, display: "block", marginBottom: 4 }}>Zona</label>
            <input
              value={zone} onChange={e => setZone(e.target.value)}
              placeholder="Salón Grande, Ventanas…"
              style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 14, fontFamily: "inherit", outline: "none" }}
            />
          </div>
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", padding: "8px 12px", borderRadius: C.r, border: `1px solid ${isCounter ? C.accentBd : C.border}`, background: isCounter ? C.accentBg : C.surface }}>
          <button
            type="button"
            onClick={() => setIsCounter(v => !v)}
            style={{
              width: 36, height: 20, borderRadius: 10, border: "none",
              background: isCounter ? C.accent : C.borderMd,
              cursor: "pointer", position: "relative", transition: "background 0.2s ease", flexShrink: 0,
            }}
          >
            <div style={{
              position: "absolute", top: 2, left: isCounter ? 18 : 2,
              width: 16, height: 16, borderRadius: "50%", background: "#fff",
              transition: "left 0.2s ease", boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
            }} />
          </button>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>Posición de mostrador</div>
            <div style={{ fontSize: 11, color: C.mute }}>Para pedidos de mostrador / para llevar</div>
          </div>
        </label>
        {/* Shape selector */}
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: C.mid, display: "block", marginBottom: 6 }}>Forma en el plano</label>
          <div style={{ display: "flex", gap: 6 }}>
            {([["round", "Redonda", "⬤"], ["square", "Cuadrada", "⬛"], ["rect", "Rectangular", "▬"]] as const).map(([sh, label, icon]) => (
              <button key={sh} type="button" onClick={() => setShape(sh)} style={{
                flex: 1, padding: "10px 0", borderRadius: 8, cursor: "pointer", fontFamily: "inherit",
                border: `2px solid ${shape === sh ? C.accent : C.border}`,
                background: shape === sh ? C.accentBg : C.surface,
                color: shape === sh ? C.accent : C.mid,
                display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
              }}>
                <span style={{ fontSize: 18 }}>{icon}</span>
                <span style={{ fontSize: 10, fontWeight: 600 }}>{label}</span>
              </button>
            ))}
          </div>
        </div>

        {err && <div style={{ fontSize: 12, color: C.red }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: isEdit ? "space-between" : "flex-end" }}>
          {isEdit && (
            <Btn variant="danger" disabled={deleting || table!.status === "OPEN"} onClick={async () => {
              if (!confirm(`¿Eliminar "${table!.name}"? Esta acción no se puede deshacer.`)) return;
              setDeleting(true);
              try {
                await apiFetch(`/tables/tables/${table!.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: false }) });
                onSaved(); onClose();
              } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Error al eliminar"); }
              finally { setDeleting(false); }
            }}>
              {deleting ? "Eliminando…" : "Eliminar"}
            </Btn>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <Btn variant="secondary" onClick={onClose}>Cancelar</Btn>
            <Btn variant="primary" disabled={saving} onClick={save}>
              {saving ? <Spinner size={14} /> : null}
              {saving ? "Guardando…" : isEdit ? "Guardar" : "Crear mesa"}
            </Btn>
          </div>
        </div>
      </div>
    </Modal>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function MesasConfigPage() {
  useStyles();
  const mob = useIsMobile();

  const [tables, setTables] = useState<Table[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingTable, setEditingTable] = useState<Table | undefined>(undefined);
  const [showFormModal, setShowFormModal] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [err, setErr] = useState("");

  const loadTables = useCallback(async () => {
    try {
      const data = await apiFetch("/tables/tables/");
      setTables(data || []);
    } catch (e) { console.error("MesasConfig: error cargando mesas:", e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadTables(); }, [loadTables]);

  function openCreate() { setEditingTable(undefined); setShowFormModal(true); }
  function openEdit(t: Table) { setEditingTable(t); setShowFormModal(true); }

  async function toggleActive(table: Table) {
    if (table.status === "OPEN" && table.is_active) {
      setErr(`No se puede desactivar "${table.name}" mientras tiene una comanda abierta.`);
      setTimeout(() => setErr(""), 4000);
      return;
    }
    setTogglingId(table.id);
    try {
      await apiFetch(`/tables/tables/${table.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !table.is_active }),
      });
      await loadTables();
    } catch (e) { console.error("MesasConfig: error toggling activo/inactivo mesa:", e); } finally { setTogglingId(null); }
  }

  const activeTables   = tables.filter(t => t.is_active);
  const inactiveTables = tables.filter(t => !t.is_active);

  return (
    <div style={{ background: C.bg, minHeight: "100vh", padding: mob ? "16px 12px" : "24px", fontFamily: "'DM Sans', 'Helvetica Neue', system-ui, sans-serif" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <a href="/dashboard/mesas" style={{ fontSize: 13, color: C.mute, textDecoration: "none", display: "flex", alignItems: "center", gap: 4 }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
              Mesas
            </a>
            <span style={{ color: C.border }}>/</span>
            <span style={{ fontSize: 13, color: C.mid, fontWeight: 600 }}>Configuración</span>
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: C.text, margin: 0 }}>Gestión de mesas</h1>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 2 }}>
            {activeTables.length} activa{activeTables.length !== 1 ? "s" : ""} · {inactiveTables.length} inactiva{inactiveTables.length !== 1 ? "s" : ""}
          </div>
        </div>
        <Btn variant="primary" onClick={openCreate}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Nueva mesa
        </Btn>
      </div>

      {/* Error banner */}
      {err && (
        <div style={{ marginBottom: 16, padding: "10px 16px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 13, fontWeight: 500 }}>
          {err}
        </div>
      )}

      {/* Table list (única vista expuesta en producción — la vista de
          "Distribuir mesas" / FloorPlanEditor queda solo en nuestro entorno
          de pruebas). */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, boxShadow: C.sh, overflow: "hidden" }}>
       <div style={{ overflowX: "auto" }}>
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 48, color: C.mute }}>
            <Spinner size={28} />
          </div>
        ) : tables.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 24px" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>🍽️</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>Sin mesas configuradas</div>
            <div style={{ fontSize: 13, color: C.mute, marginBottom: 20 }}>Crea tu primera mesa para empezar.</div>
            <Btn variant="primary" onClick={openCreate}>Crear primera mesa</Btn>
          </div>
        ) : (
          <>
            {/* Header row */}
            <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 70px 60px 90px" : "1fr 100px 70px 70px 80px 70px 120px", gap: 0, padding: mob ? "10px 12px" : "10px 20px", borderBottom: `1px solid ${C.border}`, background: C.bg }}>
              {(mob ? ["Nombre", "Estado", "Activa", "Acciones"] : ["Nombre", "Zona", "Capacidad", "Forma", "Estado", "Activa", "Acciones"]).map(h => (
                <div key={h} style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em" }}>{h}</div>
              ))}
            </div>

            {/* Rows */}
            {tables.map((t, i) => {
              const occupied = t.status === "OPEN";
              const isToggling = togglingId === t.id;
              return (
                <div key={t.id} style={{
                  display: "grid", gridTemplateColumns: mob ? "1fr 70px 60px 90px" : "1fr 100px 70px 70px 80px 70px 120px",
                  alignItems: "center", gap: 0,
                  padding: mob ? "12px 12px" : "14px 20px",
                  borderBottom: i < tables.length - 1 ? `1px solid ${C.border}` : "none",
                  opacity: t.is_active ? 1 : 0.5,
                  background: t.is_active ? C.surface : C.bg,
                }}>

                  {/* Name */}
                  <div style={{minWidth:0}}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontSize: mob?13:14, fontWeight: 600, color: C.text }}>{t.name}</span>
                      {t.is_counter && (
                        <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 99, background: C.accentBg, color: C.accent, border: `1px solid ${C.accentBd}` }}>
                          Mostrador
                        </span>
                      )}
                    </div>
                    {mob && <div style={{ fontSize: 10, color: C.mute, marginTop: 1 }}>{t.zone || "Sin zona"} · {t.capacity} pers.</div>}
                    {!t.is_active && <div style={{ fontSize: 11, color: C.mute }}>Inactiva</div>}
                  </div>

                  {/* Zone — desktop only */}
                  {!mob && <div style={{ fontSize: 12, color: t.zone ? C.mid : C.mute }}>{t.zone || "—"}</div>}

                  {/* Capacity — desktop only */}
                  {!mob && <div style={{ fontSize: 13, color: C.mid }}>{t.capacity} pers.</div>}

                  {/* Shape — desktop only */}
                  {!mob && <div style={{ fontSize: 12, color: C.mute }}>
                    {t.shape === "round" ? "⬤" : t.shape === "rect" ? "▬" : "⬛"}
                  </div>}

                  {/* Status */}
                  <div>
                    <span style={{
                      display: "inline-block", padding: "3px 10px", borderRadius: 99, fontSize: 11, fontWeight: 700,
                      background: occupied ? C.amberBg : C.greenBg,
                      color: occupied ? C.amber : C.green,
                      border: `1px solid ${occupied ? C.amberBd : C.greenBd}`,
                    }}>
                      {occupied ? "Ocupada" : "Libre"}
                    </span>
                  </div>

                  {/* Toggle active */}
                  <div>
                    <button
                      onClick={() => toggleActive(t)}
                      disabled={isToggling}
                      title={occupied && t.is_active ? "No se puede desactivar con comanda abierta" : t.is_active ? "Desactivar mesa" : "Activar mesa"}
                      style={{
                        width: 36, height: 20, borderRadius: 10, border: "none",
                        background: t.is_active ? C.accent : C.borderMd,
                        cursor: isToggling ? "not-allowed" : "pointer",
                        position: "relative", transition: "background 0.2s ease",
                        opacity: isToggling ? 0.6 : 1,
                      }}
                    >
                      <div style={{
                        position: "absolute", top: 2, left: t.is_active ? 18 : 2,
                        width: 16, height: 16, borderRadius: "50%", background: "#fff",
                        transition: "left 0.2s ease", boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
                      }} />
                    </button>
                  </div>

                  {/* Actions */}
                  <div style={{ display: "flex", gap: 6 }}>
                    <Btn size="sm" variant="secondary" onClick={() => openEdit(t)}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                      Editar
                    </Btn>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
      </div>

      {/* Info note */}
      {tables.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 12, color: C.mute }}>
          Las mesas inactivas no aparecen en la vista de comandas. No se puede desactivar una mesa con comanda abierta.
        </div>
      )}

      {/* Form modal (create or edit) */}
      {showFormModal && (
        <TableFormModal
          table={editingTable}
          onClose={() => setShowFormModal(false)}
          onSaved={loadTables}
        />
      )}
    </div>
  );
}
