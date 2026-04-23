"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { C } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// Cuánto tiempo total esperamos por la confirmación de Flow antes de decirle
// al usuario "esto no llegó, probá de nuevo". 40s era el límite anterior pero
// no se mostraba nada al user al expirar — quedaba pegado en "Verificando…".
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_COUNT = 20;  // 20 × 2s = 40 segundos

function fmt(n: number) { return Math.round(n).toLocaleString("es-CL"); }

type SessionStatus = {
  status: string;  // "pending" | "paid" | "completed" | "expired" | "failed" | "cancelled"
  plan_name: string;
  plan_key: string;
  email_masked: string;
  amount_clp: number;
  username?: string;
};

export default function CheckoutCompletePage() {
  return (
    <Suspense fallback={
      <div style={{
        minHeight: "100vh", display: "flex", alignItems: "center",
        justifyContent: "center", background: C.bg, fontFamily: C.font, color: C.mute,
      }}>Cargando...</div>
    }>
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
  // Cuándo dimos por perdido el polling (mostramos UI de timeout).
  const [timedOut, setTimedOut] = useState(false);
  // Contador visible para feedback (1/20, 2/20…).
  const [pollNum, setPollNum] = useState(0);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const checkStatus = useCallback(async () => {
    if (!token) {
      setError("Token no proporcionado");
      setChecking(false);
      return;
    }
    try {
      const res = await fetch(`${API}/billing/checkout/status/?token=${token}`);
      const data = await res.json();
      if (!mountedRef.current) return;

      if (!res.ok) {
        setError(data?.detail || "Sesión no encontrada");
        setChecking(false);
        return;
      }
      setSession(data);
      setChecking(false);

      // Solo poll mientras esté en estados intermedios. Si ya está terminal
      // (completed / expired / failed / cancelled) no tiene sentido seguir.
      const isTerminal =
        data.status === "completed" || data.status === "expired" ||
        data.status === "failed"    || data.status === "cancelled";

      if (isTerminal) {
        stopPolling();
        return;
      }

      // Estados intermedios: pending (esperando webhook), paid (creando cuenta).
      if (!pollRef.current && (data.status === "pending" || data.status === "paid")) {
        let count = 0;
        pollRef.current = setInterval(async () => {
          count++;
          if (!mountedRef.current) { stopPolling(); return; }
          setPollNum(count);

          // Timeout: ya no esperamos más. Mostrar UI de "no llegó la confirmación".
          if (count > POLL_MAX_COUNT) {
            stopPolling();
            setTimedOut(true);
            return;
          }

          try {
            const r = await fetch(`${API}/billing/checkout/status/?token=${token}`);
            const d = await r.json();
            if (!mountedRef.current) return;
            setSession(d);
            // Cualquier estado terminal corta el polling.
            if (
              d.status === "completed" || d.status === "expired" ||
              d.status === "failed"    || d.status === "cancelled"
            ) {
              stopPolling();
            }
          } catch { /* retry en próxima iteración */ }
        }, POLL_INTERVAL_MS);
      }
    } catch {
      if (!mountedRef.current) return;
      setError("Error de conexión. Verificá tu internet y refrescá la página.");
      setChecking(false);
    }
  }, [token, stopPolling]);

  // Carga inicial.
  useEffect(() => {
    mountedRef.current = true;
    checkStatus();
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Reintentar verificación manual (botón en UI de timeout).
  const handleRetry = useCallback(() => {
    setTimedOut(false);
    setPollNum(0);
    setChecking(true);
    setError("");
    checkStatus();
  }, [checkStatus]);

  return (
    <div style={{
      minHeight: "100vh", background: C.bg, fontFamily: C.font,
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", padding: "40px 20px",
    }}>
      <div style={{ maxWidth: 480, width: "100%" }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <a href="/" style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 8 }}>
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
              <rect width="32" height="32" rx="8" fill={C.accent}/>
              <path d="M9 22V10h6a4 4 0 010 8H9" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span style={{ fontSize: 20, fontWeight: 800, color: C.text }}>Pulstock</span>
          </a>
        </div>

        <div style={{
          background: C.surface, borderRadius: C.rMd, border: `1px solid ${C.border}`,
          padding: "28px 24px", boxShadow: C.shMd,
        }}>

          {/* CHECKING — primer fetch, antes de saber el status */}
          {checking && (
            <div style={{ textAlign: "center", padding: 30 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: C.mid }}>Verificando pago...</div>
            </div>
          )}

          {/* PENDING — polling activo, no expirado todavía */}
          {!checking && !timedOut && session?.status === "pending" && (
            <div style={{ textAlign: "center", padding: 30 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>{"⏳"}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>
                Verificando tu pago
              </div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 4 }}>
                Esto puede tomar unos segundos…
              </div>
              {pollNum > 2 && (
                <div style={{ fontSize: 11, color: C.mute, marginTop: 8 }}>
                  Esperando confirmación de Flow ({pollNum}/{POLL_MAX_COUNT})
                </div>
              )}
              {/* Salida temprana: si el user sabe que canceló o cerró Flow,
                  puede volver a planes sin esperar el timeout. */}
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
                <div style={{ fontSize: 11, color: C.mute, marginBottom: 8 }}>
                  ¿Cancelaste el pago o cerraste la ventana?
                </div>
                <a href="/#precios" style={{
                  display: "inline-block", padding: "8px 16px", borderRadius: C.r,
                  background: "transparent", color: C.mid, fontSize: 12, fontWeight: 600,
                  textDecoration: "none", border: `1px solid ${C.border}`,
                }}>← Volver a planes</a>
              </div>
            </div>
          )}

          {/* PAID — pago confirmado, creando cuenta automáticamente */}
          {!checking && !timedOut && session?.status === "paid" && (
            <div style={{ textAlign: "center", padding: 30 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>✓</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.green, marginBottom: 6 }}>
                Pago confirmado — ${fmt(session.amount_clp)}
              </div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 16 }}>
                Creando tu cuenta… {session.plan_name}
              </div>
              <div style={{
                display: "inline-block", width: 24, height: 24,
                border: `3px solid ${C.border}`, borderTopColor: C.accent,
                borderRadius: "50%", animation: "spin 0.8s linear infinite",
              }} />
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </div>
          )}

          {/* COMPLETED — todo listo */}
          {!checking && session?.status === "completed" && (
            <div style={{ textAlign: "center", padding: 20 }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>🎉</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: C.text, marginBottom: 6 }}>
                ¡Tu cuenta está lista!
              </div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 6 }}>
                Plan {session.plan_name} · ${fmt(session.amount_clp)} pagado
              </div>
              {session.username && (
                <div style={{
                  margin: "14px 0", padding: "12px 16px", borderRadius: C.r,
                  background: C.bg, border: `1px solid ${C.border}`, display: "inline-block",
                }}>
                  <div style={{
                    fontSize: 11, fontWeight: 700, color: C.mute,
                    textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4,
                  }}>Tu usuario</div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: C.text, fontFamily: "monospace" }}>
                    {session.username}
                  </div>
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

          {/* TIMED OUT — esperamos 40s y no llegó nada del webhook */}
          {!checking && timedOut && (
            <div style={{ textAlign: "center", padding: 20 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>{"⏱️"}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>
                No recibimos confirmación del pago
              </div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 6, lineHeight: 1.55 }}>
                Si completaste el pago en Flow, puede tardar unos minutos en confirmarse.
                Si lo cancelaste o cerraste la ventana, podés volver a intentarlo.
              </div>
              <div style={{
                margin: "14px 0", padding: "10px 14px", borderRadius: C.r,
                background: C.amberBg, border: `1px solid ${C.amberBd}`,
                fontSize: 11, color: "#92400E", textAlign: "left",
              }}>
                <strong>Importante:</strong> si efectivamente pagaste, NO vuelvas a pagar.
                Esperá unos minutos y apretá &ldquo;Verificar de nuevo&rdquo;.
                Si el problema persiste, contactanos a soporte@pulstock.cl con tu RUT.
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap", marginTop: 16 }}>
                <button onClick={handleRetry} style={{
                  padding: "10px 18px", borderRadius: C.r, border: "none",
                  background: C.accent, color: "#fff", fontSize: 13, fontWeight: 700,
                  cursor: "pointer", fontFamily: C.font,
                }}>Verificar de nuevo</button>
                <a href="/#precios" style={{
                  display: "inline-block", padding: "10px 18px", borderRadius: C.r,
                  background: "transparent", color: C.mid, fontSize: 13, fontWeight: 600,
                  textDecoration: "none", border: `1px solid ${C.border}`,
                }}>← Volver a planes</a>
              </div>
            </div>
          )}

          {/* FAILED / CANCELLED — explícitamente fallido o cancelado por Flow */}
          {!checking && !timedOut && (session?.status === "failed" || session?.status === "cancelled") && (
            <div style={{ textAlign: "center", padding: 20 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>{"⚠️"}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>
                {session.status === "cancelled" ? "Pago cancelado" : "El pago no se pudo procesar"}
              </div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 16, lineHeight: 1.55 }}>
                {session.status === "cancelled"
                  ? "Cancelaste el pago en Flow. Podés volver a intentarlo cuando quieras — no se cobró nada."
                  : "Hubo un problema con tu medio de pago. Probá con otro método o contactanos."}
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
                <a href="/#precios" style={{
                  display: "inline-block", padding: "10px 18px", borderRadius: C.r,
                  background: C.accent, color: "#fff", fontSize: 13, fontWeight: 700,
                  textDecoration: "none",
                }}>Intentar de nuevo</a>
                <a href="mailto:soporte@pulstock.cl" style={{
                  display: "inline-block", padding: "10px 18px", borderRadius: C.r,
                  background: "transparent", color: C.mid, fontSize: 13, fontWeight: 600,
                  textDecoration: "none", border: `1px solid ${C.border}`,
                }}>Contactar soporte</a>
              </div>
            </div>
          )}

          {/* EXPIRED — sesión vencida del lado del backend (ej. >24h) */}
          {!checking && session?.status === "expired" && (
            <div style={{ textAlign: "center", padding: 20 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>{"⚠️"}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>
                Sesión expirada
              </div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 16 }}>
                Esta sesión de pago expiró. Empezá una nueva desde la página de planes.
              </div>
              <a href="/#precios" style={{
                display: "inline-block", padding: "10px 24px", borderRadius: C.r,
                background: C.accent, color: "#fff", fontSize: 14, fontWeight: 700,
                textDecoration: "none",
              }}>Volver a planes</a>
            </div>
          )}

          {/* ERROR — fallo de conexión / token inválido */}
          {!checking && !session && error && (
            <div style={{ textAlign: "center", padding: 20 }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>{"⚠️"}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>
                No pudimos cargar la sesión
              </div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 16 }}>
                {error}
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
                <button onClick={handleRetry} style={{
                  padding: "10px 18px", borderRadius: C.r, border: "none",
                  background: C.accent, color: "#fff", fontSize: 13, fontWeight: 700,
                  cursor: "pointer", fontFamily: C.font,
                }}>Reintentar</button>
                <a href="/#precios" style={{
                  display: "inline-block", padding: "10px 18px", borderRadius: C.r,
                  background: "transparent", color: C.mid, fontSize: 13, fontWeight: 600,
                  textDecoration: "none", border: `1px solid ${C.border}`,
                }}>← Volver a planes</a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
