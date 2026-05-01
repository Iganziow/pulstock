"use client";

/**
 * /dashboard/caja/categorias
 * ==========================
 * CRUD de categorías personalizables de movimientos de caja.
 * Daniel 01/05/26: cada tenant define las suyas (mantienen los 10 default
 * pre-seedeados + puede agregar custom).
 */

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";

type Category = {
  id: number;
  code: string;
  label: string;
  type: "IN" | "OUT" | "BOTH";
  icon: string;
  color: string;
  is_default_template: boolean;
  is_active: boolean;
  order: number;
  created_at: string;
};

const TYPE_LABELS: Record<Category["type"], string> = {
  IN: "Ingreso",
  OUT: "Egreso",
  BOTH: "Ambos",
};

export default function MovementCategoriesPage() {
  const [data, setData] = useState<Category[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // Modal create / edit
  const [editTarget, setEditTarget] = useState<Category | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    const url = includeInactive
      ? "/caja/categories/?include_inactive=1"
      : "/caja/categories/";
    apiFetch(url)
      .then((d: any) => { if (alive) setData(d?.results || []); })
      .catch((e: any) => { if (alive) setErr(e?.message ?? "Error"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [includeInactive, refreshKey]);

  async function handleToggleActive(cat: Category) {
    try {
      await apiFetch(`/caja/categories/${cat.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !cat.is_active }),
      });
      setRefreshKey(k => k + 1);
    } catch (e: any) {
      alert(e?.message ?? "Error al cambiar estado");
    }
  }

  const expenses = data.filter(c => c.type === "OUT" || c.type === "BOTH");
  const incomes = data.filter(c => c.type === "IN" || c.type === "BOTH");

  return (
    <div style={{ background: C.bg, minHeight: "100vh", padding: "24px 28px" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 800, color: C.text, margin: 0 }}>
              Categorías de movimientos
            </h1>
            <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>
              Personalizá las categorías de ingresos/egresos. Las desactivadas no aparecen al crear movimientos pero conservan los registros viejos.
            </div>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            style={{
              padding: "8px 14px", borderRadius: C.r,
              background: C.accent, color: "#fff", border: "none",
              fontSize: 13, fontWeight: 600, cursor: "pointer",
            }}
          >
            + Nueva categoría
          </button>
        </div>

        {/* Toggle inactive */}
        <div style={{ marginBottom: 14 }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 13, color: C.mid }}>
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={e => setIncludeInactive(e.target.checked)}
            />
            Mostrar también desactivadas
          </label>
        </div>

        {err && (
          <div style={{ padding: "10px 12px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 6, color: C.red, fontSize: 13, marginBottom: 16 }}>
            {err}
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: "center", padding: 40 }}><Spinner /></div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <CategoryColumn
              title="Egresos"
              color={C.red}
              cats={expenses}
              onEdit={setEditTarget}
              onToggle={handleToggleActive}
            />
            <CategoryColumn
              title="Ingresos"
              color={C.green}
              cats={incomes}
              onEdit={setEditTarget}
              onToggle={handleToggleActive}
            />
          </div>
        )}
      </div>

      {/* Create modal */}
      {showCreate && (
        <CategoryFormModal
          mode="create"
          onClose={() => setShowCreate(false)}
          onSaved={() => { setShowCreate(false); setRefreshKey(k => k + 1); }}
        />
      )}

      {/* Edit modal */}
      {editTarget && (
        <CategoryFormModal
          mode="edit"
          existing={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); setRefreshKey(k => k + 1); }}
        />
      )}
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────

function CategoryColumn({
  title, color, cats, onEdit, onToggle,
}: {
  title: string; color: string; cats: Category[];
  onEdit: (c: Category) => void;
  onToggle: (c: Category) => void;
}) {
  return (
    <div style={{ background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`, overflow: "hidden" }}>
      <div style={{ padding: "10px 14px", background: C.bg, borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color, textTransform: "uppercase", letterSpacing: "0.06em" }}>{title}</span>
        <span style={{ fontSize: 11, color: C.mute }}>{cats.length} categorías</span>
      </div>
      {cats.length === 0 ? (
        <div style={{ padding: 24, textAlign: "center", color: C.mute, fontSize: 13, fontStyle: "italic" }}>
          Sin categorías
        </div>
      ) : (
        <div>
          {cats.map(c => (
            <div key={c.id} style={{
              padding: "10px 14px",
              borderBottom: `1px solid ${C.border}`,
              display: "flex", justifyContent: "space-between", alignItems: "center",
              opacity: c.is_active ? 1 : 0.5,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {c.icon && <span style={{ fontSize: 18 }}>{c.icon}</span>}
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: C.text, display: "flex", alignItems: "center", gap: 6 }}>
                    {c.label}
                    {c.is_default_template && (
                      <span title="Categoría predefinida del sistema" style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, background: C.bg, color: C.mute, border: `1px solid ${C.border}` }}>
                        DEFAULT
                      </span>
                    )}
                    {!c.is_active && (
                      <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, background: C.bg, color: C.mute, border: `1px solid ${C.border}` }}>
                        INACTIVA
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 10, color: C.mute, fontFamily: "monospace" }}>{c.code}</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  onClick={() => onEdit(c)}
                  title="Editar"
                  style={{
                    background: "none", border: `1px solid ${C.border}`, borderRadius: 4,
                    padding: "3px 8px", cursor: "pointer", color: C.mid, fontSize: 12,
                  }}
                >✏️</button>
                <button
                  onClick={() => onToggle(c)}
                  title={c.is_active ? "Desactivar" : "Reactivar"}
                  style={{
                    background: "none", border: `1px solid ${C.border}`, borderRadius: 4,
                    padding: "3px 8px", cursor: "pointer", color: c.is_active ? C.red : C.green, fontSize: 12,
                  }}
                >{c.is_active ? "🚫" : "✓"}</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CategoryFormModal({
  mode, existing, onClose, onSaved,
}: {
  mode: "create" | "edit";
  existing?: Category;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [label, setLabel] = useState(existing?.label || "");
  const [type, setType] = useState<Category["type"]>(existing?.type || "OUT");
  const [icon, setIcon] = useState(existing?.icon || "");
  const [color, setColor] = useState(existing?.color || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true); setErr(null);
    try {
      const body = JSON.stringify({ label, type, icon, color });
      if (mode === "create") {
        await apiFetch("/caja/categories/", { method: "POST", body });
      } else {
        await apiFetch(`/caja/categories/${existing!.id}/`, { method: "PATCH", body });
      }
      onSaved();
    } catch (e: any) {
      setErr(e?.message ?? "Error al guardar");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: 460, boxShadow: "0 20px 52px rgba(0,0,0,0.18)" }}>
        <div style={{ fontSize: 16, fontWeight: 800, color: C.text, marginBottom: 16 }}>
          {mode === "create" ? "Nueva categoría" : "Editar categoría"}
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          <Field label="Nombre">
            <input value={label} onChange={e => setLabel(e.target.value)}
              placeholder="Ej: Pago a Coca Cola"
              style={inputStyle} maxLength={80} autoFocus />
          </Field>
          <Field label="Tipo">
            <div style={{ display: "flex", gap: 6 }}>
              {(["IN", "OUT", "BOTH"] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setType(t)}
                  type="button"
                  style={{
                    flex: 1, padding: "8px 0", borderRadius: 6, border: `1px solid ${type === t ? C.accent : C.border}`,
                    background: type === t ? C.accent : C.surface, color: type === t ? "#fff" : C.mid,
                    fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  {t === "IN" ? "↑ Ingreso" : t === "OUT" ? "↓ Egreso" : "↕ Ambos"}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Ícono (emoji opcional)">
            <input value={icon} onChange={e => setIcon(e.target.value)}
              placeholder="Ej: 🛒 💰 📦" style={inputStyle} maxLength={8} />
          </Field>
          <Field label="Color (hex opcional)">
            <input value={color} onChange={e => setColor(e.target.value)}
              placeholder="#FF0066" style={inputStyle} maxLength={9} />
          </Field>
        </div>
        {err && (
          <div style={{ marginTop: 12, padding: "8px 12px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 6, color: C.red, fontSize: 12 }}>
            {err}
          </div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 18 }}>
          <button onClick={onClose} disabled={busy} style={{
            padding: "9px 18px", border: `1px solid ${C.border}`, borderRadius: 6,
            background: C.surface, color: C.mid, cursor: "pointer", fontSize: 13,
          }}>Cancelar</button>
          <button onClick={save} disabled={busy || !label.trim()} style={{
            padding: "9px 18px", border: "none", borderRadius: 6,
            background: C.accent, color: "#fff", cursor: busy ? "not-allowed" : "pointer",
            opacity: busy ? 0.6 : 1, fontSize: 13, fontWeight: 600,
          }}>{busy ? "Guardando..." : "Guardar"}</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "9px 12px", border: `1px solid ${C.border}`,
  borderRadius: 6, fontSize: 14, background: C.surface, color: C.text,
  boxSizing: "border-box",
};
