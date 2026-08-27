import Link from "next/link";
import { C } from "@/lib/theme";
import { BORRADOR, type Bloque, type Documento } from "@/lib/legal/documentos";

/**
 * Renderiza un documento legal público.
 *
 * Server component a propósito: un contrato no necesita JavaScript, y así
 * queda como HTML estático — se lee sin esperar nada, se imprime bien y
 * sobrevive a que falle un script.
 *
 * El índice se genera de `doc.secciones`, la misma fuente que el cuerpo, así
 * que no puede quedar desincronizado.
 */

/** Convierte **negrita**, `código` y [pendientes] en nodos React. */
function formatear(texto: string, clave: string) {
  const partes = texto.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\])/g);
  return partes.map((parte, i) => {
    const k = `${clave}-${i}`;
    if (parte.startsWith("**") && parte.endsWith("**")) {
      return (
        <strong key={k} style={{ fontWeight: 700, color: C.text }}>
          {parte.slice(2, -2)}
        </strong>
      );
    }
    if (parte.startsWith("`") && parte.endsWith("`")) {
      return (
        <code
          key={k}
          style={{
            fontFamily: C.mono,
            fontSize: "0.88em",
            background: C.bg,
            border: `1px solid ${C.border}`,
            borderRadius: 3,
            padding: "1px 5px",
          }}
        >
          {parte.slice(1, -1)}
        </code>
      );
    }
    // [corchetes] = decisión pendiente. Se marca visualmente para que nadie
    // publique el documento creyendo que está completo.
    if (parte.startsWith("[") && parte.endsWith("]")) {
      return (
        <span
          key={k}
          title="Pendiente de definir"
          style={{
            fontFamily: C.mono,
            fontSize: "0.85em",
            background: C.amberBg,
            color: C.amber,
            border: `1px dashed ${C.amberBd}`,
            borderRadius: 3,
            padding: "1px 5px",
            whiteSpace: "nowrap",
          }}
        >
          {parte.slice(1, -1)}
        </span>
      );
    }
    return <span key={k}>{parte}</span>;
  });
}

