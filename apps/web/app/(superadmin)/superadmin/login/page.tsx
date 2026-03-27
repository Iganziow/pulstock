"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { setTokens, setSuperAdmin } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const C = {
  bg: "#0F172A", card: "#1E293B", border: "#334155",
  text: "#F1F5F9", mute: "#94A3B8", accent: "#6366F1",
  red: "#EF4444", white: "#FFFFFF",
};

export default function SuperadminLoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
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
        setError(data.detail || "Credenciales inválidas.");
        setLoading(false);
        return;
      }

      // Verificar que es superuser (is_superuser viene en el body, no en el JWT)
      if (!data.is_superuser) {
        setError("Acceso denegado. Esta cuenta no tiene permisos de administrador.");
        setLoading(false);
        return;
      }

      setTokens(data.access);
      setSuperAdmin(true);
      router.replace("/superadmin");
    } catch {
      setError("Error de conexión. Verifica que el servidor esté activo.");
    } finally {
      setLoading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "12px 14px", borderRadius: 10,
    background: C.bg, border: `1px solid ${C.border}`,
    color: C.text, fontSize: 14, outline: "none",
    transition: "border-color .2s",
  };

  return (
    <div style={{
      minHeight: "100vh", background: C.bg,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "'Inter', sans-serif",
    }}>
      {/* Partículas decorativas */}
      <div style={{ position: "fixed", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
        {[...Array(6)].map((_, i) => (
          <div key={i} style={{
            position: "absolute",
            width: 300 + i * 100, height: 300 + i * 100,
            borderRadius: "50%",
            background: `radial-gradient(circle, ${C.accent}08, transparent)`,
            top: `${10 + i * 15}%`, left: `${5 + i * 12}%`,
          }} />
        ))}
      </div>

      <div style={{
        width: 400, maxWidth: "90vw", position: "relative", zIndex: 1,
      }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{
            width: 56, height: 56, borderRadius: 14, margin: "0 auto 16px",
            background: `linear-gradient(135deg, ${C.accent}, #8B5CF6)`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 24, fontWeight: 900, color: C.white,
            boxShadow: `0 8px 32px ${C.accent}44`,
          }}>
            P
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: C.white, margin: 0 }}>
            Pulstock Admin
          </h1>
          <p style={{ fontSize: 13, color: C.mute, margin: "6px 0 0" }}>
            Panel de administración de la plataforma
          </p>
        </div>

        {/* Card */}
        <div style={{
          background: C.card, border: `1px solid ${C.border}`,
          borderRadius: 16, padding: 28,
          boxShadow: "0 4px 24px rgba(0,0,0,.3)",
        }}>
          {error && (
            <div style={{
              padding: "10px 14px", borderRadius: 10, marginBottom: 16,
              background: C.red + "15", border: `1px solid ${C.red}33`,
              color: C.red, fontSize: 13,
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <span style={{ fontSize: 16 }}>⚠</span>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: C.mute, marginBottom: 6 }}>
                Usuario
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
                autoComplete="username"
                autoFocus
                required
                style={inputStyle}
                onFocus={(e) => e.currentTarget.style.borderColor = C.accent}
                onBlur={(e) => e.currentTarget.style.borderColor = C.border}
              />
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: C.mute, marginBottom: 6 }}>
                Contraseña
              </label>
              <div style={{ position: "relative" }}>
                <input
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                  style={{ ...inputStyle, paddingRight: 44 }}
                  onFocus={(e) => e.currentTarget.style.borderColor = C.accent}
                  onBlur={(e) => e.currentTarget.style.borderColor = C.border}
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  style={{
                    position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", color: C.mute, cursor: "pointer",
                    fontSize: 16, padding: 4,
                  }}
                >
                  {showPw ? "🙈" : "👁"}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !username || !password}
              style={{
                width: "100%", padding: "12px 0", borderRadius: 10,
                background: loading ? C.mute : `linear-gradient(135deg, ${C.accent}, #8B5CF6)`,
                color: C.white, fontSize: 14, fontWeight: 700,
                border: "none", cursor: loading ? "wait" : "pointer",
                transition: "all .2s",
                boxShadow: loading ? "none" : `0 4px 16px ${C.accent}44`,
              }}
            >
              {loading ? "Verificando..." : "Acceder al panel"}
            </button>
          </form>
        </div>

        <p style={{ textAlign: "center", fontSize: 11, color: C.mute + "88", marginTop: 20 }}>
          Acceso restringido a administradores de la plataforma
        </p>
      </div>
    </div>
  );
}
