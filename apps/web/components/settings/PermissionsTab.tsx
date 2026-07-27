"use client";

/**
 * PermissionsTab — matriz de permisos por rol editable por el dueño (Fudo-style).
 * El dueño activa/desactiva qué puede hacer cada rol. Owner = todo (bloqueado).
 * `settings`/`users` no aparecen (solo dueño; el backend los bloquea).
 */
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/settings/SettingsUI";

type PermMeta = { key: string; label: string; group: string };
type RoleRow = { role: string; role_label: string; permissions: Record<string, boolean> };
type Payload = {
  permission_meta: PermMeta[];
  editable_roles: string[];
  roles: RoleRow[];
  users_by_role: Record<string, { id: number; name: string }[]>;
};

export default function PermissionsTab({ flash, mob }: { flash: (type: "ok" | "err", text: string) => void; mob?: boolean }) {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // Estado editable: {role: {key: bool}}
  const [matrix, setMatrix] = useState<Record<string, Record<string, boolean>>>({});

  useEffect(() => {
    (async () => {
      try {
        const d = (await apiFetch("/core/role-permissions/")) as Payload;
        setData(d);
        const m: Record<string, Record<string, boolean>> = {};
        for (const r of d.roles) m[r.role] = { ...r.permissions };
        setMatrix(m);
      } catch (e: any) {
        flash("err", e?.message ?? "No se pudieron cargar los permisos");
      } finally { setLoading(false); }
    })();
  }, []);

  function toggle(role: string, key: string) {
    setMatrix(prev => ({ ...prev, [role]: { ...prev[role], [key]: !prev[role]?.[key] } }));
  }

  async function save() {
    setSaving(true);
    try {
      const permissions: Record<string, Record<string, boolean>> = {};
      for (const r of data!.editable_roles) {
        permissions[r] = {};
        for (const m of data!.permission_meta) permissions[r][m.key] = !!matrix[r]?.[m.key];
      }
      const d = (await apiFetch("/core/role-permissions/", {
        method: "PUT", body: JSON.stringify({ permissions }),
      })) as Payload;
      setData(d);
      flash("ok", "Permisos guardados");
    } catch (e: any) {
      flash("err", e?.message ?? "Error al guardar");
    } finally { setSaving(false); }
  }

  if (loading) return <div style={{ padding: 40, display: "flex", justifyContent: "center" }}><Spinner size={22} /></div>;
  if (!data) return null;

  const roles = data.roles; // editables (sin owner)
  // Agrupar permisos por "group" preservando orden.
  const groups: { group: string; items: PermMeta[] }[] = [];
  for (const m of data.permission_meta) {
    let g = groups.find(x => x.group === m.group);
    if (!g) { g = { group: m.group, items: [] }; groups.push(g); }
    g.items.push(m);
  }

  const cell = (checked: boolean, onClick?: () => void, locked = false) => (
    <div
      onClick={locked ? undefined : onClick}
      title={locked ? "El dueño siempre tiene acceso" : (checked ? "Activado" : "Desactivado")}
      style={{
        width: 26, height: 26, borderRadius: 6, margin: "0 auto",
        display: "flex", alignItems: "center", justifyContent: "center",
        cursor: locked ? "default" : "pointer",
        background: checked ? C.accent : C.bg,
        border: `1px solid ${checked ? C.accent : C.border}`,
        color: "#fff", opacity: locked ? 0.55 : 1,
      }}
    >
      {checked && (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
      )}
    </div>
  );

  const thStyle: React.CSSProperties = { padding: "8px 10px", fontSize: 12, fontWeight: 700, color: C.text, textAlign: "center", whiteSpace: "nowrap" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>Permisos por rol</div>
        <div style={{ fontSize: 12, color: C.mute, marginTop: 3, lineHeight: 1.5 }}>
          Elegí qué puede hacer cada rol. El <b>Dueño</b> siempre tiene acceso total.
          Los cambios se aplican al menú y a las páginas de cada usuario según su rol.
        </div>
      </div>

      <div style={{ overflowX: "auto", border: `1px solid ${C.border}`, borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 420 }}>
          <thead>
            <tr style={{ background: C.bg, borderBottom: `1px solid ${C.border}` }}>
              <th style={{ ...thStyle, textAlign: "left", minWidth: 180 }}>Permiso</th>
              {roles.map(r => (
                <th key={r.role} style={thStyle}>{r.role_label}</th>
              ))}
              <th style={{ ...thStyle, color: C.mute }}>Dueño</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(g => (
              <>
                <tr key={`g-${g.group}`}>
                  <td colSpan={roles.length + 2} style={{ padding: "8px 10px 4px", fontSize: 10, fontWeight: 800, color: C.accent, textTransform: "uppercase", letterSpacing: ".06em", background: C.surface }}>{g.group}</td>
                </tr>
                {g.items.map(m => (
                  <tr key={m.key} style={{ borderBottom: `1px solid ${C.border}` }}>
                    <td style={{ padding: "8px 10px", fontSize: 13, color: C.text }}>{m.label}</td>
                    {roles.map(r => (
                      <td key={r.role} style={{ padding: "6px 10px" }}>
                        {cell(!!matrix[r.role]?.[m.key], () => toggle(r.role, m.key))}
                      </td>
                    ))}
                    <td style={{ padding: "6px 10px" }}>{cell(true, undefined, true)}</td>
                  </tr>
                ))}
              </>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button onClick={save} disabled={saving} style={{
          padding: "10px 20px", border: "none", borderRadius: 8, background: C.accent, color: "#fff",
          fontSize: 14, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer", opacity: saving ? 0.5 : 1,
          display: "flex", alignItems: "center", gap: 8,
        }}>{saving ? <Spinner size={14} /> : null}{saving ? "Guardando…" : "Guardar permisos"}</button>
      </div>

      {/* Usuarios por rol */}
      <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 14 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 8 }}>Usuarios por rol</div>
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
          {[{ role: "owner", label: "Dueño" }, ...roles.map(r => ({ role: r.role, label: r.role_label }))].map(({ role, label }) => (
            <div key={role} style={{ border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px", background: C.surface }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: C.accent, marginBottom: 6 }}>{label}</div>
              {(data.users_by_role[role] || []).length === 0 ? (
                <div style={{ fontSize: 12, color: C.mute }}>— Sin usuarios —</div>
              ) : (
                (data.users_by_role[role] || []).map(u => (
                  <div key={u.id} style={{ fontSize: 12, color: C.mid, padding: "2px 0" }}>{u.name}</div>
                ))
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
