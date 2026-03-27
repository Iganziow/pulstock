"use client";

import { Suspense, useEffect, useState, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { C } from "@/lib/theme";
import { setTokens } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const BIZ_TYPES = [
  { value: "minimarket", label: "Minimarket / Almacén" },
  { value: "ferreteria", label: "Ferretería" },
  { value: "farmacia", label: "Farmacia" },
  { value: "ropa", label: "Tienda de ropa" },
  { value: "libreria", label: "Librería / Bazar" },
  { value: "restaurant", label: "Restaurant / Café" },
  { value: "otro", label: "Otro" },
];

function fmt(n: number) { return Math.round(n).toLocaleString("es-CL"); }

type SessionStatus = { status: string; plan_name: string; plan_key: string; email_masked: string; amount_clp: number };

export default function CheckoutCompletePage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: C.bg, fontFamily: C.font, color: C.mute }}>Cargando...</div>}>
      <CheckoutCompleteInner />
    </Suspense>
  );
}

function CheckoutCompleteInner() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";

  const [session, setSession] = useState<SessionStatus | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCount = useRef(0);

  // Form state
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [businessType, setBusinessType] = useState("minimarket");
  const [storeName, setStoreName] = useState("Mi Local");
  const [warehouseName, setWarehouseName] = useState("Bodega Principal");
  const [submitting, setSubmitting] = useState(false);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!token) { setError("Token no proporcionado"); setChecking(false); return; }
    checkStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function checkStatus() {
    try {
      const res = await fetch(`${API}/billing/checkout/status/?token=${token}`);
      const data = await res.json();
      if (!res.ok) { setError(data?.detail || "Sesión no encontrada"); setChecking(false); return; }
      setSession(data);

      if (data.status === "pending") {
        // Start polling
        if (!pollRef.current) {
          pollRef.current = setInterval(async () => {
            pollCount.current++;
            if (pollCount.current > 10) {
              if (pollRef.current) clearInterval(pollRef.current);
              setError("El pago no se ha confirmado. Intenta de nuevo.");
              return;
            }
            try {
              const r = await fetch(`${API}/billing/checkout/status/?token=${token}`);
              const d = await r.json();
              if (d.status !== "pending") {
                setSession(d);
                if (pollRef.current) clearInterval(pollRef.current);
              }
            } catch { /* retry */ }
          }, 3000);
        }
      }
    } catch {
      setError("Error de conexión");
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => { return () => { if (pollRef.current) clearInterval(pollRef.current); }; }, []);

  async function handleSubmit() {
    const errs: Record<string, string> = {};
    if (!password || password.length < 6) errs.password = "Mínimo 6 caracteres";
    if (!fullName.trim()) errs.full_name = "Tu nombre es obligatorio";
    if (!businessName.trim()) errs.business_name = "El nombre de tu negocio es obligatorio";
    if (Object.keys(errs).length > 0) { setFormErrors(errs); return; }

    setSubmitting(true); setFormErrors({}); setError("");
    try {
      const res = await fetch(`${API}/billing/checkout/complete/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          token,
          password,
          full_name: fullName,
          business_name: businessName,
          business_type: businessType,
          store_name: storeName || "Mi Local",
          warehouses: [warehouseName || "Bodega Principal"],
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (data.errors) setFormErrors(data.errors);
        else setError(data?.detail || "Error al crear la cuenta");
        return;
      }
      // Save tokens and redirect
      if (data.tokens?.access) {
        setTokens(data.tokens.access);
      }
      router.push("/dashboard");
    } catch {
      setError("Error de conexión");
    } finally {
      setSubmitting(false);
    }
  }

  const inputStyle = {
    width: "100%", padding: "10px 14px", border: `1px solid ${C.border}`,
    borderRadius: C.r, fontSize: 14, fontFamily: C.font, outline: "none",
    boxSizing: "border-box" as const,
  };

  return (
    <div style={{ minHeight: "100vh", background: C.bg, fontFamily: C.font, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 20px" }}>
      <div style={{ maxWidth: 480, width: "100%" }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <a href="/" style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 8 }}>
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none"><rect width="32" height="32" rx="8" fill={C.accent}/><path d="M9 22V10h6a4 4 0 010 8H9" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            <span style={{ fontSize: 20, fontWeight: 800, color: C.text }}>Pulstock</span>
          </a>
        </div>

        <div style={{ background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`, padding: "28px 24px", boxShadow: C.shMd }}>

          {/* CHECKING */}
          {checking && (
            <div style={{ textAlign: "center", padding: 30 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: C.mid }}>Verificando pago...</div>
            </div>
          )}

          {/* PENDING — polling */}
          {!checking && session?.status === "pending" && (
            <div style={{ textAlign: "center", padding: 30 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>{"⏳"}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>Verificando tu pago</div>
              <div style={{ fontSize: 13, color: C.mute }}>Esto puede tomar unos segundos...</div>
            </div>
          )}

          {/* PAID — Registration form */}
          {!checking && session?.status === "paid" && (
            <>
              <div style={{ padding: "10px 14px", borderRadius: C.r, background: C.greenBg, border: `1px solid ${C.greenBd}`, marginBottom: 20, display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 18 }}>{"✓"}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.green }}>Pago confirmado — ${fmt(session.amount_clp)}</div>
                  <div style={{ fontSize: 11, color: C.mid }}>{session.plan_name} · {session.email_masked}</div>
                </div>
              </div>

              <h2 style={{ fontSize: 18, fontWeight: 800, color: C.text, margin: "0 0 4px" }}>Configura tu cuenta</h2>
              <p style={{ fontSize: 12, color: C.mute, margin: "0 0 18px" }}>Solo necesitamos unos datos para activar Pulstock.</p>

              {/* Full name */}
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 4 }}>Tu nombre completo</label>
                <input value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Juan Pérez" style={inputStyle} />
                {formErrors.full_name && <div style={{ fontSize: 11, color: C.red, marginTop: 2 }}>{formErrors.full_name}</div>}
              </div>

              {/* Password */}
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 4 }}>Contraseña</label>
                <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Mínimo 6 caracteres" style={inputStyle} />
                {formErrors.password && <div style={{ fontSize: 11, color: C.red, marginTop: 2 }}>{formErrors.password}</div>}
              </div>

              {/* Business name */}
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 4 }}>Nombre del negocio</label>
                <input value={businessName} onChange={e => setBusinessName(e.target.value)} placeholder="Ferretería El Tornillo" style={inputStyle} />
                {formErrors.business_name && <div style={{ fontSize: 11, color: C.red, marginTop: 2 }}>{formErrors.business_name}</div>}
              </div>

              {/* Business type */}
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 4 }}>Tipo de negocio</label>
                <select value={businessType} onChange={e => setBusinessType(e.target.value)}
                  style={{ ...inputStyle, cursor: "pointer", background: C.surface }}>
                  {BIZ_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>

              {/* Store name */}
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 4 }}>
                  Nombre de tu local <span style={{ color: C.mute, fontWeight: 400 }}>(puedes agregar más después)</span>
                </label>
                <input value={storeName} onChange={e => setStoreName(e.target.value)} placeholder="Mi Local" style={inputStyle} />
              </div>

              {/* Warehouse */}
              <div style={{ marginBottom: 20 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 4 }}>
                  Bodega principal
                </label>
                <input value={warehouseName} onChange={e => setWarehouseName(e.target.value)} placeholder="Bodega Principal" style={inputStyle} />
              </div>

              {error && (
                <div style={{ marginBottom: 14, padding: "8px 12px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 12 }}>
                  {error}
                </div>
              )}
              {formErrors.email && (
                <div style={{ marginBottom: 14, padding: "8px 12px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 12 }}>
                  {formErrors.email} <a href="/login" style={{ color: C.accent, fontWeight: 600 }}>Ir a login</a>
                </div>
              )}

              <button onClick={handleSubmit} disabled={submitting}
                style={{
                  width: "100%", padding: "12px", borderRadius: C.r, border: "none",
                  background: submitting ? C.mid : C.accent, color: "#fff",
                  fontSize: 15, fontWeight: 700, fontFamily: C.font,
                  cursor: submitting ? "not-allowed" : "pointer",
                  opacity: submitting ? 0.6 : 1,
                }}>
                {submitting ? "Creando cuenta..." : "Activar Pulstock"}
              </button>
            </>
          )}

          {/* COMPLETED */}
          {!checking && session?.status === "completed" && (
            <div style={{ textAlign: "center", padding: 20 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>{"✓"}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>Cuenta ya creada</div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 16 }}>Ya completaste tu registro con este pago.</div>
              <a href="/login" style={{
                display: "inline-block", padding: "10px 24px", borderRadius: C.r,
                background: C.accent, color: "#fff", fontSize: 14, fontWeight: 700,
                textDecoration: "none",
              }}>Iniciar sesión</a>
            </div>
          )}

          {/* EXPIRED */}
          {!checking && (session?.status === "expired" || (!session && error)) && (
            <div style={{ textAlign: "center", padding: 20 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>{"⚠️"}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>
                {session?.status === "expired" ? "Sesión expirada" : "Error"}
              </div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 16 }}>
                {error || "El pago no se completó a tiempo. Intenta de nuevo."}
              </div>
              <a href="/#precios" style={{
                display: "inline-block", padding: "10px 24px", borderRadius: C.r,
                background: C.accent, color: "#fff", fontSize: 14, fontWeight: 700,
                textDecoration: "none",
              }}>Volver a planes</a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
