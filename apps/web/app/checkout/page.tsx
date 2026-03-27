"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { C } from "@/lib/theme";

type Plan = { key: string; name: string; price_clp: number; max_products: number; max_stores: number; max_users: number; has_forecast: boolean; has_abc: boolean; has_reports: boolean; has_transfers: boolean };

function fmt(n: number) { return Math.round(n).toLocaleString("es-CL"); }

export default function CheckoutPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: C.bg, fontFamily: C.font, color: C.mute }}>Cargando...</div>}>
      <CheckoutInner />
    </Suspense>
  );
}

function CheckoutInner() {
  const params = useSearchParams();
  const planParam = params.get("plan") || "";

  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedKey, setSelectedKey] = useState(planParam);
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [loadingPlans, setLoadingPlans] = useState(true);

  const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

  useEffect(() => {
    fetch(`${API}/billing/plans/`)
      .then(r => r.json())
      .then(data => {
        const list = (data || []).filter((p: Plan) => p.price_clp > 0);
        setPlans(list);
        if (!selectedKey && list.length > 0) setSelectedKey(list[0].key);
      })
      .catch(() => setError("No se pudo cargar los planes"))
      .finally(() => setLoadingPlans(false));
  }, [API, selectedKey]);

  const plan = plans.find(p => p.key === selectedKey);

  async function handleCheckout() {
    if (!email || !email.includes("@")) { setError("Ingresa un email válido"); return; }
    if (!plan) { setError("Selecciona un plan"); return; }

    setLoading(true); setError("");
    try {
      const res = await fetch(`${API}/billing/checkout/create/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, plan_key: selectedKey }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data?.detail || "Error al iniciar el pago"); return; }
      if (data.payment_url) {
        window.location.href = data.payment_url;
      } else {
        setError("No se obtuvo URL de pago");
      }
    } catch {
      setError("Error de conexión");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: C.bg, fontFamily: C.font, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 20px" }}>
      <div style={{ maxWidth: 480, width: "100%" }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <a href="/" style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 8 }}>
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none"><rect width="32" height="32" rx="8" fill={C.accent}/><path d="M9 22V10h6a4 4 0 010 8H9" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            <span style={{ fontSize: 20, fontWeight: 800, color: C.text }}>Pulstock</span>
          </a>
        </div>

        <div style={{ background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`, padding: "28px 24px", boxShadow: C.shMd }}>
          <h1 style={{ fontSize: 20, fontWeight: 800, color: C.text, margin: "0 0 4px" }}>Elige tu plan</h1>
          <p style={{ fontSize: 13, color: C.mute, margin: "0 0 20px" }}>Paga y accede inmediatamente a Pulstock.</p>

          {loadingPlans ? (
            <div style={{ textAlign: "center", padding: 20, color: C.mute, fontSize: 13 }}>Cargando planes...</div>
          ) : (
            <>
              {/* Plan selector */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
                {plans.map(p => (
                  <label key={p.key} onClick={() => setSelectedKey(p.key)} style={{
                    display: "flex", alignItems: "center", gap: 12, padding: "14px 16px",
                    borderRadius: C.r, cursor: "pointer",
                    border: `2px solid ${selectedKey === p.key ? C.accent : C.border}`,
                    background: selectedKey === p.key ? C.accentBg : C.surface,
                    transition: "all 0.15s ease",
                  }}>
                    <input type="radio" name="plan" checked={selectedKey === p.key} onChange={() => setSelectedKey(p.key)}
                      style={{ accentColor: C.accent, width: 16, height: 16 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 700, fontSize: 14, color: C.text }}>{p.name}</div>
                      <div style={{ fontSize: 11, color: C.mid, marginTop: 2 }}>
                        {p.max_products === -1 ? "Ilimitados" : `${p.max_products} productos`} · {p.max_stores === -1 ? "Ilimitados" : `${p.max_stores} local${p.max_stores > 1 ? "es" : ""}`}
                        {p.has_forecast ? " · Forecast IA" : ""}
                      </div>
                    </div>
                    <div style={{ fontWeight: 800, fontSize: 15, color: selectedKey === p.key ? C.accent : C.text }}>
                      ${fmt(p.price_clp)}<span style={{ fontSize: 10, fontWeight: 500, color: C.mute }}>/mes</span>
                    </div>
                  </label>
                ))}
              </div>

              {/* Email */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 6 }}>
                  Tu email
                </label>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="juan@mi-negocio.cl" autoFocus
                  onKeyDown={e => { if (e.key === "Enter" && !loading) handleCheckout(); }}
                  style={{
                    width: "100%", padding: "10px 14px", border: `1px solid ${C.border}`,
                    borderRadius: C.r, fontSize: 14, fontFamily: C.font, outline: "none",
                    boxSizing: "border-box",
                  }} />
                <div style={{ fontSize: 11, color: C.mute, marginTop: 4 }}>
                  Con este email crearás tu cuenta después del pago.
                </div>
              </div>

              {error && (
                <div style={{ marginBottom: 14, padding: "8px 12px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 12 }}>
                  {error}
                </div>
              )}

              {/* CTA */}
              <button onClick={handleCheckout} disabled={loading || !plan || !email}
                style={{
                  width: "100%", padding: "12px", borderRadius: C.r, border: "none",
                  background: loading ? C.mid : C.accent, color: "#fff",
                  fontSize: 15, fontWeight: 700, fontFamily: C.font,
                  cursor: loading ? "not-allowed" : "pointer",
                  opacity: loading || !plan || !email ? 0.6 : 1,
                  transition: "all 0.15s ease",
                }}>
                {loading ? "Procesando..." : plan ? `Pagar $${fmt(plan.price_clp)} con Flow` : "Selecciona un plan"}
              </button>

              {plan && (
                <div style={{ textAlign: "center", marginTop: 10, fontSize: 11, color: C.mute }}>
                  Serás redirigido a Flow.cl para completar el pago de forma segura.
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{ textAlign: "center", marginTop: 16 }}>
          <a href="/login" style={{ fontSize: 12, color: C.mid, textDecoration: "none" }}>
            ¿Ya tienes cuenta? <span style={{ color: C.accent, fontWeight: 600 }}>Iniciar sesión</span>
          </a>
        </div>
      </div>
    </div>
  );
}
