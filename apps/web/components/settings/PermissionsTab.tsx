"use client";

/**
 * PermissionsTab — matriz de permisos por rol editable por el dueño (Fudo-style).
 * El dueño activa/desactiva qué puede hacer cada rol. Owner = todo (bloqueado).
 * `settings`/`users` no aparecen (solo dueño; el backend los bloquea).
 *
 * Segunda mitad: quién está en cada rol, y mover personas entre roles sin salir
 * de acá. Como cada persona tiene UN solo rol, "quitar de un rol" = moverla a
 * otro; por eso no hay botón de quitar suelto (dejaría a alguien sin permisos
 * de ningún tipo y sin forma de volver a entrar).
 */
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner, ROLES } from "@/components/settings/SettingsUI";

type PermMeta = { key: string; label: string; group: string };
type RoleRow = { role: string; role_label: string; permissions: Record<string, boolean> };
type RoleUser = { id: number; name: string; email?: string };
type Payload = {
  permission_meta: PermMeta[];
  editable_roles: string[];
  roles: RoleRow[];
  users_by_role: Record<string, RoleUser[]>;
};

export default function PermissionsTab({ flash, mob, meId, onUsersChanged }: {
  flash: (type: "ok" | "err", text: string) => void;
  mob?: boolean;
  meId?: number | null;
  onUsersChanged?: () => void;
}) {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // Estado editable: {role: {key: bool}}
  const [matrix, setMatrix] = useState<Record<string, Record<string, boolean>>>({});
  // Persona cuyo rol se está guardando (para bloquear el select mientras tanto).
  const [movingId, setMovingId] = useState<number | null>(null);
  // Card que tiene abierto el selector de "agregar persona".
  const [addingTo, setAddingTo] = useState<string | null>(null);

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

  /** Mueve una persona a otro rol.
   *
   * Refresca SOLO la lista de usuarios: si volviéramos a derivar `matrix` del
   * payload, se perderían los toggles de permisos que el dueño todavía no
   * guardó. Son dos cosas independientes en la misma pantalla.
   */
  async function changeRole(userId: number, newRole: string, personName: string) {
    setMovingId(userId);
    try {
      await apiFetch(`/core/users/${userId}/`, {
        method: "PATCH", body: JSON.stringify({ role: newRole }),
      });
      const d = (await apiFetch("/core/role-permissions/")) as Payload;
      setData(d);
      const label = ROLES.find(r => r.value === newRole)?.label ?? newRole;
      flash("ok", `${personName} ahora es ${label}`);
      onUsersChanged?.();
    } catch (e: any) {
      flash("err", e?.data?.detail ?? e?.message ?? "No se pudo cambiar el rol");
    } finally {
      setMovingId(null);
      setAddingTo(null);
    }
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
  // Tarjetas de personas: el dueño primero, después los roles editables.
  const allRoles = [
    { role: "owner", label: ROLES.find(r => r.value === "owner")?.label ?? "Dueño" },
    ...roles.map(r => ({ role: r.role, label: r.role_label })),
  ];
  // Gente que hoy NO está en ese rol (candidatos a moverse a él).
  const otrosRoles = (role: string) =>
    allRoles
      .filter(x => x.role !== role)
      .flatMap(x => (data.users_by_role[x.role] || []).map(u => ({ ...u, role: x.role })))
      .filter(u => meId == null || u.id !== meId);
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
          Elige qué puede hacer cada rol. El <b>Dueño</b> siempre tiene acceso total.
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

      {/* ── Personas en cada rol ─────────────────────────────────────────── */}
      <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 16 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>Personas en cada rol</div>
        <div style={{ fontSize: 12, color: C.mute, marginTop: 3, marginBottom: 12, lineHeight: 1.5 }}>
          Cambia el rol de una persona y sus permisos pasan a ser los de arriba.
          Cada persona tiene un solo rol, así que moverla a otro la saca del anterior.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
          {allRoles.map(({ role, label }) => {
            const gente = data.users_by_role[role] || [];
            const rc = ROLES.find(r => r.value === role);
            const fuera = otrosRoles(role);

            return (
              <div key={role} style={{
                border: `1px solid ${C.border}`, borderRadius: 10, background: C.surface,
                display: "flex", flexDirection: "column",
              }}>
                <div style={{
                  padding: "9px 12px", borderBottom: `1px solid ${C.border}`,
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
                  background: rc?.bg ?? C.bg, borderRadius: "10px 10px 0 0",
                }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: rc?.color ?? C.accent }}>{label}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: C.mute, fontFamily: C.mono }}>{gente.length}</span>
                </div>

                <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
                  {gente.length === 0 && (
                    <div style={{ fontSize: 12, color: C.mute, padding: "4px 2px" }}>— Nadie en este rol —</div>
                  )}

                  {gente.map(u => {
                    const soyYo = meId != null && u.id === meId;
                    // El backend rechaza dejar el negocio sin dueño; lo avisamos acá
                    // en vez de esperar el 400.
                    const ultimoDueno = role === "owner" && (data.users_by_role["owner"] || []).length <= 1;
                    const bloqueado = soyYo || ultimoDueno;
                    const motivo = soyYo
                      ? "No puedes cambiar tu propio rol"
                      : "Es el único dueño — asigna otro dueño antes de moverlo";

                    return (
                      <div key={u.id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{
                            fontSize: 12, fontWeight: 600, color: C.text,
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                          }} title={u.email || u.name}>
                            {u.name}{soyYo ? " (tú)" : ""}
                          </div>
                        </div>
                        {bloqueado ? (
                          <span data-testid={`lock-${u.id}`} title={motivo} style={{ fontSize: 13, color: C.mute, cursor: "help", flexShrink: 0 }}>🔒</span>
                        ) : (
                          <select
                            data-testid={`role-select-${u.id}`}
                            value={role}
                            disabled={movingId === u.id}
                            onChange={e => {
                              const nuevo = e.target.value;
                              if (nuevo !== role) changeRole(u.id, nuevo, u.name);
                            }}
                            title={`Mover a ${u.name} a otro rol`}
                            style={{
                              fontSize: 11, padding: "3px 5px", borderRadius: 6,
                              border: `1px solid ${C.border}`, background: C.bg, color: C.mid,
                              cursor: movingId === u.id ? "wait" : "pointer",
                              maxWidth: 118, flexShrink: 0,
                            }}
                          >
                            {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                          </select>
                        )}
                      </div>
                    );
                  })}

                  {/* Agregar alguien que hoy está en otro rol */}
                  <div style={{ marginTop: "auto", paddingTop: 4 }}>
                    {addingTo === role ? (
                      <select
                        data-testid={`add-picker-${role}`}
                        autoFocus
                        defaultValue=""
                        disabled={movingId != null}
                        onChange={e => {
                          const uid = Number(e.target.value);
                          const p = fuera.find(x => x.id === uid);
                          if (p) changeRole(p.id, role, p.name);
                        }}
                        onBlur={() => setAddingTo(null)}
                        style={{
                          width: "100%", fontSize: 12, padding: "5px 6px", borderRadius: 6,
                          border: `1px solid ${C.accent}`, background: C.surface, color: C.text,
                        }}
                      >
                        <option value="" disabled>Elige a quién mover…</option>
                        {fuera.map(p => (
                          <option key={p.id} value={p.id}>
                            {p.name} · {ROLES.find(r => r.value === p.role)?.label ?? p.role}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <button
                        data-testid={`add-to-${role}`}
                        onClick={() => setAddingTo(role)}
                        disabled={fuera.length === 0}
                        title={fuera.length === 0 ? "No hay nadie más para mover a este rol" : `Mover a alguien a ${label}`}
                        style={{
                          width: "100%", padding: "5px 8px", fontSize: 11, fontWeight: 700,
                          borderRadius: 6, border: `1px dashed ${C.border}`, background: "none",
                          color: fuera.length === 0 ? C.mute : C.accent,
                          cursor: fuera.length === 0 ? "not-allowed" : "pointer",
                          opacity: fuera.length === 0 ? 0.5 : 1,
                        }}
                      >
                        + Agregar persona
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ fontSize: 11, color: C.mute, marginTop: 10, lineHeight: 1.5 }}>
          Para crear una persona nueva o desactivar a alguien, ve a la pestaña <b>Usuarios</b>.
        </div>
      </div>
    </div>
  );
}
