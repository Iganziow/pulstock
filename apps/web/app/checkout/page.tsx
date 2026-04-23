"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { C } from "@/lib/theme";
import { LogoIcon } from "@/components/ui/Logo";

type Plan = { key: string; name: string; price_clp: number; max_products: number; max_stores: number; max_users: number; has_forecast: boolean; has_abc: boolean; has_reports: boolean; has_transfers: boolean };

function fmt(n: number) { return Math.round(n).toLocaleString("es-CL"); }

function slugify(text: string): string {
  return text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30);
}

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

  // Plans
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedKey, setSelectedKey] = useState(planParam);
  const [loadingPlans, setLoadingPlans] = useState(true);

  // Business
  const [businessName, setBusinessName] = useState("");
  const [businessType, setBusinessType] = useState("retail");

  // Owner
  const [ownerName, setOwnerName] = useState("");
  const [ownerUser, setOwnerUser] = useState("");
  const [ownerUserEdited, setOwnerUserEdited] = useState(false);
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);

  // Email for Flow
  const [email, setEmail] = useState("");

  // UI
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState(1); // 1=negocio, 2=usuario+plan+pago

  // Guard sincrónico para doble-click. setLoading(true) es asíncrono — entre
  // dos clicks rápidos (<50ms) el estado puede no haberse propagado todavía
  // y los dos llegan al fetch. Con un useRef chequeamos antes del setState.
  const submittingRef = useRef(false);

  const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

  useEffect(() => {
    fetch(`${API}/billing/plans/`)
      .then(r => r.json())
      .then(data => {
        const list = (data || []).filter((p: Plan) => p.price_clp > 0);
        setPlans(list);
        if (!selectedKey && list.length > 0) setSelectedKey(list[0].key);
      })
      .catch(() => setError("No pudimos cargar los planes. Verifica tu conexión a internet y recarga la página."))
      .finally(() => setLoadingPlans(false));
  }, [API, selectedKey]);

  // Auto-generate username when business name or owner name changes
  useEffect(() => {
    if (ownerUserEdited) return;
    const slug = slugify(businessName);
    const firstName = ownerName.split(" ")[0]?.toLowerCase() || "";
    if (firstName && slug) {
      setOwnerUser(`${firstName}@${slug}`);
    } else if (firstName) {
      setOwnerUser(firstName);
    }
  }, [businessName, ownerName, ownerUserEdited]);

  const plan = plans.find(p => p.key === selectedKey);

  const BUSINESS_TYPES = [
    { value: "retail", label: "Minimarket / Retail", icon: "🏪" },
    { value: "restaurant", label: "Restaurant / Cafetería", icon: "🍽️" },
    { value: "hardware", label: "Ferretería", icon: "🔧" },
    { value: "wholesale", label: "Distribuidora", icon: "🚛" },
    { value: "pharmacy", label: "Farmacia", icon: "💊" },
    { value: "other", label: "Otro", icon: "📦" },
  ];

  function validateStep1(): boolean {
    if (!businessName.trim()) { setError("Ingresa el nombre de tu negocio"); return false; }
    if (businessName.trim().length < 3) { setError("El nombre debe tener al menos 3 caracteres"); return false; }
    setError("");
    return true;
  }

  function validateStep2(): boolean {
    if (!ownerName.trim()) { setError("Ingresa tu nombre completo"); return false; }
    if (!ownerUser.trim()) { setError("Ingresa un nombre de usuario"); return false; }
    if (ownerUser.includes(" ")) { setError("El usuario no puede tener espacios"); return false; }
    if (!password || password.length < 8) { setError("La contraseña debe tener al menos 8 caracteres"); return false; }
    if (!email || !email.includes("@")) { setError("Ingresa un email válido para el pago"); return false; }
    if (!plan) { setError("Selecciona un plan"); return false; }
    setError("");
    return true;
  }

  async function handleCheckout() {
    // Guard sincrónico contra doble-click. Si ya hay un fetch en vuelo,
    // el segundo click se ignora silenciosamente (sin error visible al user).
    if (submittingRef.current) return;
    if (!validateStep2()) return;

    submittingRef.current = true;
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API}/billing/checkout/create/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          plan_key: selectedKey,
          business_name: businessName.trim(),
          business_type: businessType,
          owner_name: ownerName.trim(),
          owner_username: ownerUser.trim(),
          owner_password: password,
        }),
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        // Mensajes amigables según el código HTTP del backend.
        if (res.status === 409) {
          // Conflicto: email o usuario ya tomado.
          setError(data?.detail || "Ya existe una cuenta con este email o nombre de usuario. Si es tuya, inicia sesión.");
        } else if (res.status === 502) {
          // Flow caído o error en el gateway.
          setError("El sistema de pagos no responde en este momento. Intenta de nuevo en 1 minuto.");
        } else if (res.status === 400) {
          setError(data?.detail || "Algunos datos son inválidos. Revisa el formulario y vuelve a intentar.");
        } else if (res.status === 429) {
          setError("Demasiados intentos. Espera unos minutos antes de volver a intentar.");
        } else {
          setError(data?.detail || "No pudimos iniciar el pago. Intenta de nuevo o contacta a soporte@pulstock.cl.");
        }
        return;
      }

      if (data.payment_url) {
        // Redirige a Flow. El user vuelve después a /checkout/complete.
        window.location.href = data.payment_url;
      } else {
        setError("Recibimos respuesta del servidor pero sin URL de pago. Intenta de nuevo o contacta a soporte@pulstock.cl.");
      }
    } catch {
      setError("Sin conexión a internet. Verifica tu WiFi o datos móviles y vuelve a intentar.");
    } finally {
      submittingRef.current = false;
      setLoading(false);
    }
  }

  const iS: React.CSSProperties = {
    width: "100%", padding: "11px 14px", border: `1.5px solid ${C.border}`,
    borderRadius: 10, fontSize: 14, fontFamily: C.font, outline: "none",
    boxSizing: "border-box" as const, transition: "border-color .15s",
  };

  return (
    <div style={{ minHeight: "100vh", background: `linear-gradient(135deg, #F7F7F8 0%, #EEF2FF 50%, #F7F7F8 100%)`, fontFamily: C.font, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 20px" }}>
      <div style={{ maxWidth: 520, width: "100%" }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <a href="/" style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 10 }}>
            <LogoIcon size={36} />
            <span style={{ fontSize: 22, fontWeight: 800, color: C.text }}>Pulstock</span>
          </a>
        </div>

        {/* Progress */}
        <div style={{ display: "flex", gap: 4, marginBottom: 20 }}>
          <div style={{ flex: 1, height: 4, borderRadius: 2, background: C.accent }} />
          <div style={{ flex: 1, height: 4, borderRadius: 2, background: step >= 2 ? C.accent : C.border, transition: "background .3s" }} />
        </div>

        <div style={{ background: C.surface, borderRadius: 16, border: `1px solid ${C.border}`, padding: "32px 28px", boxShadow: "0 8px 30px rgba(0,0,0,.06)" }}>

          {/* ═══ STEP 1: NEGOCIO ═══ */}
          {step === 1 && (
            <>
              <h1 style={{ fontSize: 22, fontWeight: 800, color: C.text, margin: "0 0 4px" }}>Tu negocio</h1>
              <p style={{ fontSize: 13, color: C.mute, margin: "0 0 24px" }}>Cuéntanos sobre tu local para configurar todo automáticamente.</p>

              {/* Business name */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, display: "block", marginBottom: 6 }}>
                  Nombre del negocio *
                </label>
                <input value={businessName} onChange={e => setBusinessName(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && validateStep1()) setStep(2); }}
                  placeholder="Cafetería El Tornillo, Minimarket Don Juan..."
                  autoFocus style={iS} />
              </div>

              {/* Business type */}
              <div style={{ marginBottom: 20 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, display: "block", marginBottom: 8 }}>
                  Tipo de negocio
                </label>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                  {BUSINESS_TYPES.map(bt => (
                    <button key={bt.value} type="button" onClick={() => setBusinessType(bt.value)} style={{
                      padding: "12px 8px", borderRadius: 10, cursor: "pointer", fontFamily: C.font,
                      border: `2px solid ${businessType === bt.value ? C.accent : C.border}`,
                      background: businessType === bt.value ? C.accentBg : C.surface,
                      display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                      transition: "all .12s",
                    }}>
                      <span style={{ fontSize: 20 }}>{bt.icon}</span>
                      <span style={{ fontSize: 10, fontWeight: 600, color: businessType === bt.value ? C.accent : C.mid, textAlign: "center", lineHeight: 1.2 }}>{bt.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {error && (
                <div style={{ marginBottom: 14, padding: "8px 12px", borderRadius: 8, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 12 }}>
                  {error}
                </div>
              )}

              <button onClick={() => { if (validateStep1()) setStep(2); }} style={{
                width: "100%", padding: "13px", borderRadius: 10, border: "none",
                background: `linear-gradient(135deg, ${C.accent}, #7C3AED)`, color: "#fff",
                fontSize: 15, fontWeight: 700, fontFamily: C.font, cursor: "pointer",
                boxShadow: `0 4px 14px ${C.accent}30`,
              }}>
                Continuar →
              </button>
            </>
          )}

          {/* ═══ STEP 2: USUARIO + PLAN + PAGO ═══ */}
          {step === 2 && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
                <button type="button" onClick={() => { setStep(1); setError(""); }} style={{
                  background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 2, display: "flex",
                }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
                </button>
                <div>
                  <h1 style={{ fontSize: 20, fontWeight: 800, color: C.text, margin: 0 }}>{businessName}</h1>
                  <p style={{ fontSize: 12, color: C.mute, margin: 0 }}>Configura tu cuenta y elige plan</p>
                </div>
              </div>

              {/* Owner name */}
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, display: "block", marginBottom: 5 }}>Tu nombre completo *</label>
                <input value={ownerName} onChange={e => setOwnerName(e.target.value)}
                  placeholder="Juan Pérez" style={iS} />
              </div>

              {/* Username (auto-generated) */}
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, display: "block", marginBottom: 5 }}>
                  Usuario para ingresar
                </label>
                <div style={{ position: "relative" }}>
                  <input value={ownerUser} onChange={e => { setOwnerUser(e.target.value); setOwnerUserEdited(true); }}
                    placeholder="juan@mi-negocio" style={{ ...iS, fontFamily: C.mono, paddingRight: 70 }} />
                  {ownerUserEdited && (
                    <button type="button" onClick={() => { setOwnerUserEdited(false); }} style={{
                      position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
                      background: C.accentBg, border: `1px solid ${C.accentBd}`, borderRadius: 6,
                      padding: "3px 8px", fontSize: 10, fontWeight: 600, color: C.accent,
                      cursor: "pointer", fontFamily: C.font,
                    }}>Auto</button>
                  )}
                </div>
                <div style={{ fontSize: 10, color: C.mute, marginTop: 3 }}>
                  Se genera automáticamente. Puedes editarlo.
                </div>
              </div>

              {/* Password */}
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, display: "block", marginBottom: 5 }}>Contraseña *</label>
                <div style={{ position: "relative" }}>
                  <input type={showPw ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)}
                    placeholder="Mínimo 8 caracteres" style={{ ...iS, paddingRight: 46 }} />
                  <button type="button" onClick={() => setShowPw(!showPw)} tabIndex={-1}
                    aria-label={showPw ? "Ocultar" : "Mostrar"}
                    style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 4, display: "flex" }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      {showPw ? <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></> : <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></>}
                    </svg>
                  </button>
                </div>
              </div>

              {/* Email for payment */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, display: "block", marginBottom: 5 }}>Email para el pago *</label>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="tu@email.com" style={iS} />
                <div style={{ fontSize: 10, color: C.mute, marginTop: 3 }}>
                  Flow.cl enviará la confirmación a este email.
                </div>
              </div>

              {/* Divider */}
              <div style={{ height: 1, background: C.border, margin: "20px 0" }} />

              {/* Plan selector */}
              <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, display: "block", marginBottom: 8 }}>Plan</label>
              {loadingPlans ? (
                <div style={{ textAlign: "center", padding: 16, color: C.mute, fontSize: 13 }}>Cargando planes...</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 16 }}>
                  {plans.map(p => (
                    <label key={p.key} onClick={() => setSelectedKey(p.key)} style={{
                      display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
                      borderRadius: 10, cursor: "pointer",
                      border: `2px solid ${selectedKey === p.key ? C.accent : C.border}`,
                      background: selectedKey === p.key ? C.accentBg : C.surface,
                      transition: "all .12s",
                    }}>
                      <input type="radio" name="plan" checked={selectedKey === p.key} onChange={() => setSelectedKey(p.key)}
                        style={{ accentColor: C.accent, width: 16, height: 16 }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 700, fontSize: 14, color: C.text }}>{p.name}</div>
                        <div style={{ fontSize: 10, color: C.mid, marginTop: 2 }}>
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
              )}

              {error && (
                <div style={{ marginBottom: 14, padding: "8px 12px", borderRadius: 8, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 12 }}>
                  {error}
                </div>
              )}

              {/* Preview */}
              {ownerUser && (
                <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 8, background: C.bg, border: `1px solid ${C.border}`, fontSize: 12 }}>
                  <div style={{ fontWeight: 700, color: C.mid, marginBottom: 4 }}>Resumen de tu cuenta:</div>
                  <div style={{ color: C.text }}>Negocio: <b>{businessName}</b></div>
                  <div style={{ color: C.text }}>Usuario: <b style={{ fontFamily: C.mono }}>{ownerUser}</b></div>
                  <div style={{ color: C.text }}>Plan: <b>{plan?.name}</b> — ${plan ? fmt(plan.price_clp) : "0"}/mes</div>
                </div>
              )}

              <button onClick={handleCheckout} disabled={loading || !plan || !email || !ownerUser || !password}
                style={{
                  width: "100%", padding: "13px", borderRadius: 10, border: "none",
                  background: loading ? C.mid : `linear-gradient(135deg, ${C.accent}, #7C3AED)`, color: "#fff",
                  fontSize: 15, fontWeight: 700, fontFamily: C.font,
                  cursor: loading ? "not-allowed" : "pointer",
                  opacity: loading || !plan || !email ? 0.6 : 1,
                  boxShadow: loading ? "none" : `0 4px 14px ${C.accent}30`,
                  transition: "all .15s",
                }}>
                {loading ? "Procesando..." : plan ? `Pagar $${fmt(plan.price_clp)} con Flow` : "Selecciona un plan"}
              </button>

              {plan && (
                <div style={{ textAlign: "center", marginTop: 10, fontSize: 11, color: C.mute }}>
                  Serás redirigido a Flow.cl para completar el pago.
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
