"use client";

import { Suspense, useEffect, useState, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { C } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

function fmt(n: number) { return Math.round(n).toLocaleString("es-CL"); }

type SessionStatus = { status: string; plan_name: string; plan_key: string; email_masked: string; amount_clp: number; username?: string };

export default function CheckoutCompletePage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: C.bg, fontFamily: C.font, color: C.mute }}>Cargando...</div>}>
      <CheckoutCompleteInner />
    </Suspense>
  );
}

function CheckoutCompleteInner() {
  const params = useSearchParams();
  const token = params.get("token") || "";

  const [session, setSession] = useState<SessionStatus | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCount = useRef(0);

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

      // Poll while pending OR paid (waiting for webhook to auto-create)
      if (data.status === "pending" || data.status === "paid") {
        if (!pollRef.current) {
          pollRef.current = setInterval(async () => {
            pollCount.current++;
            if (pollCount.current > 20) {
              if (pollRef.current) clearInterval(pollRef.current);
              return;
            }
            try {
              const r = await fetch(`${API}/billing/checkout/status/?token=${token}`);
              const d = await r.json();
              setSession(d);
              if (d.status === "completed" || d.status === "expired") {
                if (pollRef.current) clearInterval(pollRef.current);
              }
            } catch { /* retry */ }
          }, 2000);
        }
      }
    } catch {
      setError("Error de conexión");
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => { return () => { if (pollRef.current) clearInterval(pollRef.current); }; }, []);

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

          {/* PAID — creating account automatically */}
          {!checking && session?.status === "paid" && (
            <div style={{ textAlign: "center", padding: 30 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>✓</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.green, marginBottom: 6 }}>Pago confirmado — ${fmt(session.amount_clp)}</div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 16 }}>
                Creando tu cuenta... {session.plan_name}
              </div>
              <div style={{ display: "inline-block", width: 24, height: 24, border: `3px solid ${C.border}`, borderTopColor: C.accent, borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </div>
          )}


          {/* COMPLETED */}
          {!checking && session?.status === "completed" && (
            <div style={{ textAlign: "center", padding: 20 }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>🎉</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: C.text, marginBottom: 6 }}>¡Tu cuenta está lista!</div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 6 }}>
                Plan {session.plan_name} · ${fmt(session.amount_clp)} pagado
              </div>
              {session.username && (
                <div style={{ margin: "14px 0", padding: "12px 16px", borderRadius: C.r, background: C.bg, border: `1px solid ${C.border}`, display: "inline-block" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4 }}>Tu usuario</div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: C.text, fontFamily: "monospace" }}>{session.username}</div>
                </div>
              )}
              <div style={{ fontSize: 12, color: C.mute, marginBottom: 16 }}>
                Inicia sesión con la contraseña que creaste.
              </div>
              <a href="/login" style={{
                display: "inline-block", padding: "12px 28px", borderRadius: C.r,
                background: C.accent, color: "#fff", fontSize: 15, fontWeight: 700,
                textDecoration: "none",
              }}>Iniciar sesión →</a>
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
