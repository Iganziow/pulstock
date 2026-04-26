"use client";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Card } from "./SettingsUI";
import { humanizeError } from "@/lib/errors";

interface PlanTabProps {
  mob: boolean;
  flash: (type: "ok" | "err", text: string) => void;
  tenantCreatedAt?: string;
}

type SubPlan = {
  key: string; name: string; price_clp: number; trial_days: number;
  max_products: number; max_stores: number; max_users: number;
  has_forecast: boolean; has_abc: boolean; has_reports: boolean; has_transfers: boolean;
};
type SubInvoice = {
  id: number; status: string; amount_clp: number;
  period_start: string; period_end: string;
  paid_at: string | null; payment_url: string | null; created_at: string;
};
type SubData = {
  status: string; status_label: string; is_access_allowed: boolean;
  plan: SubPlan; trial_ends_at: string | null; current_period_end: string | null;
  days_remaining: number | null; payment_retry_count: number;
  next_retry_at: string | null; recent_invoices: SubInvoice[];
  has_card: boolean; card_brand: string; card_last4: string;
};

const CLP = (n: number) =>
  new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", minimumFractionDigits: 0 }).format(n);
const fmtD = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("es-CL", { day: "numeric", month: "long", year: "numeric" }) : "—";

const ST_CFG: Record<string, { label: string; color: string; bg: string; bd: string }> = {
  trialing:  { label: "Período de prueba", color: "#2563EB", bg: "#EFF6FF", bd: "#BFDBFE" },
  active:    { label: "Activa",            color: "#16A34A", bg: "#ECFDF5", bd: "#A7F3D0" },
  past_due:  { label: "Pago pendiente",    color: "#D97706", bg: "#FFFBEB", bd: "#FDE68A" },
  suspended: { label: "Suspendida",        color: "#DC2626", bg: "#FEF2F2", bd: "#FECACA" },
  cancelled: { label: "Cancelada",         color: "#71717A", bg: "#F4F4F5", bd: "#E4E4E7" },
};
const INV_ST: Record<string, { label: string; color: string }> = {
  pending: { label: "Pendiente", color: "#D97706" },
  paid:    { label: "Pagada",    color: "#16A34A" },
  failed:  { label: "Fallida",   color: "#DC2626" },
  voided:  { label: "Anulada",   color: "#71717A" },
};

