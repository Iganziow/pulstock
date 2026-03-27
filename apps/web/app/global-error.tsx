"use client";

/**
 * Global Error Boundary — último recurso si el layout mismo crashea.
 * Next.js requiere que este archivo defina <html> y <body>.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="es">
      <body
        style={{
          margin: 0,
          fontFamily: "'DM Sans','Helvetica Neue',system-ui,sans-serif",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
          background: "#F7F7F8",
        }}
      >
        <div
          style={{
            background: "#fff",
            border: "1px solid #FECACA",
            borderRadius: 12,
            padding: "32px 40px",
            maxWidth: 440,
            textAlign: "center",
          }}
        >
          <h2 style={{ color: "#DC2626", margin: "0 0 8px", fontSize: 20 }}>
            Error inesperado
          </h2>
          <p style={{ color: "#52525B", margin: "0 0 20px", fontSize: 14 }}>
            La aplicación encontró un problema. Tu información está segura.
          </p>
          <button
            onClick={reset}
            style={{
              background: "#4F46E5",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "10px 24px",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Reintentar
          </button>
        </div>
      </body>
    </html>
  );
}
