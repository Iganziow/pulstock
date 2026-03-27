import { C } from "@/lib/theme";

export default function NotFound() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        background: C.bg,
        fontFamily: C.font,
        textAlign: "center",
        padding: 32,
      }}
    >
      <div
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: C.rLg,
          padding: "48px 56px",
          maxWidth: 420,
          boxShadow: C.shMd,
        }}
      >
        <p style={{ fontSize: 64, fontWeight: 900, color: C.accent, margin: "0 0 8px", lineHeight: 1 }}>
          404
        </p>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: C.text, margin: "0 0 12px" }}>
          Página no encontrada
        </h1>
        <p style={{ fontSize: 14, color: C.mid, margin: "0 0 32px", lineHeight: 1.6 }}>
          La ruta que buscas no existe o fue movida.
        </p>
        <a
          href="/dashboard"
          style={{
            display: "inline-block",
            background: C.accent,
            color: "#fff",
            borderRadius: C.r,
            padding: "10px 28px",
            fontSize: 14,
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          Volver al dashboard
        </a>
      </div>
    </div>
  );
}
