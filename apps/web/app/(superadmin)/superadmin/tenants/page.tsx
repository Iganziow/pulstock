"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

const C = {
  bg: "#0F172A", card: "#1E293B", border: "#334155",
  text: "#F1F5F9", mute: "#94A3B8", accent: "#6366F1",
  green: "#22C55E", red: "#EF4444", yellow: "#F59E0B", white: "#FFFFFF",
};

type TenantRow = {
  id: number; name: string; slug: string; email: string;
  is_active: boolean; created_at: string;
  user_count: number; store_count: number;
  subscription: {
    status: string; plan_name: string; plan_key: string;
    price_clp: number; current_period_end: string | null; has_card: boolean;
  } | null;
};

const STATUS_COLORS: Record<string, string> = {
  active: C.green, trialing: C.accent, past_due: C.yellow, suspended: C.red, cancelled: C.mute,
};
const STATUS_LABELS: Record<string, string> = {
  active: "Activa", trialing: "Trial", past_due: "Pendiente", suspended: "Suspendida", cancelled: "Cancelada",
};
const fCLP = (n: number) => "$" + n.toLocaleString("es-CL");

export default function TenantsPage() {
  const router = useRouter();
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [q, setQ] = useState("");
  const [subStatus, setSubStatus] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "25" });
      if (q) params.set("q", q);
      if (subStatus) params.set("sub_status", subStatus);
      const data = await apiFetch(`/superadmin/tenants/?${params}`);
      setTenants(data.results);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } finally { setLoading(false); }
  }, [page, q, subStatus]);

  useEffect(() => { load(); }, [load]);

  const toggleActive = async (id: number, current: boolean) => {
    await apiFetch(`/superadmin/tenants/${id}/`, {
      method: "PATCH", body: JSON.stringify({ is_active: !current }),
    });
    load();
  };

  const deleteTenant = async (id: number, name: string) => {
    if (!confirm(`¿Eliminar permanentemente "${name}" y todos sus datos? Esta acción no se puede deshacer.`)) return;
    await apiFetch(`/superadmin/tenants/${id}/`, { method: "DELETE" });
    load();
  };

  const inputStyle: React.CSSProperties = {
    background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8,
    padding: "8px 12px", color: C.text, fontSize: 13, outline: "none",
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>Tenants</h1>
          <p style={{ color: C.mute, fontSize: 13, margin: "4px 0 0" }}>{total} negocios registrados</p>
        </div>
      </div>

      {/* Filtros */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <input
          placeholder="Buscar por nombre, slug o email..."
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
          style={{ ...inputStyle, flex: "1 1 250px" }}
        />
        <select value={subStatus} onChange={(e) => { setSubStatus(e.target.value); setPage(1); }} style={{ ...inputStyle, minWidth: 160 }}>
          <option value="">Todos los estados</option>
          <option value="active">Activa</option>
          <option value="trialing">Trial</option>
          <option value="past_due">Pago pendiente</option>
          <option value="suspended">Suspendida</option>
          <option value="cancelled">Cancelada</option>
        </select>
      </div>

      {/* Tabla */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: C.bg, borderBottom: `1px solid ${C.border}` }}>
              {["Negocio", "Plan", "Estado", "Usuarios", "Locales", "Creado", "Acciones"].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", color: C.mute, fontWeight: 600, fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ padding: 30, textAlign: "center", color: C.mute }}>Cargando...</td></tr>
            ) : tenants.length === 0 ? (
              <tr><td colSpan={7} style={{ padding: 30, textAlign: "center", color: C.mute }}>Sin resultados.</td></tr>
            ) : tenants.map((t) => (
              <tr
                key={t.id}
                onClick={() => router.push(`/superadmin/tenants/${t.id}`)}
                style={{ borderBottom: `1px solid ${C.border}`, cursor: "pointer", transition: "background .15s" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = C.bg)}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <td style={{ padding: "10px 14px" }}>
                  <div style={{ fontWeight: 700 }}>{t.name}</div>
                  <div style={{ fontSize: 11, color: C.mute }}>{t.email || t.slug}</div>
                </td>
                <td style={{ padding: "10px 14px" }}>
                  {t.subscription ? (
                    <div>
                      <div style={{ fontWeight: 600 }}>{t.subscription.plan_name}</div>
                      <div style={{ fontSize: 11, color: C.mute }}>{fCLP(t.subscription.price_clp)}/mes</div>
                    </div>
                  ) : <span style={{ color: C.mute }}>—</span>}
                </td>
                <td style={{ padding: "10px 14px" }}>
                  {t.subscription ? (
                    <span style={{
                      display: "inline-flex", alignItems: "center", gap: 4,
                      padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700,
                      background: (STATUS_COLORS[t.subscription.status] || C.mute) + "20",
                      color: STATUS_COLORS[t.subscription.status] || C.mute,
                    }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: STATUS_COLORS[t.subscription.status] || C.mute }} />
                      {STATUS_LABELS[t.subscription.status] || t.subscription.status}
                    </span>
                  ) : (
                    <span style={{ color: C.mute, fontSize: 11 }}>Sin plan</span>
                  )}
                </td>
                <td style={{ padding: "10px 14px", fontWeight: 600 }}>{t.user_count}</td>
                <td style={{ padding: "10px 14px", fontWeight: 600 }}>{t.store_count}</td>
                <td style={{ padding: "10px 14px", color: C.mute, fontSize: 12 }}>
                  {new Date(t.created_at).toLocaleDateString("es-CL")}
                </td>
                <td style={{ padding: "10px 14px" }} onClick={(e) => e.stopPropagation()}>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      onClick={() => toggleActive(t.id, t.is_active)}
                      style={{
                        padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                        border: "none", cursor: "pointer",
                        background: t.is_active ? C.red + "20" : C.green + "20",
                        color: t.is_active ? C.red : C.green,
                      }}
                    >
                      {t.is_active ? "Desactivar" : "Activar"}
                    </button>
                    <button
                      onClick={() => deleteTenant(t.id, t.name)}
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

      {/* Paginación */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
          <button
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
            style={{ ...inputStyle, cursor: page > 1 ? "pointer" : "default", opacity: page === 1 ? 0.4 : 1 }}
          >
            Anterior
          </button>
          <span style={{ display: "flex", alignItems: "center", fontSize: 13, color: C.mute }}>
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
            style={{ ...inputStyle, cursor: page < totalPages ? "pointer" : "default", opacity: page >= totalPages ? 0.4 : 1 }}
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}
