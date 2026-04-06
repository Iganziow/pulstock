"use client";
import { LogoIcon } from "@/components/ui/Logo";
import { useEffect, useState } from "react";
import { C } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const LOGIN_CSS = `
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&family=JetBrains+Mono:wght@400;500&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'DM Sans','Helvetica Neue',system-ui,sans-serif;background:#F7F7F8}

@keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}

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
  width:100%;padding:15px 24px;border:none;border-radius:10px;
  font-size:15px;font-weight:700;font-family:'DM Sans',system-ui,sans-serif;
  color:#fff;background:linear-gradient(135deg,#4F46E5,#4338CA);cursor:pointer;
  transition:all 0.15s cubic-bezier(0.4,0,0.2,1);
  position:relative;overflow:hidden;
  box-shadow:0 2px 8px rgba(79,70,229,0.25);
}
.login-btn:hover:not(:disabled){background:linear-gradient(135deg,#4338CA,#3730A3);transform:translateY(-1px);box-shadow:0 4px 16px rgba(79,70,229,0.35)}
.login-btn:active:not(:disabled){transform:scale(0.98);box-shadow:none}
.login-btn:disabled{opacity:0.5;cursor:not-allowed;transform:none;box-shadow:none}
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

export default function LoginPage() {
  useLoginStyles();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

      if (!data.tenant_id && data.role === "") {
        localStorage.setItem("access", data.access);
        localStorage.setItem("is_superuser", "true");
        window.location.href = "/superadmin";
        return;
      }

      localStorage.setItem("access", data.access);
      window.location.href = "/dashboard";
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Error de conexión");
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
      <div className="grid-bg" />

      <span className="floating-icon" style={{ top: "12%", left: "8%", animationDelay: "0s" }}>📦</span>
      <span className="floating-icon" style={{ top: "25%", right: "12%", animationDelay: "0.5s" }}>🏷️</span>
      <span className="floating-icon" style={{ bottom: "20%", left: "15%", animationDelay: "1s" }}>📊</span>
      <span className="floating-icon" style={{ bottom: "30%", right: "8%", animationDelay: "1.5s" }}>🛒</span>

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
          borderRadius: 20,
          border: `1px solid ${C.border}`,
          boxShadow: "0 20px 60px rgba(0,0,0,.08), 0 0 0 1px rgba(0,0,0,.02)",
          padding: "40px 32px 36px",
        }}>

          {/* Logo + Brand */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 36 }}>
            <div style={{
              width: 64, height: 64, borderRadius: 16,
              display: "flex", alignItems: "center", justifyContent: "center",
              marginBottom: 16,
            }}>
              <LogoIcon size={64} />
            </div>
            <h1 style={{
              fontSize: 26, fontWeight: 800, color: C.text,
              letterSpacing: "-0.03em", margin: 0,
            }}>
              Pulstock
            </h1>
            <p style={{
              fontSize: 14, color: C.mute, marginTop: 6, fontWeight: 400,
            }}>
              Ingresa a tu cuenta
            </p>
          </div>

          {/* Error */}
          {err && (
            <div className="error-bar" style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "12px 16px", borderRadius: 12,
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
          <form onSubmit={onSubmit} style={{ display: "grid", gap: 18 }}>

            <div className="login-field">
              <label style={{
                display: "block", fontSize: 12, fontWeight: 600,
                color: C.mid, marginBottom: 7, letterSpacing: "0.02em",
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

            <div className="login-field">
              <label style={{
                display: "block", fontSize: 12, fontWeight: 600,
                color: C.mid, marginBottom: 7, letterSpacing: "0.02em",
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

            <div className="login-btn-wrap" style={{ marginTop: 6 }}>
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

        <p style={{
          textAlign: "center", fontSize: 12, color: C.mute,
          marginTop: 24, fontWeight: 400,
        }}>
          Sistema de inventario inteligente · Pulstock
        </p>
      </div>
    </div>
  );
}
