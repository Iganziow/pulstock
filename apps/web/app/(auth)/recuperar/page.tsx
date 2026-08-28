"use client";

import { useState } from "react";
import Link from "next/link";
import { C } from "@/lib/theme";

/**
 * Pedir el enlace de recuperación.
 *
 * La respuesta del servidor es siempre la misma, exista o no el correo: no
 * revelamos quién tiene cuenta. Por eso la pantalla muestra el mismo mensaje
 * en los dos casos — y tiene que ser un mensaje que no frustre a quien SÍ
 * escribió bien su correo.
 */
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export default function RecuperarPage() {
  const [email, setEmail] = useState("");
  const [estado, setEstado] = useState<"idle" | "enviando" | "listo">("idle");

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setEstado("enviando");
    try {
      await fetch(`${API}/auth/password/reset/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
    } catch {
      // Aun si la red falla mostramos lo mismo: la pantalla no debe
      // convertirse en un detector de correos válidos.
    }
    setEstado("listo");
  }

  const caja: React.CSSProperties = {
    width: "100%", maxWidth: 420, background: C.surface,
    border: `1px solid ${C.border}`, borderRadius: C.rLg,
    padding: "36px 32px", boxShadow: C.shMd,
  };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: C.bg, fontFamily: C.font, padding: 24,
    }}>
      <div style={caja}>
        <h1 style={{ fontSize: 22, fontWeight: 800, margin: "0 0 8px", letterSpacing: "-0.02em" }}>
          Recuperar contraseña
        </h1>

        {estado === "listo" ? (
          <>
            <p style={{ fontSize: 14.5, color: C.mid, lineHeight: 1.65, margin: "0 0 16px" }}>
              Si ese correo tiene una cuenta, le enviamos un enlace para crear una
              contraseña nueva. <strong style={{ color: C.text }}>Revisa también la
              carpeta de spam.</strong>
            </p>
            <p style={{ fontSize: 13, color: C.mute, lineHeight: 1.6, margin: "0 0 24px" }}>
              El enlace vence en 2 horas y sirve una sola vez.
            </p>
            <Link href="/login" style={{
              display: "block", textAlign: "center", padding: "12px",
              borderRadius: C.r, border: `1px solid ${C.border}`,
              color: C.text, textDecoration: "none", fontSize: 14, fontWeight: 600,
            }}>
              Volver a ingresar
            </Link>
          </>
        ) : (
          <>
            <p style={{ fontSize: 14.5, color: C.mid, lineHeight: 1.65, margin: "0 0 22px" }}>
              Escribe el correo de tu cuenta y te mandamos un enlace para crear
              una contraseña nueva.
            </p>
            <form onSubmit={enviar} style={{ display: "grid", gap: 16 }}>
              <div>
                <label htmlFor="email" style={{
                  display: "block", fontSize: 12.5, fontWeight: 600,
                  color: C.mid, marginBottom: 6,
                }}>
                  Correo
                </label>
                <input
                  id="email" name="email" type="email" required autoFocus
                  autoComplete="email" value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="tu@correo.cl"
                  style={{
                    width: "100%", padding: "12px 14px", fontSize: 14,
                    borderRadius: C.r, border: `1.5px solid ${C.border}`,
                    outline: "none", fontFamily: "inherit", background: C.surface,
                  }}
                />
              </div>
              <button
                type="submit"
                disabled={estado === "enviando" || !email.trim()}
                style={{
                  padding: "12px", fontSize: 14.5, fontWeight: 700,
                  background: C.accent, color: "#fff", border: "none",
                  borderRadius: C.r, cursor: estado === "enviando" ? "wait" : "pointer",
                  opacity: !email.trim() ? 0.5 : 1,
                }}
              >
                {estado === "enviando" ? "Enviando..." : "Enviarme el enlace"}
              </button>
            </form>
            <Link href="/login" style={{
              display: "block", textAlign: "center", marginTop: 20,
              fontSize: 13, color: C.mid, textDecoration: "none",
            }}>
              Volver a ingresar
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