function BloqueRender({ b, clave }: { b: Bloque; clave: string }) {
  if (b.tipo === "p") {
    return (
      <p style={{ margin: "0 0 14px", fontSize: 15, lineHeight: 1.72, color: C.mid }}>
        {formatear(b.texto, clave)}
      </p>
    );
  }

  if (b.tipo === "sub") {
    return (
      <h3
        style={{
          margin: "22px 0 10px",
          fontSize: 14,
          fontWeight: 700,
          color: C.text,
          letterSpacing: "-0.01em",
        }}
      >
        {b.texto}
      </h3>
    );
  }

  if (b.tipo === "lista") {
    return (
      <ul style={{ margin: "0 0 14px", paddingLeft: 0, listStyle: "none", display: "grid", gap: 9 }}>
        {b.items.map((it, i) => (
          <li
            key={i}
            style={{
              fontSize: 15,
              lineHeight: 1.68,
              color: C.mid,
              paddingLeft: 20,
              position: "relative",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                position: "absolute",
                left: 4,
                top: "0.66em",
                width: 4,
                height: 4,
                borderRadius: "50%",
                background: C.accentBd,
              }}
            />
            {formatear(it, `${clave}-${i}`)}
          </li>
        ))}
      </ul>
    );
  }

  if (b.tipo === "tabla") {
    return (
      <div style={{ overflowX: "auto", margin: "0 0 16px", border: `1px solid ${C.border}`, borderRadius: C.r }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 480, fontSize: 13.5 }}>
          <thead>
            <tr>
              {b.encabezados.map((h, i) => (
                <th
                  key={i}
                  style={{
                    textAlign: "left",
                    padding: "10px 14px",
                    background: C.bg,
                    borderBottom: `1px solid ${C.border}`,
                    fontWeight: 700,
                    color: C.text,
                    fontSize: 12,
                    letterSpacing: "0.03em",
                    textTransform: "uppercase",
                    whiteSpace: "nowrap",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {b.filas.map((fila, r) => (
              <tr key={r}>
                {fila.map((celda, c2) => (
                  <td
                    key={c2}
                    style={{
                      padding: "11px 14px",
                      borderTop: r === 0 ? "none" : `1px solid ${C.border}`,
                      color: c2 === 0 ? C.text : C.mid,
                      fontWeight: c2 === 0 ? 500 : 400,
                      lineHeight: 1.55,
                      verticalAlign: "top",
                    }}
                  >
                    {formatear(celda, `${clave}-${r}-${c2}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // nota
  const alerta = b.tono === "alerta";
  return (
    <div
      style={{
        margin: "0 0 16px",
        padding: "13px 16px",
        background: alerta ? C.redBg : C.accentBg,
        border: `1px solid ${alerta ? C.redBd : C.accentBd}`,
        borderRadius: C.r,
        fontSize: 14.5,
        lineHeight: 1.65,
        color: alerta ? C.red : C.mid,
      }}
    >
      {formatear(b.texto, clave)}
    </div>
  );
}

export function DocumentoLegal({ doc }: { doc: Documento }) {
  const otro = doc.slug === "terminos"
    ? { href: "/legal/privacidad", label: "Política de Privacidad" }
    : { href: "/legal/terminos", label: "Términos de Servicio" };

  return (
    <div style={{ background: C.surface, minHeight: "100vh", fontFamily: C.font, color: C.text }}>
      {/* Barra superior */}
      <header
        style={{
          borderBottom: `1px solid ${C.border}`,
          padding: "18px 24px",
          background: C.surface,
        }}
      >
        <div
          style={{
            maxWidth: 1040,
            margin: "0 auto",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <Link
            href="/"
            style={{ fontSize: 15, fontWeight: 700, color: C.text, textDecoration: "none", letterSpacing: "-0.01em" }}
          >
            Pulstock
          </Link>
          <Link
            href={otro.href}
            style={{ fontSize: 13.5, color: C.accent, textDecoration: "none", fontWeight: 500 }}
          >
            {otro.label} →
          </Link>
        </div>
      </header>

      {BORRADOR && (
        <div
          style={{
            background: C.amberBg,
            borderBottom: `1px solid ${C.amberBd}`,
            padding: "14px 24px",
          }}
        >
          <div style={{ maxWidth: 1040, margin: "0 auto", display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span
              style={{
                fontFamily: C.mono,
                fontSize: 10.5,
                fontWeight: 700,
                letterSpacing: "0.1em",
                color: C.amber,
                border: `1px solid ${C.amberBd}`,
                borderRadius: 3,
                padding: "3px 7px",
                whiteSpace: "nowrap",
                marginTop: 1,
              }}
            >
              BORRADOR
            </span>
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: C.amber }}>
              Este documento <strong>no está vigente</strong> y no obliga a nadie. Falta la revisión
              de un abogado. Lo resaltado en naranja son decisiones todavía pendientes.
            </p>
          </div>
        </div>
      )}

      <main
        style={{
          maxWidth: 1040,
          margin: "0 auto",
          padding: "44px 24px 96px",
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr)",
          gap: 40,
        }}
        className="legal-grid"
      >
        {/* Índice */}
        <nav aria-label="Índice del documento" className="legal-indice">
          <div style={{ position: "sticky", top: 28 }}>
            <div
              style={{
                fontFamily: C.mono,
                fontSize: 10.5,
                fontWeight: 700,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: C.mute,
                marginBottom: 12,
              }}
            >
              Contenido
            </div>
            <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 7 }}>
              {doc.secciones.map((s) => (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    style={{
                      fontSize: 13,
                      lineHeight: 1.45,
                      color: C.mid,
                      textDecoration: "none",
                      display: "block",
                    }}
                  >
                    {s.titulo}
                  </a>
                </li>
              ))}
            </ol>
          </div>
        </nav>

        {/* Documento */}
        <article style={{ minWidth: 0 }}>
          <div style={{ marginBottom: 36 }}>
            <h1
              style={{
                fontSize: 34,
                fontWeight: 700,
                letterSpacing: "-0.03em",
                lineHeight: 1.15,
                margin: "0 0 12px",
              }}
            >
              {doc.titulo}
            </h1>
            <p style={{ fontSize: 16.5, lineHeight: 1.6, color: C.mid, margin: "0 0 20px", maxWidth: "60ch" }}>
              {doc.bajada}
            </p>
            <div
              style={{
                display: "flex",
                gap: 20,
                flexWrap: "wrap",
                fontFamily: C.mono,
                fontSize: 12,
                color: C.mute,
                borderTop: `1px solid ${C.border}`,
                paddingTop: 14,
              }}
            >
              <span>Versión {doc.version}</span>
              <span>Actualizado: {formatear(doc.actualizado, "fecha")}</span>
            </div>
          </div>

          {doc.secciones.map((s) => (
            <section key={s.id} id={s.id} style={{ scrollMarginTop: 24, marginBottom: 34 }}>
              <h2
                style={{
                  fontSize: 19,
                  fontWeight: 700,
                  letterSpacing: "-0.018em",
                  lineHeight: 1.3,
                  margin: "0 0 14px",
                  paddingBottom: 10,
                  borderBottom: `1px solid ${C.border}`,
                }}
              >
                {s.titulo}
              </h2>
              {s.bloques.map((b, i) => (
                <BloqueRender key={i} b={b} clave={`${s.id}-${i}`} />
              ))}
            </section>
          ))}

          <footer
            style={{
              borderTop: `1px solid ${C.border}`,
              paddingTop: 20,
              marginTop: 44,
              display: "flex",
              justifyContent: "space-between",
              gap: 16,
              flexWrap: "wrap",
              fontSize: 13,
              color: C.mute,
            }}
          >
            <span>© 2026 Pulstock</span>
            <Link href={otro.href} style={{ color: C.accent, textDecoration: "none" }}>
              {otro.label}
            </Link>
          </footer>
        </article>
      </main>
    </div>
  );
}
