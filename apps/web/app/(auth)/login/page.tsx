"use client";

import { useEffect, useState } from "react";
import { C } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// ─── Design tokens (consistent with dashboard/POS) ───────────────────────────


const LOGIN_CSS = `
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&family=JetBrains+Mono:wght@400;500&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'DM Sans','Helvetica Neue',system-ui,sans-serif;background:#F7F7F8}

@keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
@keyframes pulse{0%,100%{opacity:0.4}50%{opacity:0.8}}

.login-card{animation:fadeUp 0.5s cubic-bezier(0.22,1,0.36,1) both}
.login-field{animation:fadeUp 0.5s cubic-bezier(0.22,1,0.36,1) both}
.login-field:nth-child(1){animation-delay:0.1s}
.login-field:nth-child(2){animation-delay:0.15s}
.login-btn-wrap{animation:fadeUp 0.5s cubic-bezier(0.22,1,0.36,1) 0.2s both}

.login-input{
  width:100%;padding:14px 16px 14px 46px;border:1.5px solid #E4E4E7;border-radius:10px;
  font-size:14px;font-family:'DM Sans',system-ui,sans-serif;color:#18181B;
  background:#FFFFFF;transition:all 0.15s ease;outline:none;
}
.login-input::placeholder{color:#A1A1AA;font-weight:400}
.login-input:focus{border-color:#4F46E5;box-shadow:0 0 0 3px rgba(79,70,229,0.1)}
.login-input:hover:not(:focus){border-color:#D1D1D6}

.login-btn{
  width:100%;padding:14px 24px;border:none;border-radius:10px;
  font-size:15px;font-weight:700;font-family:'DM Sans',system-ui,sans-serif;
  color:#fff;background:#4F46E5;cursor:pointer;
  transition:all 0.15s cubic-bezier(0.4,0,0.2,1);
  position:relative;overflow:hidden;
}
.login-btn:hover:not(:disabled){background:#4338CA;transform:translateY(-1px);box-shadow:0 4px 16px rgba(79,70,229,0.3)}
.login-btn:active:not(:disabled){transform:scale(0.98);box-shadow:none}
.login-btn:disabled{opacity:0.6;cursor:not-allowed;transform:none}
.login-btn::after{
  content:'';position:absolute;top:0;left:0;right:0;bottom:0;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,0.1),transparent);
  background-size:200% 100%;animation:shimmer 2s infinite;
  pointer-events:none;opacity:0;transition:opacity 0.3s;
}
.login-btn:hover::after{opacity:1}

.error-bar{animation:fadeUp 0.3s ease both}

.grid-bg{
  position:absolute;inset:0;
  background-image:
    linear-gradient(rgba(79,70,229,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(79,70,229,0.03) 1px, transparent 1px);
  background-size:48px 48px;
  pointer-events:none;
}

.floating-icon{animation:float 3s ease-in-out infinite;opacity:0.12;position:absolute;font-size:28px;pointer-events:none;user-select:none}
`;

function useLoginStyles() {
  useEffect(() => {
    const id = "login-ds-v1";
    if (document.getElementById(id)) return;
    const el = document.createElement("style");
    el.id = id;
    el.textContent = LOGIN_CSS;
    document.head.appendChild(el);
  }, []);
}

// ─── SVG Icons ────────────────────────────────────────────────────────────────

function UserIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#A1A1AA" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
      <circle cx="12" cy="7" r="4"/>
    </svg>
  );
}

function LockIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#A1A1AA" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  );
}

