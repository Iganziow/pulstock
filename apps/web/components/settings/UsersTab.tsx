"use client";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { Me } from "@/lib/me";
import { Card, SectionHeader, Btn, Spinner, Label, iS, FL, ROLES, type User, type Store } from "./SettingsUI";

interface UsersTabProps {
  users: User[];
  me: Me;
  stores: Store[];
  onRefresh: () => void;
  flash: (type: "ok" | "err", text: string) => void;
}

export default function UsersTab({ users, me, stores, onRefresh, flash }: UsersTabProps) {
  const [saving, setSaving] = useState(false);

  const [showCreateUser, setShowCreateUser] = useState(false);
  const [nuUser, setNuUser] = useState(""); const [nuPass, setNuPass] = useState("");
  const [nuFirst, setNuFirst] = useState(""); const [nuLast, setNuLast] = useState("");
  const [nuEmail, setNuEmail] = useState(""); const [nuRole, setNuRole] = useState("cashier");
  const [nuStoreIds, setNuStoreIds] = useState<number[]>([]);

  const [editUser, setEditUser] = useState<User | null>(null);
  const [euRole, setEuRole] = useState(""); const [euFirst, setEuFirst] = useState(""); const [euLast, setEuLast] = useState("");
  const [euEmail, setEuEmail] = useState(""); const [euPw, setEuPw] = useState(""); const [euCurrentPw, setEuCurrentPw] = useState("");
  const [euStoreIds, setEuStoreIds] = useState<number[]>([]);

  const toggleStore = (ids: number[], setIds: (v: number[]) => void, sid: number) => {
    setIds(ids.includes(sid) ? ids.filter(x => x !== sid) : [...ids, sid]);
  };

  const createUser = async () => {
    setSaving(true);
    try {
      await apiFetch("/core/users/", {
        method: "POST",
        body: JSON.stringify({
          username: nuUser, password: nuPass, first_name: nuFirst,
          last_name: nuLast, email: nuEmail, role: nuRole,
          store_ids: nuRole === "owner" ? [] : nuStoreIds,
        }),
      });
      onRefresh(); setShowCreateUser(false);
      setNuUser(""); setNuPass(""); setNuFirst(""); setNuLast(""); setNuEmail(""); setNuRole("cashier"); setNuStoreIds([]);
      flash("ok", "Usuario creado");
    } catch (e: unknown) { flash("err", e instanceof Error ? e.message : "Error creando usuario"); }
    finally { setSaving(false); }
  };

  const saveEditUser = async () => {
    if (!editUser) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        role: euRole, first_name: euFirst, last_name: euLast, email: euEmail,
        store_ids: euRole === "owner" ? undefined : euStoreIds,
      };
      if (euPw) { body.password = euPw; if (editUser.id !== me?.id) body.current_password = euCurrentPw; }
      await apiFetch(`/core/users/${editUser.id}/`, { method: "PATCH", body: JSON.stringify(body) });
      onRefresh(); setEditUser(null); setEuPw(""); setEuCurrentPw("");
      flash("ok", "Usuario actualizado");
    } catch (e: unknown) { flash("err", e instanceof Error ? e.message : "Error actualizando"); }
    finally { setSaving(false); }
  };

  const toggleUserActive = async (u: User) => {
    try {
      await apiFetch(`/core/users/${u.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !u.is_active }) });
      onRefresh();
      flash("ok", u.is_active ? "Usuario desactivado" : "Usuario reactivado");
    } catch (e: unknown) { flash("err", e instanceof Error ? e.message : "Error"); }
  };

  const deleteUser = async (u: User) => {
    if (!confirm(`Eliminar permanentemente a ${u.first_name || u.username}? Esta accion no se puede deshacer.`)) return;
    try {
      await apiFetch(`/core/users/${u.id}/`, { method: "DELETE" });
      onRefresh();
      flash("ok", "Usuario eliminado");
    } catch (e: unknown) { flash("err", e instanceof Error ? e.message : "Error eliminando"); }
  };

  const multiStore = stores.length > 1;

  function StoreChips({ selected, onToggle, role }: { selected: number[]; onToggle: (sid: number) => void; role: string }) {
    if (role === "owner") return <div style={{ fontSize: 12, color: C.mute, fontStyle: "italic" }}>Los dueños acceden a todos los locales automáticamente.</div>;
    if (!multiStore) return null;
    return (
      <div style={FL}>
        <Label>Locales asignados</Label>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {stores.map(s => {
            const on = selected.includes(s.id);
            return (
              <button key={s.id} type="button" onClick={() => onToggle(s.id)} style={{
                padding: "7px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                border: `1.5px solid ${on ? C.accent : C.border}`,
                background: on ? C.accentBg : C.surface,
                color: on ? C.accent : C.mid,
                cursor: "pointer", fontFamily: C.font,
              }}>
                {on ? "✓ " : ""}{s.name}
              </button>
            );
          })}
        </div>
        {selected.length === 0 && <div style={{ fontSize: 11, color: C.red }}>Selecciona al menos un local</div>}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-.02em" }}>Usuarios</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 2 }}>{users.length} usuario{users.length !== 1 ? "s" : ""} en tu negocio</div>
        </div>
        <Btn onClick={() => setShowCreateUser(!showCreateUser)} size="sm">
          {showCreateUser ? "Cancelar" : "+ Nuevo usuario"}
        </Btn>
      </div>

      {showCreateUser && (
        <Card style={{ borderColor: C.accentBd }}>
          <SectionHeader icon="👤" title="Crear usuario" desc="El usuario podrá acceder al sistema con estas credenciales" />
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div style={FL}><Label req>Usuario</Label><input value={nuUser} onChange={e => setNuUser(e.target.value)} style={{ ...iS, fontFamily: C.mono }} placeholder="jperez" /></div>
              <div style={FL}><Label req>Contraseña</Label><input type="password" value={nuPass} onChange={e => setNuPass(e.target.value)} style={iS} placeholder="Mín. 8 caracteres" /></div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div style={FL}><Label>Nombre</Label><input value={nuFirst} onChange={e => setNuFirst(e.target.value)} style={iS} /></div>
              <div style={FL}><Label>Apellido</Label><input value={nuLast} onChange={e => setNuLast(e.target.value)} style={iS} /></div>
            </div>
            <div style={FL}><Label>Email</Label><input type="email" value={nuEmail} onChange={e => setNuEmail(e.target.value)} style={iS} /></div>
            <div style={FL}>
              <Label req>Rol</Label>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {ROLES.map(r => (
                  <button key={r.value} type="button" onClick={() => setNuRole(r.value)} style={{
                    padding: "10px 14px", border: `1.5px solid ${nuRole === r.value ? r.color : C.border}`,
                    borderRadius: 8, background: nuRole === r.value ? r.bg : C.surface,
                    cursor: "pointer", fontFamily: C.font, flex: 1, textAlign: "left", minWidth: 120,
                  }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: nuRole === r.value ? r.color : C.text }}>{r.label}</div>
                    <div style={{ fontSize: 11, color: C.mute, marginTop: 1 }}>{r.desc}</div>
                  </button>
                ))}
              </div>
            </div>
            <StoreChips selected={nuStoreIds} onToggle={sid => toggleStore(nuStoreIds, setNuStoreIds, sid)} role={nuRole} />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <Btn onClick={() => setShowCreateUser(false)} variant="secondary">Cancelar</Btn>
              <Btn onClick={createUser} disabled={saving || !nuUser || !nuPass || (nuRole !== "owner" && multiStore && nuStoreIds.length === 0)} variant="success">
                {saving ? <><Spinner /> Creando...</> : "Crear usuario"}
              </Btn>
            </div>
          </div>
        </Card>
      )}

      {users.map(u => {
        const rc = ROLES.find(r => r.value === u.role);
        const isEditing = editUser?.id === u.id;
        return (
          <Card key={u.id} style={{ padding: "12px 18px", borderColor: isEditing ? C.accentBd : C.border }}>
            {!isEditing ? (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", gap: 7 }}>
                    {u.first_name || u.username} {u.last_name}
                    {!u.is_active && (
                      <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 99, background: C.redBg, color: C.red, border: `1px solid ${C.redBd}` }}>
                        Inactivo
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>
                    {u.email || u.username}
                    {u.last_login
                      ? ` · Último acceso: ${new Date(u.last_login).toLocaleDateString("es-CL", { day: "numeric", month: "short", year: "numeric" })}`
                      : " · Nunca accedió"}
                  </div>
                  {/* Store access tags */}
                  {multiStore && u.role !== "owner" && u.store_access && u.store_access.length > 0 && (
                    <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                      {u.store_access.map(sa => (
                        <span key={sa.store_id} style={{
                          fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 6,
                          background: C.bg, border: `1px solid ${C.border}`, color: C.mid,
                        }}>{sa.store_name}</span>
                      ))}
                    </div>
                  )}
                  {multiStore && u.role === "owner" && (
                    <div style={{ fontSize: 10, color: C.mute, marginTop: 3, fontStyle: "italic" }}>Todos los locales</div>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="wh-tag" style={{ background: rc?.bg || "#F4F4F5", border: `1px solid ${rc?.bd || "#E4E4E7"}`, color: rc?.color || C.mute }}>
                    {rc?.label || u.role}
                  </span>
                  <button type="button" onClick={() => {
                    setEditUser(u); setEuRole(u.role); setEuFirst(u.first_name); setEuLast(u.last_name);
                    setEuEmail(u.email); setEuPw(""); setEuCurrentPw("");
                    setEuStoreIds(u.store_access?.map(sa => sa.store_id) || []);
                  }} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, color: C.accent, fontWeight: 700 }}>
                    Editar
                  </button>
                  {u.id !== me?.id && (
                    <button type="button" onClick={() => toggleUserActive(u)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, color: u.is_active ? C.red : C.green, fontWeight: 700 }}>
                      {u.is_active ? "Desactivar" : "Reactivar"}
                    </button>
                  )}
                  {u.id !== me?.id && !u.is_active && (
                    <button type="button" onClick={() => deleteUser(u)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, color: C.red, fontWeight: 700 }}>
                      Eliminar
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div style={{ display: "grid", gap: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>Editando: <code style={{ fontFamily: C.mono }}>{u.username}</code></div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <div style={FL}><Label>Nombre</Label><input value={euFirst} onChange={e => setEuFirst(e.target.value)} style={iS} /></div>
                  <div style={FL}><Label>Apellido</Label><input value={euLast} onChange={e => setEuLast(e.target.value)} style={iS} /></div>
                </div>
                <div style={FL}><Label>Email</Label><input type="email" value={euEmail} onChange={e => setEuEmail(e.target.value)} style={iS} /></div>
                <div style={FL}><Label>Nueva contraseña</Label><input type="password" value={euPw} onChange={e => setEuPw(e.target.value)} style={iS} placeholder="Dejar vacío para no cambiar" /></div>
                {euPw && u.id !== me?.id && (
                  <div style={FL}><Label req>Tu contraseña actual (para confirmar)</Label><input type="password" value={euCurrentPw} onChange={e => setEuCurrentPw(e.target.value)} style={iS} placeholder="Tu contraseña de administrador" autoComplete="current-password" /></div>
                )}
                <div style={FL}>
                  <Label>Rol</Label>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {ROLES.map(r => (
                      <button key={r.value} type="button" onClick={() => setEuRole(r.value)} style={{
                        padding: "8px 14px", border: `1.5px solid ${euRole === r.value ? r.color : C.border}`,
                        borderRadius: 8, background: euRole === r.value ? r.bg : C.surface,
                        cursor: "pointer", fontFamily: C.font, fontSize: 13, fontWeight: 600,
                        color: euRole === r.value ? r.color : C.mid,
                      }}>{r.label}</button>
                    ))}
                  </div>
                </div>
                <StoreChips selected={euStoreIds} onToggle={sid => toggleStore(euStoreIds, setEuStoreIds, sid)} role={euRole} />
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                  <Btn onClick={() => { setEditUser(null); setEuCurrentPw(""); }} variant="secondary">Cancelar</Btn>
                  <Btn onClick={saveEditUser} disabled={saving} variant="primary">{saving ? <><Spinner /> Guardando</> : "Guardar"}</Btn>
                </div>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