export default function PlanTab({ mob, flash, tenantCreatedAt }: PlanTabProps) {
  const [sub, setSub] = useState<SubData | null>(null);
  const [plans, setPlans] = useState<SubPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [payUrl, setPayUrl] = useState<string | null>(null);
  const [showCancel, setShowCancel] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [s, p] = await Promise.all([
        apiFetch("/billing/subscription/"),
        apiFetch("/billing/plans/"),
      ]);
      setSub(s); setPlans(p);
    } catch { flash("err", "No se pudo cargar la suscripción."); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  // Confirmar pago si hay token en la URL (retorno de Flow)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (!token) return;
    (async () => {
      setBusy(true);
      try {
        const res = await apiFetch("/billing/subscription/confirm-payment/", {
          method: "POST", body: JSON.stringify({ token }),
        });
        if (res.ok || res.status === "already_paid") {
          flash("ok", res.detail || "Pago confirmado exitosamente.");
          setPayUrl(null);
          await load();
        } else {
          flash("err", res.detail || "El pago fue rechazado.");
        }
      } catch (e: any) {
        flash("err", e?.data?.detail || "Error verificando el pago.");
      } finally {
        setBusy(false);
        const url = new URL(window.location.href);
        url.searchParams.delete("token");
        url.searchParams.delete("tab");
        window.history.replaceState({}, "", url.toString());
      }
    })();
  }, []);

  // Guard sincrónico para que dos clicks rápidos en el botón "Pagar" no
  // creen 2 invoices duplicadas. setBusy es async (React puede deferir el
  // re-render), así que el botón disabled NO es suficiente. El useRef
  // chequea ANTES del fetch en el mismo tick.
  const payingRef = useRef(false);
  const handlePay = async () => {
    if (payingRef.current) return;
    payingRef.current = true;
    setBusy(true);
    try {
      const data = await apiFetch("/billing/subscription/pay/", { method: "POST", body: JSON.stringify({}) });
      if (data.payment_url) {
        window.location.href = data.payment_url;
      } else {
        flash("err", "No recibimos un link de pago. Intenta de nuevo.");
      }
    } catch (e: any) {
      // apiFetch tiene timeout 30s — si lo superó, mensaje específico.
      if (e?.name === "AbortError" || e?.message?.includes("timeout")) {
        flash("err", "El servidor tardó demasiado. Verifica tu conexión y vuelve a intentar.");
      } else {
        flash("err", "No se pudo generar el link de pago.");
      }
    }
    finally {
      payingRef.current = false;
      setBusy(false);
    }
  };

  const handleUpgrade = async (key: string) => {
    if (!sub || key === sub.plan.key) return;
    setBusy(true);
    try {
      const data = await apiFetch("/billing/subscription/upgrade/", {
        method: "POST", body: JSON.stringify({ plan: key }),
      });
      setSub(data);
      if (data.payment_url) {
        window.location.href = data.payment_url;
      } else {
        flash("ok", "Plan actualizado.");
      }
    } catch (e: any) {
      flash("err", e?.data?.detail || "Error al cambiar de plan.");
    } finally { setBusy(false); }
  };

  const handleCancel = async () => {
    setBusy(true);
    try {
      await apiFetch("/billing/subscription/cancel/", { method: "POST", body: JSON.stringify({}) });
      setShowCancel(false);
      flash("ok", "Suscripción cancelada. Tu acceso continúa hasta el fin del período.");
      await load();
    } catch (e: any) {
      flash("err", e?.data?.detail || "Error al cancelar.");
    } finally { setBusy(false); }
  };

  const handleReactivate = async () => {
    setBusy(true);
    try {
      const data = await apiFetch("/billing/subscription/reactivate/", { method: "POST", body: JSON.stringify({}) });
      if (data.payment_url) {
        window.location.href = data.payment_url;
      } else {
        flash("ok", "Suscripción reactivada.");
        await load();
      }
    } catch (e: any) {
      if (e?.data?.payment_url) window.location.href = e.data.payment_url;
      else flash("err", humanizeError(e, "Error al reactivar."));
    } finally { setBusy(false); }
  };

  // Tarjeta de crédito
  const handleRegisterCard = async () => {
    setBusy(true);
    try {
      const data = await apiFetch("/billing/subscription/card/", { method: "POST", body: JSON.stringify({}) });
      if (data.register_url) window.location.href = data.register_url;
    } catch (e: any) {
      flash("err", e?.data?.detail || "Error al iniciar registro de tarjeta.");
    } finally { setBusy(false); }
  };

  const handleRemoveCard = async () => {
    setBusy(true);
    try {
      await apiFetch("/billing/subscription/card/remove/", { method: "POST", body: JSON.stringify({}) });
      flash("ok", "Tarjeta eliminada.");
      await load();
    } catch (e: any) {
      flash("err", e?.data?.detail || "Error al eliminar tarjeta.");
    } finally { setBusy(false); }
  };

  // Detectar retorno de registro de tarjeta
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const card = params.get("card");
    if (card === "ok") {
      flash("ok", "Tarjeta registrada exitosamente. Los próximos cobros se harán automáticamente.");
      load();
    } else if (card === "fail") {
      flash("err", "No se pudo registrar la tarjeta. Intenta nuevamente.");
    }
    if (card) {
      const url = new URL(window.location.href);
      url.searchParams.delete("card");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: 40, color: C.mute }}>
      <div style={{ width: 18, height: 18, border: `2px solid ${C.border}`, borderTopColor: C.accent, borderRadius: "50%", animation: "spin .7s linear infinite" }} />
      Cargando suscripción...
    </div>
  );
  if (!sub) return <Card><div style={{ color: C.mute, fontSize: 13 }}>Sin datos de suscripción.</div></Card>;

  const sc = ST_CFG[sub.status] || ST_CFG.cancelled;
  const isFree = sub.plan.price_clp === 0;
  const isTrial = sub.status === "trialing";
  const isPD = sub.status === "past_due";
  const isSusp = sub.status === "suspended";
  const isCanc = sub.status === "cancelled";

  const pb: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: "pointer", border: "none", fontFamily: "inherit", minHeight: 40 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

      {/* Alerta pago pendiente */}
      {isPD && (
        <Card style={{ borderColor: "#FDE68A", background: "#FFFBEB" }} padding={14}>
          <div style={{ display: "flex", alignItems: mob ? "stretch" : "center", gap: 12, flexDirection: mob ? "column" : "row" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, color: "#92400E", fontSize: 13 }}>⚠ Pago pendiente</div>
              <div style={{ fontSize: 12, color: "#78350F", marginTop: 2 }}>
                Intento {sub.payment_retry_count} de 3.
                {sub.next_retry_at && ` Próximo reintento: ${fmtD(sub.next_retry_at)}.`}
              </div>
            </div>
            <button onClick={handlePay} disabled={busy} style={{ ...pb, background: C.accent, color: "#fff" }}>
              💳 Pagar ahora
            </button>
          </div>
        </Card>
      )}

      {/* Alerta suspendida */}
      {isSusp && (
        <Card style={{ borderColor: "#FECACA", background: "#FEF2F2" }} padding={14}>
          <div style={{ display: "flex", alignItems: mob ? "stretch" : "center", gap: 12, flexDirection: mob ? "column" : "row" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, color: "#991B1B", fontSize: 13 }}>🔒 Cuenta suspendida</div>
              <div style={{ fontSize: 12, color: "#7F1D1D", marginTop: 2 }}>Tu acceso está bloqueado por falta de pago.</div>
            </div>
            <button onClick={handleReactivate} disabled={busy} style={{ ...pb, background: "#DC2626", color: "#fff" }}>
              Reactivar cuenta
            </button>
          </div>
        </Card>
      )}

      {/* Estado actual */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span style={{
                padding: "3px 10px", borderRadius: 99, fontSize: 11, fontWeight: 700,
                background: sc.bg, color: sc.color, border: `1px solid ${sc.bd}`
              }}>{sc.label}</span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-.03em" }}>
              {sub.plan.name}
              {!isFree && <span style={{ fontSize: 14, fontWeight: 500, color: C.mute, marginLeft: 8 }}>{CLP(sub.plan.price_clp)}/mes</span>}
            </div>
          </div>
          <div style={{ textAlign: mob ? "left" : "right" }}>
            {isTrial && sub.trial_ends_at && (
              <>
                <div style={{ fontSize: 11, color: C.mute }}>Trial vence</div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{fmtD(sub.trial_ends_at)}</div>
                <div style={{ fontSize: 12, color: sub.days_remaining! <= 3 ? C.red : C.mid }}>{sub.days_remaining} días</div>
              </>
            )}
            {!isTrial && sub.current_period_end && !isFree && (
              <>
                <div style={{ fontSize: 11, color: C.mute }}>Próximo cobro</div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{fmtD(sub.current_period_end)}</div>
                <div style={{ fontSize: 12, color: sub.days_remaining! <= 3 ? C.red : C.mid }}>{sub.days_remaining} días</div>
              </>
            )}
          </div>
        </div>

        {/* Límites */}
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 8, marginBottom: 16 }}>
          {[
            { l: "Productos", v: sub.plan.max_products === -1 ? "∞ ilimitados" : `hasta ${sub.plan.max_products}` },
            { l: "Locales",   v: sub.plan.max_stores === -1 ? "∞ ilimitados" : `hasta ${sub.plan.max_stores}` },
            { l: "Usuarios",  v: sub.plan.max_users === -1 ? "∞ ilimitados" : `hasta ${sub.plan.max_users}` },
            { l: "Forecast IA", v: sub.plan.has_forecast ? "✓ incluido" : "✗" },
            { l: "Análisis ABC", v: sub.plan.has_abc ? "✓ incluido" : "✗" },
            { l: "Transferencias", v: sub.plan.has_transfers ? "✓ incluido" : "✗" },
          ].map(i => (
            <div key={i.l} style={{ padding: "8px 12px", background: C.bg, borderRadius: 8, border: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 10, color: C.mute, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em" }}>{i.l}</div>
              <div style={{ fontSize: 13, fontWeight: 700, marginTop: 2, color: i.v.startsWith("✗") ? C.mute : i.v.startsWith("✓") ? C.green : C.text }}>{i.v}</div>
            </div>
          ))}
        </div>

        {/* Acciones */}
        {!isSusp && !isCanc && !isFree && (
          <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {isPD && <button onClick={handlePay} disabled={busy} style={{ ...pb, background: C.accent, color: "#fff" }}>💳 Pagar ahora</button>}
            <button onClick={() => setShowCancel(true)} disabled={busy}
              style={{ ...pb, background: "transparent", color: C.red, border: `1px solid #FECACA` }}>
              Cancelar suscripción
            </button>
          </div>
        )}
        {isCanc && (
          <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 14 }}>
            <button onClick={handleReactivate} disabled={busy} style={{ ...pb, background: C.accent, color: "#fff" }}>Reactivar suscripción</button>
          </div>
        )}
      </Card>

      {/* Método de pago */}
      {!isFree && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 10 }}>Método de pago</div>
          {sub.has_card ? (
            <div style={{ display: "flex", alignItems: mob ? "stretch" : "center", gap: 12, flexDirection: mob ? "column" : "row" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
                <div style={{ width: 44, height: 30, borderRadius: 6, background: C.bg, border: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 800, color: C.mid }}>
                  {sub.card_brand === "Visa" ? "VISA" : sub.card_brand === "Mastercard" ? "MC" : sub.card_brand?.slice(0, 4) || "CARD"}
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{sub.card_brand} •••• {sub.card_last4}</div>
                  <div style={{ fontSize: 11, color: C.green }}>Cobro automático activo</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={handleRegisterCard} disabled={busy}
                  style={{ ...pb, background: "transparent", color: C.mid, border: `1px solid ${C.border}`, fontSize: 12, padding: "6px 12px", minHeight: 34 }}>
                  Cambiar
                </button>
                <button onClick={handleRemoveCard} disabled={busy}
                  style={{ ...pb, background: "transparent", color: C.red, border: `1px solid #FECACA`, fontSize: 12, padding: "6px 12px", minHeight: 34 }}>
                  Eliminar
                </button>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: mob ? "stretch" : "center", gap: 12, flexDirection: mob ? "column" : "row" }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: C.mid }}>Sin tarjeta registrada. Los cobros se realizan manualmente.</div>
                <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>Registra tu tarjeta para activar el cobro automático mensual.</div>
              </div>
              <button onClick={handleRegisterCard} disabled={busy}
                style={{ ...pb, background: C.accent, color: "#fff", flexShrink: 0 }}>
                💳 Registrar tarjeta
              </button>
            </div>
          )}
        </Card>
      )}

      {/* Cuenta creada */}
      <Card style={{ borderColor: C.greenBd }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>✓</span>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: C.green }}>Cuenta activa</div>
            <div style={{ fontSize: 12, color: C.mute }}>Creada el {tenantCreatedAt ? new Date(tenantCreatedAt).toLocaleDateString("es-CL", { day: "numeric", month: "long", year: "numeric" }) : "—"}</div>
          </div>
        </div>
      </Card>

      {/* Cambiar plan */}
      <div style={{ fontSize: 14, fontWeight: 800 }}>Cambiar plan</div>
      <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
        {plans.map(p => {
          const cur = p.key === sub.plan.key;
          const up = p.price_clp > sub.plan.price_clp;
          return (
            <Card key={p.key} style={cur ? { borderColor: C.accent, boxShadow: `0 0 0 3px ${C.accentBg}` } : {}} padding={18}>
              {cur && <div style={{ textAlign: "center", background: C.accent, color: "#fff", padding: "3px 0", borderRadius: 99, fontSize: 10, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 8 }}>Plan actual</div>}
              <div style={{ fontSize: 13, fontWeight: 700, color: C.mid }}>{p.name}</div>
              <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-.04em", marginTop: 4 }}>
                {p.price_clp === 0 ? "Gratis" : <>{CLP(p.price_clp)}<span style={{ fontSize: 12, color: C.mute, fontWeight: 500 }}>/mes</span></>}
              </div>
              <ul style={{ listStyle: "none", margin: "10px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> {p.max_products === -1 ? "Productos ilimitados" : `Hasta ${p.max_products} productos`}</li>
                <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> {p.max_stores === -1 ? "Locales ilimitados" : `Hasta ${p.max_stores} local${p.max_stores > 1 ? "es" : ""}`}</li>
                <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> {p.max_users === -1 ? "Usuarios ilimitados" : `Hasta ${p.max_users} usuarios`}</li>
                {p.has_forecast && <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> Forecast IA</li>}
                {p.has_abc && <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> Análisis ABC</li>}
                {p.has_transfers && <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> Transferencias</li>}
              </ul>
              {!cur && (
                <button onClick={() => handleUpgrade(p.key)} disabled={busy}
                  style={{ ...pb, width: "100%", justifyContent: "center", marginTop: 12, ...(up ? { background: C.accent, color: "#fff" } : { background: "transparent", color: C.mid, border: `1.5px solid ${C.border}` }) }}>
                  {up ? `Subir a ${p.name}` : `Cambiar a ${p.name}`}
                </button>
              )}
            </Card>
          );
        })}
      </div>

      {/* Historial de pagos */}
      {sub.recent_invoices.length > 0 && (
        <>
          <div style={{ fontSize: 14, fontWeight: 800 }}>Historial de pagos</div>
          <Card padding={0}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: mob ? 500 : undefined }}>
                <thead>
                  <tr style={{ background: C.bg }}>
                    {["Período", "Monto", "Estado", "Fecha pago", ""].map(h => (
                      <th key={h} style={{ padding: "8px 12px", fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em", textAlign: "left" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sub.recent_invoices.map(inv => {
                    const is = INV_ST[inv.status] || { label: inv.status, color: C.mid };
                    return (
                      <tr key={inv.id} style={{ borderBottom: `1px solid ${C.bg}` }}>
                        <td style={{ padding: "10px 12px", fontSize: 12, fontFamily: "monospace" }}>{inv.period_start} → {inv.period_end}</td>
                        <td style={{ padding: "10px 12px", fontSize: 13, fontWeight: 700 }}>{CLP(inv.amount_clp)}</td>
                        <td style={{ padding: "10px 12px" }}>
                          <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 700, color: is.color, background: is.color + "18", border: `1px solid ${is.color}40` }}>{is.label}</span>
                        </td>
                        <td style={{ padding: "10px 12px", fontSize: 13 }}>{inv.paid_at ? fmtD(inv.paid_at) : "—"}</td>
                        <td style={{ padding: "10px 12px" }}>
                          {inv.payment_url && inv.status !== "paid" && (
                            <a href={inv.payment_url} style={{ fontSize: 12, color: C.accent, fontWeight: 600, textDecoration: "none" }}>Pagar →</a>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      {/* Modal cancelar */}
      {showCancel && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 999 }}>
          <div style={{ background: "#fff", borderRadius: 14, padding: 28, maxWidth: 420, width: "90%", boxShadow: "0 20px 60px rgba(0,0,0,.15)" }}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>⚠</div>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 8 }}>¿Cancelar suscripción?</div>
            <p style={{ fontSize: 13, color: C.mid, lineHeight: 1.6, marginBottom: 20 }}>
              Tu suscripción quedará activa hasta el <strong>{fmtD(sub.current_period_end)}</strong>.
              Después pasarás al plan Gratuito. Tus datos se conservan.
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setShowCancel(false)} style={{ ...pb, background: "transparent", color: C.mid, border: `1.5px solid ${C.border}` }}>No cancelar</button>
              <button onClick={handleCancel} disabled={busy} style={{ ...pb, background: "#DC2626", color: "#fff" }}>Sí, cancelar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