function EyeIcon({ open }: { open: boolean }) {
  if (open) return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#A1A1AA" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  );
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#A1A1AA" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function LoginPage() {
  useLoginStyles();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const access = localStorage.getItem("access");
    if (access) window.location.replace("/dashboard");
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);

    try {
      const res = await fetch(`${API}/auth/token/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data?.detail || "Usuario o contraseña incorrectos");
      }

      // Superadmin sin tenant → redirigir al panel de administración
      if (data.is_superuser && !data.tenant_id) {
        localStorage.setItem("access", data.access);
        localStorage.setItem("is_superuser", "true");
        window.location.href = "/superadmin";
        return;
      }

      localStorage.setItem("access", data.access);
      window.location.href = "/dashboard";
    } catch (e: any) {
      setErr(e?.message ?? "Error de conexión");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      fontFamily: C.font,
      background: `linear-gradient(135deg, #F7F7F8 0%, #EEF2FF 50%, #F7F7F8 100%)`,
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Grid background */}
      <div className="grid-bg" />

      {/* Floating decorative icons */}
      <span className="floating-icon" style={{ top: "12%", left: "8%", animationDelay: "0s" }}>📦</span>
      <span className="floating-icon" style={{ top: "25%", right: "12%", animationDelay: "0.5s" }}>🏷️</span>
      <span className="floating-icon" style={{ bottom: "20%", left: "15%", animationDelay: "1s" }}>📊</span>
      <span className="floating-icon" style={{ bottom: "30%", right: "8%", animationDelay: "1.5s" }}>🛒</span>
      <span className="floating-icon" style={{ top: "60%", left: "5%", animationDelay: "2s" }}>📋</span>

      {/* Center card */}
      <div style={{
        margin: "auto",
        width: "100%",
        maxWidth: 420,
        padding: "20px",
        position: "relative",
        zIndex: 1,
      }}>
        <div className="login-card" style={{
          background: C.surface,
          borderRadius: "16px",
          border: `1px solid ${C.border}`,
          boxShadow: C.shLg,
          padding: "32px 20px 28px",
        }}>

          {/* Logo / Brand */}
          <div style={{ textAlign: "center", marginBottom: 32 }}>
            <div style={{
              width: 56, height: 56, borderRadius: 14,
              background: `linear-gradient(135deg, ${C.accent}, #7C3AED)`,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              marginBottom: 16,
              boxShadow: "0 4px 14px rgba(79,70,229,0.25)",
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                <line x1="12" y1="22.08" x2="12" y2="12"/>
              </svg>
            </div>
            <h1 style={{
              fontSize: 24, fontWeight: 800, color: C.text,
              letterSpacing: "-0.02em", margin: 0,
            }}>
              Pulstock
            </h1>
            <p style={{
              fontSize: 13, color: C.mute, marginTop: 6, fontWeight: 400,
            }}>
              Ingresa a tu cuenta para continuar
            </p>
          </div>

          {/* Error */}
          {err && (
            <div className="error-bar" style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "12px 14px", borderRadius: C.rMd,
              background: C.redBg, border: `1px solid ${C.redBd}`,
              marginBottom: 20,
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.red} strokeWidth="2.5" strokeLinecap="round">
                <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
              <span style={{ fontSize: 13, color: C.red, fontWeight: 500 }}>{err}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={onSubmit} style={{ display: "grid", gap: 16 }}>

            {/* Username */}
            <div className="login-field">
              <label style={{
                display: "block", fontSize: 12, fontWeight: 600,
                color: C.mid, marginBottom: 6, letterSpacing: "0.02em",
              }}>
                Usuario
              </label>
              <div style={{ position: "relative" }}>
                <div style={{
                  position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)",
                  display: "flex", pointerEvents: "none",
                }}>
                  <UserIcon />
                </div>
                <input
                  className="login-input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Tu nombre de usuario"
                  autoComplete="username"
                  autoFocus
                  required
                />
              </div>
            </div>

            {/* Password */}
            <div className="login-field">
              <label style={{
                display: "block", fontSize: 12, fontWeight: 600,
                color: C.mid, marginBottom: 6, letterSpacing: "0.02em",
              }}>
                Contraseña
              </label>
              <div style={{ position: "relative" }}>
                <div style={{
                  position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)",
                  display: "flex", pointerEvents: "none",
                }}>
                  <LockIcon />
                </div>
                <input
                  className="login-input"
                  style={{ paddingRight: 46 }}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  type={showPw ? "text" : "password"}
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  style={{
                    position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", cursor: "pointer",
                    display: "flex", padding: 4,
                  }}
                  tabIndex={-1}
                  aria-label={showPw ? "Ocultar contraseña" : "Mostrar contraseña"}
                >
                  <EyeIcon open={showPw} />
                </button>
              </div>
            </div>

            {/* Submit */}
            <div className="login-btn-wrap" style={{ marginTop: 4 }}>
              <button className="login-btn" type="submit" disabled={loading || !username || !password}>
                {loading ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                    <svg width={16} height={16} viewBox="0 0 24 24" fill="none"
                      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                      style={{ animation: "spin 0.7s linear infinite" }}>
                      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                    </svg>
                    Ingresando...
                  </span>
                ) : "Ingresar"}
              </button>
            </div>
          </form>
        </div>

        {/* Footer */}
        <p style={{
          textAlign: "center", fontSize: 12, color: C.mute,
          marginTop: 20, fontWeight: 400,
        }}>
          Sistema de inventario y punto de venta · Pulstock
        </p>
      </div>
    </div>
  );
}