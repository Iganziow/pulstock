"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { C } from "@/lib/theme";

/**
 * Fijar la contraseña nueva desde el enlace del correo.
 *
 * Verifica el token ANTES de mostrar el formulario. Sin eso, la persona
 * escribe una contraseña, la repite, aprieta el botón y recién ahí se entera
 * de que el enlace venció — habiendo tipeado dos veces para nada.
 */
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const caja: React.CSSProperties = {
  width: "100%", maxWidth: 420, background: C.surface,
  border: `1px solid ${C.border}`, borderRadius: C.rLg,
  padding: "36px 32px", boxShadow: C.shMd,
};

const input: React.CSSProperties = {
  width: "100%", padding: "12px 14px", fontSize: 14,
  borderRadius: C.r, border: `1.5px solid ${C.border}`,
  outline: "none", fontFamily: "inherit", background: C.surface,
};

function Formulario() {
  const params = useSearchParams();
  const router = useRouter();
  const uid = params.get("uid") || "";
  const token = params.get("token") || "";

  const [validando, setValidando] = useState(true);
  const [valido, setValido] = useState(false);
  const [clave, setClave] = useState("");
  const [repetida, setRepetida] = useState("");
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    if (!uid || !token) { setValidando(false); return; }
    fetch(`${API}/auth/password/reset/check/?uid=${encodeURIComponent(uid)}&token=${encodeURIComponent(token)}`)
      .then((r) => r.json())
      .then((d) => setValido(Boolean(d?.valido)))
      .catch(() => setValido(false))
      .finally(() => setValidando(false));
  }, [uid, token]);

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (clave.length < 8) { setError("La contraseña debe tener al menos 8 caracteres."); return; }
    if (clave !== repetida) { setError("Las dos contraseñas no coinciden."); return; }

    setGuardando(true);
    try {
      const r = await fetch(`${API}/auth/password/reset/confirm/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid, token, password: clave }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { setError(d?.detail || "No se pudo cambiar la contraseña."); return; }
      setListo(true);
      setTimeout(() => router.push("/login"), 2200);
    } catch {
      setError("No se pudo conectar. Revisa tu conexión e intenta de nuevo.");
    } finally {
      setGuardando(false);
    }
  }

  if (validando) {
    return (
      <div style={caja}>
        <p style={{ color: C.mid, fontSize: 14, margin: 0 }}>Verificando el enlace...</p>
      </div>
    );
  }

  if (!valido) {
    return (
      <div style={caja}>
        <h1 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 10px" }}>
          Este enlace ya no sirve
        </h1>
        <p style={{ fontSize: 14.5, color: C.mid, lineHeight: 1.65, margin: "0 0 24px" }}>
          Los enlaces vencen a las 2 horas y sirven una sola vez. Pide uno nuevo
          y usa el correo más reciente.
        </p>
        <Link href="/recuperar" style={{
          display: "block", textAlign: "center", padding: "12px",
          background: C.accent, color: "#fff", borderRadius: C.r,
          textDecoration: "none", fontSize: 14, fontWeight: 700,
        }}>
          Pedir un enlace nuevo
        </Link>
      </div>
    );
  }

  if (listo) {
    return (
      <div style={caja}>
        <h1 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 10px" }}>
          Contraseña cambiada
        </h1>
        <p style={{ fontSize: 14.5, color: C.mid, lineHeight: 1.65, margin: 0 }}>
          Listo. Te llevamos a ingresar...
        </p>
      </div>
    );
  }

  return (
    <div style={caja}>
      <h1 style={{ fontSize: 22, fontWeight: 800, margin: "0 0 8px", letterSpacing: "-0.02em" }}>
        Crear contraseña nueva
      </h1>
      <p style={{ fontSize: 14, color: C.mid, lineHeight: 1.6, margin: "0 0 22px" }}>
        Al menos 8 caracteres.
      </p>
      <form onSubmit={guardar} style={{ display: "grid", gap: 16 }}>
        <div>
          <label htmlFor="clave" style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: C.mid, marginBottom: 6 }}>
            Contraseña nueva
          </label>
          <input id="clave" type="password" required autoFocus autoComplete="new-password"
            value={clave} onChange={(e) => setClave(e.target.value)} style={input} />
        </div>
        <div>
          <label htmlFor="repetida" style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: C.mid, marginBottom: 6 }}>
            Repítela
          </label>
          <input id="repetida" type="password" required autoComplete="new-password"
            value={repetida} onChange={(e) => setRepetida(e.target.value)} style={input} />
        </div>
        {error && (
          <p role="alert" style={{
            margin: 0, fontSize: 13.5, color: C.red, background: C.redBg,
            border: `1px solid ${C.redBd}`, borderRadius: C.r, padding: "10px 12px",
          }}>{error}</p>
        )}
        <button type="submit" disabled={guardando}
          style={{
            padding: "12px", fontSize: 14.5, fontWeight: 700,
            background: C.accent, color: "#fff", border: "none",
            borderRadius: C.r, cursor: guardando ? "wait" : "pointer",
          }}>
          {guardando ? "Guardando..." : "Guardar y entrar"}
        </button>
      </form>
    </div>
  );
}

export default function NuevaClavePage() {
  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: C.bg, fontFamily: C.font, padding: 24,
    }}>
      <Suspense fallback={null}>
        <Formulario />
      </Suspense>
    </div>
  );
}
