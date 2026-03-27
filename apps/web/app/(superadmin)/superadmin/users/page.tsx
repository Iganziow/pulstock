"use client";
import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";

const C = {
  bg: "#0F172A", card: "#1E293B", border: "#334155",
  text: "#F1F5F9", mute: "#94A3B8", accent: "#6366F1",
  green: "#22C55E", red: "#EF4444", white: "#FFFFFF",
};

type UserRow = {
  id: number; email: string; username: string;
  first_name: string; last_name: string; role: string;
  is_active: boolean; tenant_id: number | null; tenant_name: string | null;
  last_login: string | null; date_joined: string;
};

const ROLE_LABELS: Record<string, string> = { owner: "Dueño", manager: "Admin", cashier: "Cajero", inventory: "Inventario" };

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(true);

  // Modal crear usuario
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", first_name: "", last_name: "", role: "owner", tenant_id: "" });
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState("");
  const [tenants, setTenants] = useState<{ id: number; name: string }[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "25" });
      if (q) params.set("q", q);
      if (role) params.set("role", role);
      const data = await apiFetch(`/superadmin/users/?${params}`);
      setUsers(data.results);
      setTotal(data.total);
    } finally { setLoading(false); }
  }, [page, q, role]);

  useEffect(() => { load(); }, [load]);

  // Load tenants for the create modal dropdown
  const loadTenants = useCallback(async () => {
    try {
      const data = await apiFetch("/superadmin/tenants/?page_size=200");
      setTenants(data.results.map((t: any) => ({ id: t.id, name: t.name })));
    } catch {}
  }, []);

  const toggleUser = async (id: number) => {
    await apiFetch(`/superadmin/users/${id}/toggle/`, { method: "POST" });
    load();
  };

  const deleteUser = async (id: number, email: string) => {
    if (!confirm(`¿Eliminar permanentemente a "${email}"? Esta acción no se puede deshacer.`)) return;
    await apiFetch(`/superadmin/users/${id}/`, { method: "DELETE" });
    load();
  };

  const handleCreate = async () => {
    setCreating(true);
    setCreateMsg("");
    try {
      await apiFetch("/superadmin/users/create/", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          tenant_id: form.tenant_id ? Number(form.tenant_id) : undefined,
        }),
      });
      setShowCreate(false);
      setForm({ email: "", password: "", first_name: "", last_name: "", role: "owner", tenant_id: "" });
      load();
    } catch (e: any) {
      setCreateMsg(e?.data?.detail || "Error al crear usuario.");
    } finally { setCreating(false); }
  };

  const inputStyle: React.CSSProperties = {
    background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8,
    padding: "8px 12px", color: C.text, fontSize: 13, outline: "none", width: "100%",
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>Usuarios</h1>
          <p style={{ color: C.mute, fontSize: 13, margin: "4px 0 0" }}>{total} usuarios en la plataforma</p>
        </div>
        <button
          onClick={() => { loadTenants(); setShowCreate(true); }}
          style={{
            padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 700,
            background: C.accent, color: C.white, border: "none", cursor: "pointer",
          }}
        >
          + Crear usuario
        </button>
      </div>

      {/* Filtros */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <input
          placeholder="Buscar por email o nombre..."
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
          style={{ ...inputStyle, flex: "1 1 250px", width: "auto" }}
        />
        <select value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }} style={{ ...inputStyle, width: "auto", minWidth: 140 }}>
          <option value="">Todos los roles</option>
          <option value="owner">Dueño</option>
          <option value="manager">Administrador</option>
          <option value="cashier">Cajero</option>
          <option value="inventory">Inventario</option>
        </select>
      </div>

      {/* Tabla */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: C.bg, borderBottom: `1px solid ${C.border}` }}>
              {["Email", "Nombre", "Negocio", "Rol", "Último login", "Estado", ""].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", color: C.mute, fontWeight: 600, fontSize: 11, textTransform: "uppercase" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ padding: 30, textAlign: "center", color: C.mute }}>Cargando...</td></tr>
            ) : users.map((u) => (
              <tr key={u.id} style={{ borderBottom: `1px solid ${C.border}22` }}>
                <td style={{ padding: "10px 14px", fontWeight: 600 }}>{u.email}</td>
                <td style={{ padding: "10px 14px" }}>{u.first_name} {u.last_name}</td>
                <td style={{ padding: "10px 14px", color: u.tenant_name ? C.text : C.mute }}>
                  {u.tenant_name || "Sin tenant"}
                </td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{ padding: "2px 8px", borderRadius: 12, fontSize: 11, fontWeight: 600, background: C.accent + "20", color: C.accent }}>
                    {ROLE_LABELS[u.role] || u.role}
                  </span>
                </td>
                <td style={{ padding: "10px 14px", color: C.mute, fontSize: 12 }}>
                  {u.last_login ? new Date(u.last_login).toLocaleDateString("es-CL") : "Nunca"}
                </td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{ color: u.is_active ? C.green : C.red, fontSize: 12, fontWeight: 600 }}>
                    {u.is_active ? "Activo" : "Inactivo"}
                  </span>
                </td>
                <td style={{ padding: "10px 14px" }}>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      onClick={() => toggleUser(u.id)}
                      style={{
                        padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                        border: "none", cursor: "pointer",
                        background: u.is_active ? C.red + "15" : C.green + "15",
                        color: u.is_active ? C.red : C.green,
                      }}
                    >
                      {u.is_active ? "Desactivar" : "Activar"}
                    </button>
                    <button
                      onClick={() => deleteUser(u.id, u.email)}
                      style={{
                        padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                        border: "none", cursor: "pointer",
                        background: C.red + "20", color: C.red,
                      }}
                    >
                      Eliminar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal Crear */}
      {showCreate && (
        <div style={{
          position: "fixed", inset: 0, background: "#00000088",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100,
        }}>
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 16, padding: 28, width: 420, maxWidth: "90vw" }}>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 16 }}>Crear usuario</div>

            {createMsg && <div style={{ padding: "8px 12px", borderRadius: 8, background: C.red + "20", color: C.red, fontSize: 12, marginBottom: 12 }}>{createMsg}</div>}

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} style={inputStyle} />
              <input placeholder="Contraseña" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} style={inputStyle} />
              <div style={{ display: "flex", gap: 8 }}>
                <input placeholder="Nombre" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} style={inputStyle} />
                <input placeholder="Apellido" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} style={inputStyle} />
              </div>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} style={inputStyle}>
                <option value="owner">Dueño</option>
                <option value="manager">Administrador</option>
                <option value="cashier">Cajero</option>
                <option value="inventory">Inventario</option>
              </select>
              <select value={form.tenant_id} onChange={(e) => setForm({ ...form, tenant_id: e.target.value })} style={inputStyle} required>
                <option value="">— Seleccionar negocio —</option>
                {tenants.map((t) => <option key={t.id} value={t.id}>{t.name} (ID {t.id})</option>)}
              </select>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button onClick={() => setShowCreate(false)} style={{ padding: "8px 16px", borderRadius: 8, fontSize: 13, background: "transparent", color: C.mute, border: `1px solid ${C.border}`, cursor: "pointer" }}>
                Cancelar
              </button>
              <button onClick={handleCreate} disabled={creating || !form.email || !form.password} style={{ padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 700, background: C.accent, color: C.white, border: "none", cursor: "pointer", opacity: creating ? 0.6 : 1 }}>
                {creating ? "Creando..." : "Crear"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
