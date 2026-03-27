"use client";

import { C } from "@/lib/theme";
import { useEffect } from "react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log para debugging en producción (sin exponer al usuario)
    console.error("[DashboardError]", error);
  }, [error]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "60vh",
        padding: 32,
        fontFamily: C.font,
        textAlign: "center",
      }}
    >
      <div
        style={{
          background: C.surface,
          border: `1px solid ${C.redBd}`,
          borderRadius: C.rLg,
          padding: "40px 48px",
          maxWidth: 460,
          boxShadow: C.shMd,
        }}
      >
        {/* Ícono */}
        <div style={{ fontSize: 40, marginBottom: 16 }}>⚠️</div>

        <h2 style={{ color: C.text, margin: "0 0 8px", fontSize: 20, fontWeight: 700 }}>
          Algo salió mal
        </h2>
        <p style={{ color: C.mid, margin: "0 0 24px", fontSize: 14, lineHeight: 1.6 }}>
          Ocurrió un error inesperado en esta sección.
          Tu información está segura.
        </p>

        {/* Código de referencia para soporte */}
        {error.digest && (
          <p style={{
            fontFamily: C.mono,
            fontSize: 11,
            color: C.mute,
            background: C.bg,
            border: `1px solid ${C.border}`,
            borderRadius: C.r,
            padding: "6px 12px",
            marginBottom: 24,
            wordBreak: "break-all",
          }}>
            ref: {error.digest}
          </p>
        )}

        <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
          <button
            onClick={reset}
            style={{
              background: C.accent,
              color: "#fff",
              border: "none",
              borderRadius: C.r,
              padding: "10px 22px",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: C.font,
            }}
          >
            Reintentar
          </button>
          <a
            href="/dashboard"
            style={{
              background: C.bg,
              color: C.mid,
              border: `1px solid ${C.border}`,
              borderRadius: C.r,
              padding: "10px 22px",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: C.font,
              textDecoration: "none",
              display: "inline-block",
            }}
          >
            Ir al inicio
          </a>
        </div>
      </div>
    </div>
  );
}
