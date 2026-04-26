"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

const C = {
  bg: "#0F172A", card: "#1E293B", border: "#334155",
  text: "#F1F5F9", mute: "#94A3B8", accent: "#6366F1",
  green: "#22C55E", red: "#EF4444", yellow: "#F59E0B", white: "#FFFFFF",
};

const fCLP = (n: number) => "$" + n.toLocaleString("es-CL");
const STATUS_COLORS: Record<string, string> = { active: C.green, trialing: C.accent, past_due: C.yellow, suspended: C.red, cancelled: C.mute };
const STATUS_LABELS: Record<string, string> = { active: "Activa", trialing: "Trial", past_due: "Pendiente", suspended: "Suspendida", cancelled: "Cancelada" };
const INV_COLORS: Record<string, string> = { paid: C.green, pending: C.yellow, failed: C.red, voided: C.mute };

function Card({ children, title, style }: { children: React.ReactNode; title?: string; style?: React.CSSProperties }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 20, ...style }}>
      {title && <div style={{ fontSize: 12, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 12 }}>{title}</div>}
      {children}
    </div>
  );
}

export default function TenantDetailPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.id;
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const d = await apiFetch(`/superadmin/tenants/${tenantId}/`);
      setData(d);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [tenantId]);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 3000); };

  const updateSub = async (body: Record<string, any>) => {
    setBusy(true);
    try {
      await apiFetch(`/superadmin/tenants/${tenantId}/subscription/`, {
        method: "PATCH", body: JSON.stringify(body),
      });
      flash("Actualizado correctamente.");
      load();
    } catch (e: any) {
      flash(e?.data?.detail || "Error al actualizar.");
    } finally { setBusy(false); }
  };

  const toggleTenant = async () => {
    setBusy(true);
    try {
      await apiFetch(`/superadmin/tenants/${tenantId}/`, {
        method: "PATCH", body: JSON.stringify({ is_active: !data.is_active }),
      });
      flash(data.is_active ? "Tenant desactivado." : "Tenant activado.");
      load();
    } finally { setBusy(false); }
  };

  const toggleUser = async (userId: number) => {
    await apiFetch(`/superadmin/users/${userId}/toggle/`, { method: "POST" });
    load();
  };

  // ── SOPORTE ──
  const [resetting, setResetting] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState<{ email: string; pwd: string } | null>(null);
  const resetUserPassword = async (userId: number, userEmail: string) => {
    if (!confirm(`Generar nueva contraseña para ${userEmail}?\n\nLa contraseña actual dejará de funcionar inmediatamente.`)) return;
    setResetting(userId);
    try {
      const r = await apiFetch(`/superadmin/users/${userId}/reset-password/`, { method: "POST" });
      setNewPassword({ email: r.email, pwd: r.new_password });
    } catch (e: any) {
      flash(e?.data?.detail || "Error al generar contraseña.");
    } finally {
      setResetting(null);
    }
  };

  const [resending, setResending] = useState<string | null>(null);
  const resendEmail = async (type: string) => {
    setResending(type);
    try {
      const r = await apiFetch(`/superadmin/tenants/${tenantId}/resend-email/`, {
        method: "POST", body: JSON.stringify({ type }),
      });
      flash(`Email "${type}" enviado a ${r.sent_to}.`);
    } catch (e: any) {
      flash(e?.data?.detail || "Error al reenviar.");
    } finally {
      setResending(null);
    }
  };

  const [notes, setNotes] = useState<string>("");
  const [savingNotes, setSavingNotes] = useState(false);
  useEffect(() => { if (data?.internal_notes !== undefined) setNotes(data.internal_notes || ""); }, [data?.internal_notes]);
  const saveNotes = async () => {
    setSavingNotes(true);
    try {
      await apiFetch(`/superadmin/tenants/${tenantId}/notes/`, {
        method: "PATCH", body: JSON.stringify({ internal_notes: notes }),
      });
      flash("Notas guardadas.");
    } catch (e: any) {
      flash(e?.data?.detail || "Error al guardar notas.");
    } finally {
      setSavingNotes(false);
    }
  };

  if (loading) return <div style={{ color: C.mute, padding: 40 }}>Cargando...</div>;
  if (!data) return <div style={{ color: C.mute, padding: 40 }}>Tenant no encontrado.</div>;

  const sub = data.subscription;
  const btnStyle: React.CSSProperties = {
    padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700,
    border: "none", cursor: "pointer", fontFamily: "inherit",
  };

  return (
    <div>
      <button onClick={() => router.push("/superadmin/tenants")} style={{ background: "none", border: "none", color: C.accent, fontSize: 13, cursor: "pointer", marginBottom: 12, padding: 0 }}>
        ← Volver a tenants
      </button>

      {msg && (
        <div style={{ padding: "10px 16px", borderRadius: 8, background: C.green + "20", color: C.green, fontSize: 13, marginBottom: 12 }}>
          {msg}
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>{data.name}</h1>
          <p style={{ color: C.mute, fontSize: 13, margin: "4px 0 0" }}>
            {data.slug} · {data.email || "Sin email"} · RUT: {data.rut || "—"}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <span style={{
            padding: "4px 14px", borderRadius: 20, fontSize: 12, fontWeight: 700,
            background: data.is_active ? C.green + "20" : C.red + "20",
            color: data.is_active ? C.green : C.red,
          }}>
            {data.is_active ? "Activo" : "Inactivo"}
          </span>
          <button onClick={toggleTenant} disabled={busy} style={{ ...btnStyle, background: data.is_active ? C.red + "20" : C.green + "20", color: data.is_active ? C.red : C.green }}>
            {data.is_active ? "Desactivar" : "Activar"}
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 20 }}>
        {/* Stats */}
        <Card title="Métricas" style={{ flex: "1 1 200px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {[
              ["Productos", data.stats.products],
              ["Ventas", data.stats.sales],
              ["Usuarios", data.users.length],
              ["Locales", data.stores.length],
            ].map(([l, v]) => (
              <div key={l as string}>
                <div style={{ fontSize: 11, color: C.mute }}>{l}</div>
                <div style={{ fontSize: 20, fontWeight: 800 }}>{v}</div>
              </div>
            ))}
          </div>
        </Card>

        {/* Suscripción */}
        {sub && (
          <Card title="Suscripción" style={{ flex: "2 1 350px" }}>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 11, color: C.mute }}>Plan</div>
                <div style={{ fontSize: 16, fontWeight: 800 }}>{sub.plan_name}</div>
                <div style={{ fontSize: 12, color: C.mute }}>{fCLP(sub.price_clp)}/mes</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: C.mute }}>Estado</div>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 4, padding: "4px 12px",
                  borderRadius: 20, fontSize: 12, fontWeight: 700, marginTop: 4,
                  background: (STATUS_COLORS[sub.status] || C.mute) + "20",
                  color: STATUS_COLORS[sub.status] || C.mute,
                }}>
                  {STATUS_LABELS[sub.status] || sub.status}
                </span>
              </div>
              <div>
                <div style={{ fontSize: 11, color: C.mute }}>Período hasta</div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>
                  {sub.current_period_end ? new Date(sub.current_period_end).toLocaleDateString("es-CL") : "—"}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: C.mute }}>Tarjeta</div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>
                  {sub.has_card ? `${sub.card_brand} •••• ${sub.card_last4}` : "Sin tarjeta"}
                </div>
              </div>
            </div>

            {/* Acciones de suscripción */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
              <select
                onChange={(e) => { if (e.target.value) updateSub({ plan_key: e.target.value }); e.target.value = ""; }}
                style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 12px", color: C.text, fontSize: 12 }}
              >
                <option value="">Cambiar plan...</option>
                <option value="inicio">Plan Inicio</option>
                <option value="crecimiento">Plan Crecimiento</option>
                <option value="pro">Plan Pro</option>
              </select>

              <select
                onChange={(e) => { if (e.target.value) updateSub({ status: e.target.value }); e.target.value = ""; }}
                style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 12px", color: C.text, fontSize: 12 }}
              >
                <option value="">Cambiar estado...</option>
                <option value="active">Activar</option>
                <option value="trialing">Trial</option>
                <option value="past_due">Pago pendiente</option>
                <option value="suspended">Suspender</option>
                <option value="cancelled">Cancelar</option>
              </select>

              <button onClick={() => updateSub({ extend_days: 30 })} disabled={busy}
                style={{ ...btnStyle, background: C.accent + "20", color: C.accent }}>
                +30 días
              </button>
              <button onClick={() => updateSub({ extend_days: 7 })} disabled={busy}
                style={{ ...btnStyle, background: C.accent + "20", color: C.accent }}>
                +7 días
              </button>
            </div>
          </Card>
        )}
      </div>

      {/* Usuarios */}
      <Card title={`Usuarios (${data.users.length})`} style={{ marginBottom: 20 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${C.border}` }}>
              {["Email", "Nombre", "Rol", "Último login", "Estado", ""].map((h) => (
                <th key={h} style={{ padding: "8px 10px", textAlign: "left", color: C.mute, fontWeight: 600, fontSize: 11 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.users.map((u: any) => (
              <tr key={u.id} style={{ borderBottom: `1px solid ${C.border}22` }}>
                <td style={{ padding: "8px 10px" }}>{u.email}</td>
                <td style={{ padding: "8px 10px" }}>{u.first_name} {u.last_name}</td>
                <td style={{ padding: "8px 10px" }}>
                  <span style={{ padding: "2px 8px", borderRadius: 12, fontSize: 11, fontWeight: 600, background: C.accent + "20", color: C.accent }}>
                    {u.role}
                  </span>
                </td>
                <td style={{ padding: "8px 10px", color: C.mute, fontSize: 12 }}>
                  {u.last_login ? new Date(u.last_login).toLocaleDateString("es-CL") : "Nunca"}
                </td>
                <td style={{ padding: "8px 10px" }}>
                  <span style={{ color: u.is_active ? C.green : C.red, fontSize: 12 }}>
                    {u.is_active ? "Activo" : "Inactivo"}
                  </span>
                </td>
                <td style={{ padding: "8px 10px", display: "flex", gap: 6 }}>
                  <button onClick={() => toggleUser(u.id)} style={{ ...btnStyle, background: u.is_active ? C.red + "15" : C.green + "15", color: u.is_active ? C.red : C.green, fontSize: 11 }}>
                    {u.is_active ? "Desactivar" : "Activar"}
                  </button>
                  <button
                    onClick={() => resetUserPassword(u.id, u.email)}
                    disabled={resetting === u.id}
                    style={{ ...btnStyle, background: C.yellow + "15", color: C.yellow, fontSize: 11, opacity: resetting === u.id ? 0.5 : 1 }}
                    title="Generar contraseña nueva"
                  >
                    {resetting === u.id ? "..." : "🔑 Reset pass"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Reenviar emails */}
      <Card title="Reenviar email al cliente" style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: C.mute, marginBottom: 12 }}>
          Útil cuando el cliente reporta "no me llegó". Se envía al email del owner ({data.users.find((u: any) => u.role === "owner")?.email || "—"}).
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {[
            { type: "welcome",           label: "🎉 Bienvenida" },
            { type: "payment_link",      label: "💳 Link de pago" },
            { type: "trial_reminder",    label: "⏰ Aviso de trial" },
            { type: "renewal_reminder",  label: "📅 Aviso de renovación" },
            { type: "payment_recovered", label: "✅ Pago recuperado" },
          ].map((b) => (
            <button
              key={b.type}
              onClick={() => resendEmail(b.type)}
              disabled={resending === b.type}
              style={{
                ...btnStyle, background: C.accent + "15", color: C.accent, fontSize: 12,
                opacity: resending === b.type ? 0.5 : 1,
              }}
            >
              {resending === b.type ? "Enviando..." : b.label}
            </button>
          ))}
        </div>
      </Card>

      {/* Notas internas */}
      <Card title="Notas internas (solo admin)" style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: C.mute, marginBottom: 8 }}>
          Estas notas NO son visibles al cliente. Anota acá contexto del cliente, llamadas, decisiones, etc.
        </div>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          maxLength={5000}
          rows={4}
          placeholder="Ej: Dueño Pedro, prefiere WhatsApp +569... Ya pagó 2 veces sin issues."
          style={{
            width: "100%", boxSizing: "border-box",
            background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8,
            padding: "10px 12px", fontSize: 13, color: C.text, fontFamily: "inherit",
            resize: "vertical", minHeight: 80,
          }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
          <span style={{ fontSize: 11, color: C.mute }}>{notes.length} / 5000</span>
          <button
            onClick={saveNotes}
            disabled={savingNotes || notes === (data.internal_notes || "")}
            style={{
              ...btnStyle, background: C.accent, color: C.white, fontSize: 12,
              opacity: (savingNotes || notes === (data.internal_notes || "")) ? 0.5 : 1,
            }}
          >
            {savingNotes ? "Guardando..." : "Guardar notas"}
          </button>
        </div>
      </Card>

      {/* Modal de password nueva */}
      {newPassword && (
        <div
          onClick={() => setNewPassword(null)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,.7)",
            display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: C.card, border: `1px solid ${C.border}`, borderRadius: 12,
              padding: 24, maxWidth: 480, width: "90%",
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>
              🔑 Nueva contraseña generada
            </div>
            <div style={{ fontSize: 12, color: C.mute, marginBottom: 16 }}>
              Para <strong style={{ color: C.text }}>{newPassword.email}</strong>. Esta contraseña solo se muestra UNA VEZ. Anótala o cópiala ahora.
            </div>
            <div style={{
              background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8,
              padding: "14px 16px", fontFamily: "monospace", fontSize: 18, fontWeight: 700,
              color: C.accent, textAlign: "center", letterSpacing: 1.5, userSelect: "all",
              marginBottom: 16,
            }}>
              {newPassword.pwd}
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={() => { navigator.clipboard.writeText(newPassword.pwd); flash("Copiado al portapapeles."); }}
                style={{ ...btnStyle, background: C.accent + "20", color: C.accent }}
              >
                📋 Copiar
              </button>
              <button
                onClick={() => setNewPassword(null)}
                style={{ ...btnStyle, background: C.accent, color: C.white }}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Facturas */}
      {data.invoices.length > 0 && (
        <Card title={`Últimas facturas (${data.invoices.length})`}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                {["#", "Período", "Monto", "Estado", "Fecha pago"].map((h) => (
                  <th key={h} style={{ padding: "8px 10px", textAlign: "left", color: C.mute, fontWeight: 600, fontSize: 11 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.invoices.map((inv: any) => (
                <tr key={inv.id} style={{ borderBottom: `1px solid ${C.border}22` }}>
                  <td style={{ padding: "8px 10px", color: C.mute }}>#{inv.id}</td>
                  <td style={{ padding: "8px 10px", fontSize: 12 }}>{inv.period_start} → {inv.period_end}</td>
                  <td style={{ padding: "8px 10px", fontWeight: 700 }}>{fCLP(inv.amount_clp)}</td>
                  <td style={{ padding: "8px 10px" }}>
                    <span style={{
                      padding: "2px 8px", borderRadius: 12, fontSize: 11, fontWeight: 700,
                      background: (INV_COLORS[inv.status] || C.mute) + "20",
                      color: INV_COLORS[inv.status] || C.mute,
                    }}>
                      {inv.status}
                    </span>
                  </td>
                  <td style={{ padding: "8px 10px", color: C.mute, fontSize: 12 }}>
                    {inv.paid_at ? new Date(inv.paid_at).toLocaleDateString("es-CL") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
