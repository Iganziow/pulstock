"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { C } from "@/lib/theme";
import { setTokens } from "@/lib/api";
import { LogoIcon } from "@/components/ui/Logo";

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

export default function TrialPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [businessType, setBusinessType] = useState("minimarket");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setErrors({});

    // Client validation
    const errs: Record<string, string> = {};
    if (!email.trim()) errs.email = "Email es obligatorio";
    if (!password || password.length < 8) errs.password = "Mínimo 8 caracteres";
    if (!fullName.trim()) errs.full_name = "Tu nombre es obligatorio";
    if (!businessName.trim()) errs.business_name = "El nombre del negocio es obligatorio";
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }

    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/register/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password,
          full_name: fullName.trim(),
          business_name: businessName.trim(),
          business_type: businessType,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (data.errors) setErrors(data.errors);
        else setError(data?.detail || "No se pudo crear la cuenta");
        return;
      }
      if (data.tokens?.access) setTokens(data.tokens.access);
      router.push("/dashboard");
    } catch {
      setError("Error de conexión. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  const inputStyle = {
    width: "100%", padding: "11px 14px", border: `1px solid ${C.border}`,
    borderRadius: C.r, fontSize: 14, fontFamily: C.font, outline: "none",
    boxSizing: "border-box" as const,
  };

  return (
    <div style={{ minHeight: "100vh", background: `linear-gradient(135deg, #FAFAFA 0%, #EEF2FF 50%, #F5F3FF 100%)`, fontFamily: C.font, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 20px" }}>
      <div style={{ maxWidth: 440, width: "100%" }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 20 }}>
          <a href="/" style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 8 }}>
            <LogoIcon size={32} />
            <span style={{ fontSize: 22, fontWeight: 800, color: C.text }}>Pulstock</span>
          </a>
        </div>

        <div style={{ background: "#fff", borderRadius: 16, border: `1px solid ${C.border}`, padding: "32px 28px", boxShadow: "0 10px 40px rgba(0,0,0,.08)" }}>
          {/* Trial badge */}
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "5px 12px", borderRadius: 99, fontSize: 11, fontWeight: 700,
            background: "#ECFDF5", color: "#16A34A", border: "1px solid #A7F3D0",
            marginBottom: 12,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#16A34A" }} />
            7 DÍAS GRATIS · SIN TARJETA
          </div>

          <h1 style={{ fontSize: 24, fontWeight: 900, color: C.text, margin: "0 0 6px", letterSpacing: "-0.02em" }}>
            Empieza a usar Pulstock hoy
          </h1>
          <p style={{ fontSize: 13, color: C.mute, margin: "0 0 24px" }}>
            Acceso completo por 7 días. Sin tarjeta, sin compromiso.
          </p>

          <form onSubmit={handleSubmit}>
            {/* Email */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 5 }}>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="juan@minegocio.cl" style={inputStyle} disabled={loading} />
              {errors.email && <div style={{ fontSize: 11, color: C.red, marginTop: 3 }}>{errors.email}</div>}
            </div>

            {/* Password */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 5 }}>Contraseña</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres" style={inputStyle} disabled={loading} />
              {errors.password && <div style={{ fontSize: 11, color: C.red, marginTop: 3 }}>{errors.password}</div>}
            </div>

            {/* Full name */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 5 }}>Tu nombre completo</label>
              <input value={fullName} onChange={e => setFullName(e.target.value)}
                placeholder="Juan Pérez" style={inputStyle} disabled={loading} />
              {errors.full_name && <div style={{ fontSize: 11, color: C.red, marginTop: 3 }}>{errors.full_name}</div>}
            </div>

            {/* Business name */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 5 }}>Nombre de tu negocio</label>
              <input value={businessName} onChange={e => setBusinessName(e.target.value)}
                placeholder="Cafetería El Tornillo" style={inputStyle} disabled={loading} />
              {errors.business_name && <div style={{ fontSize: 11, color: C.red, marginTop: 3 }}>{errors.business_name}</div>}
            </div>

            {/* Business type */}
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 5 }}>Tipo de negocio</label>
              <select value={businessType} onChange={e => setBusinessType(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer", background: "#fff" }} disabled={loading}>
                {BIZ_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>

            {error && (
              <div style={{ marginBottom: 14, padding: "9px 12px", borderRadius: C.r, background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red, fontSize: 12 }}>
                {error}
              </div>
            )}

            <button type="submit" disabled={loading}
              style={{
                width: "100%", padding: "14px", borderRadius: 10, border: "none",
                background: loading ? C.mid : `linear-gradient(135deg, ${C.accent}, #7C3AED)`,
                color: "#fff", fontSize: 15, fontWeight: 800, fontFamily: C.font,
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1,
                boxShadow: `0 4px 14px ${C.accent}40`,
              }}>
              {loading ? "Creando cuenta..." : "Empezar prueba gratis →"}
            </button>

            <p style={{ fontSize: 11, color: C.mute, textAlign: "center", margin: "14px 0 0" }}>
              Al registrarte aceptas nuestros términos. Cancela cuando quieras.
            </p>

            <div style={{ textAlign: "center", marginTop: 16, paddingTop: 16, borderTop: `1px solid ${C.border}`, fontSize: 13, color: C.mid }}>
              ¿Ya tienes cuenta? <a href="/login" style={{ color: C.accent, fontWeight: 600, textDecoration: "none" }}>Iniciar sesión</a>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
