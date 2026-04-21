"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

/**
 * Página pública de descarga del Pulstock Printer Agent.
 * URL: https://pulstock.cl/agent
 *
 * Para Windows: un solo .exe, doble click, escribí el código.
 * Para Mac/Linux: ZIP con instalador shell (mantenido como fallback).
 */
type OS = "windows" | "mac" | "linux";

function detectOS(): OS {
  if (typeof window === "undefined") return "windows";
  const ua = window.navigator.userAgent.toLowerCase();
  if (ua.includes("mac")) return "mac";
  if (ua.includes("linux")) return "linux";
  return "windows";
}

export default function AgentPage() {
  const [os, setOs] = useState<OS>("windows");
  const [detectedOS, setDetectedOS] = useState<OS>("windows");

  useEffect(() => {
    const d = detectOS();
    setDetectedOS(d);
    setOs(d);
  }, []);

  const isWindows = os === "windows";
  const downloadUrl = isWindows
    ? "/agent/PulstockAgent.exe"
    : os === "mac"
    ? "/agent/PulstockAgent-MacLinux.zip"
    : "/agent/PulstockAgent-MacLinux.zip";

  const fileName = isWindows
    ? "PulstockAgent.exe"
    : "PulstockAgent-MacLinux.zip";

  const osLabel = isWindows ? "Windows" : os === "mac" ? "Mac" : "Linux";
  const osIcon = isWindows ? "🪟" : os === "mac" ? "🍎" : "🐧";

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #FAFBFF 0%, #F4F6FB 100%)",
        fontFamily: "'DM Sans', system-ui, sans-serif",
        color: "#1F2937",
      }}
    >
      {/* Header */}
      <header
        style={{
          padding: "16px 24px",
          background: "#fff",
          borderBottom: "1px solid #E5E7EB",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Link href="/" style={{ textDecoration: "none" }}>
          <span
            style={{
              fontSize: 22,
              fontWeight: 800,
              letterSpacing: "-0.04em",
              color: "#4F46E5",
            }}
          >
            Pulstock
          </span>
        </Link>
        <a
          href="mailto:soporte@pulstock.cl"
          style={{
            fontSize: 13,
            color: "#6B7280",
            textDecoration: "none",
          }}
        >
          soporte@pulstock.cl
        </a>
      </header>

      <div style={{ maxWidth: 640, margin: "0 auto", padding: "48px 20px" }}>
        {/* Hero */}
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <div style={{ fontSize: 64, marginBottom: 16 }}>🖨️</div>
          <h1
            style={{
              fontSize: 34,
              fontWeight: 800,
              letterSpacing: "-0.04em",
              margin: "0 0 12px",
              lineHeight: 1.15,
            }}
          >
            Conecta tu impresora a Pulstock
          </h1>
          <p
            style={{
              fontSize: 17,
              color: "#6B7280",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            {isWindows
              ? "Descargá, doble click, pegá tu código. Listo."
              : "Descargá el instalador, ejecutalo, escribí el código."}
          </p>
        </div>

        {/* OS chips */}
        <div
          style={{
            display: "flex",
            gap: 8,
            justifyContent: "center",
            marginBottom: 28,
          }}
        >
          {([
            { key: "windows" as const, label: "Windows", icon: "🪟" },
            { key: "mac" as const, label: "Mac", icon: "🍎" },
            { key: "linux" as const, label: "Linux", icon: "🐧" },
          ]).map((o) => (
            <button
              key={o.key}
              onClick={() => setOs(o.key)}
              style={{
                padding: "8px 16px",
                borderRadius: 99,
                border: `1.5px solid ${os === o.key ? "#4F46E5" : "#E5E7EB"}`,
                background: os === o.key ? "#EEF2FF" : "#fff",
                color: os === o.key ? "#4F46E5" : "#6B7280",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                gap: 6,
                transition: "all 0.15s",
              }}
            >
              <span>{o.icon}</span>
              <span>{o.label}</span>
              {detectedOS === o.key && (
                <span
                  style={{
                    fontSize: 10,
                    background: os === o.key ? "#4F46E5" : "#9CA3AF",
                    color: "#fff",
                    padding: "1px 6px",
                    borderRadius: 99,
                    fontWeight: 700,
                  }}
                >
                  tu PC
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Download CARD (único CTA — lo más importante de la página) */}
        <div
          style={{
            background: "#fff",
            borderRadius: 20,
            padding: 32,
            boxShadow: "0 4px 20px rgba(79, 70, 229, 0.08)",
            border: "2px solid #C7D2FE",
            textAlign: "center",
            marginBottom: 28,
          }}
        >
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "4px 12px",
              background: "#EEF2FF",
              borderRadius: 99,
              fontSize: 12,
              fontWeight: 700,
              color: "#4F46E5",
              marginBottom: 12,
              letterSpacing: "0.02em",
            }}
          >
            {isWindows ? "✨ RECOMENDADO" : "📦 DESCARGA"}
          </div>
          <div
            style={{
              fontSize: 18,
              fontWeight: 700,
              marginBottom: 4,
            }}
          >
            {fileName}
          </div>
          <div
            style={{
              fontSize: 13,
              color: "#6B7280",
              marginBottom: 20,
            }}
          >
            {isWindows
              ? "6.5 MB · No requiere instalar nada más"
              : "~8 KB · Incluye instalador automático"}
          </div>
          <a
            href={downloadUrl}
            download
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 10,
              padding: "16px 36px",
              background: "#4F46E5",
              color: "#fff",
              borderRadius: 12,
              textDecoration: "none",
              fontSize: 17,
              fontWeight: 700,
              boxShadow: "0 6px 20px rgba(79, 70, 229, 0.3)",
              transition: "transform 0.15s, box-shadow 0.15s",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
              (e.currentTarget as HTMLElement).style.boxShadow = "0 8px 28px rgba(79, 70, 229, 0.4)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
              (e.currentTarget as HTMLElement).style.boxShadow = "0 6px 20px rgba(79, 70, 229, 0.3)";
            }}
          >
            <span style={{ fontSize: 20 }}>⬇️</span>
            Descargar para {osLabel} {osIcon}
          </a>
        </div>

        {/* Instrucciones (muy breves) */}
        <div
          style={{
            background: "#fff",
            borderRadius: 16,
            padding: 24,
            border: "1px solid #E5E7EB",
            marginBottom: 24,
          }}
        >
          <h2
            style={{
              fontSize: 18,
              fontWeight: 700,
              margin: "0 0 20px",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            🎯 Qué hacer después de descargar
          </h2>

          {isWindows ? (
            <ol style={listStyle}>
              <li>
                <strong>Doble click</strong> en el archivo{" "}
                <code style={codeStyle}>PulstockAgent.exe</code> descargado
              </li>
              <li>
                Windows puede mostrar <strong>&quot;Windows protegió tu PC&quot;</strong> →
                apretá <strong>&quot;Más información&quot;</strong> y después{" "}
                <strong>&quot;Ejecutar de todas formas&quot;</strong>
                <div style={warningBox}>
                  💡 Es normal — pasa con programas nuevos. Podés verificar
                  con Windows Defender, no tiene virus.
                </div>
              </li>
              <li>
                Aparece una ventana negra que te pide el <strong>código de emparejado</strong>.
                Pegalo (<code style={codeStyle}>ABCD-1234</code>) y presioná Enter.
              </li>
              <li>
                ¡Listo! El agente empieza a funcionar.
              </li>
            </ol>
          ) : os === "mac" ? (
            <ol style={listStyle}>
              <li>
                Descomprimí el ZIP (doble click)
              </li>
              <li>
                Dentro de la carpeta, <strong>click derecho</strong> en{" "}
                <code style={codeStyle}>instalar-pulstock.sh</code> → <strong>Abrir con Terminal</strong>
                <div style={warningBox}>
                  💡 Si Mac se queja de &quot;desarrollador no identificado&quot;,
                  hacé click derecho → <strong>Abrir</strong> y luego <strong>&quot;Abrir&quot;</strong> de nuevo.
                </div>
              </li>
              <li>
                El instalador te va a pedir tu código de emparejado — pegalo y listo.
              </li>
            </ol>
          ) : (
            <ol style={listStyle}>
              <li>Descomprimí el ZIP</li>
              <li>
                Abrí una terminal en la carpeta y ejecutá:{" "}
                <code style={codeStyle}>bash instalar-pulstock.sh</code>
              </li>
              <li>Pegá el código de emparejado cuando te lo pida.</li>
            </ol>
          )}
        </div>

        {/* Dónde conseguir el código */}
        <div
          style={{
            padding: 20,
            background: "#FEF3C7",
            border: "1px solid #FDE68A",
            borderRadius: 16,
            marginBottom: 24,
            display: "flex",
            gap: 14,
            alignItems: "flex-start",
          }}
        >
          <div style={{ fontSize: 28, flexShrink: 0 }}>🔑</div>
          <div>
            <div
              style={{
                fontWeight: 700,
                marginBottom: 6,
                fontSize: 15,
                color: "#92400E",
              }}
            >
              ¿Dónde saco el código de emparejado?
            </div>
            <div style={{ fontSize: 14, color: "#78350F", lineHeight: 1.6 }}>
              En Pulstock →{" "}
              <Link
                href="/dashboard/settings?tab=impresoras"
                style={{ color: "#92400E", fontWeight: 600, textDecoration: "underline" }}
              >
                Configuración → Impresoras
              </Link>
              {" "}→ botón <strong>&quot;+ Agregar agente PC&quot;</strong>. Te muestra
              un código tipo <code style={codeStyle}>ABCD-1234</code>.
            </div>
          </div>
        </div>

        {/* Success promise */}
        <div
          style={{
            padding: 20,
            background: "#ECFDF5",
            border: "1px solid #A7F3D0",
            borderRadius: 16,
            display: "flex",
            alignItems: "center",
            gap: 14,
            marginBottom: 32,
          }}
        >
          <div style={{ fontSize: 32, flexShrink: 0 }}>✅</div>
          <div>
            <div style={{ fontWeight: 700, marginBottom: 4, color: "#065F46" }}>
              Después de eso, olvidate.
            </div>
            <div style={{ fontSize: 14, color: "#047857", lineHeight: 1.5 }}>
              El agente queda corriendo en segundo plano y arranca solo
              cada vez que prendes el PC.
            </div>
          </div>
        </div>

        {/* FAQ */}
        <details>
          <summary
            style={{
              cursor: "pointer",
              fontSize: 14,
              fontWeight: 600,
              color: "#6B7280",
              padding: "10px 0",
              listStyle: "none",
              textAlign: "center",
            }}
          >
            ▸ Preguntas comunes
          </summary>
          <div
            style={{
              marginTop: 12,
              padding: 20,
              background: "#fff",
              borderRadius: 12,
              border: "1px solid #E5E7EB",
            }}
          >
            <FAQ q="¿Es seguro?">
              Sí. El agente solo habla con Pulstock (HTTPS) hacia afuera.
              No abre puertos en tu PC ni acepta conexiones entrantes.
            </FAQ>
            <FAQ q="¿Funciona con cualquier impresora?">
              Sí — impresoras del sistema (instaladas en Windows/Mac/Linux),
              USB ESC/POS directas, e impresoras de red (IP).
            </FAQ>
            <FAQ q="¿Los celulares tienen que estar en la misma red?">
              <strong>No</strong>. Pueden estar con datos móviles o en otra
              red WiFi. El agente escucha trabajos por internet.
            </FAQ>
            <FAQ q="¿Qué pasa si el PC se apaga?">
              Los trabajos quedan en cola. Cuando prendas el PC, el agente
              los toma y los imprime automáticamente.
            </FAQ>
            <FAQ q="Windows Defender lo marca como sospechoso">
              Es un falso positivo común con programas nuevos sin firma.
              El código del agente es público y auditable.
              Apretá &quot;Más información&quot; → &quot;Ejecutar de todas formas&quot;.
            </FAQ>
            <FAQ q="¿Cómo lo desinstalo?">
              Simplemente borra el archivo{" "}
              <code style={codeStyle}>PulstockAgent.exe</code>. Si configuraste
              auto-inicio, también borra{" "}
              <code style={codeStyle}>
                C:\Users\tu-usuario\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\PulstockAgent.bat
              </code>
            </FAQ>
            <FAQ q="¿Quiero instalarlo desde el código fuente">
              Usuarios avanzados pueden descargar el script Python (
              <a href="/agent/pulstock_agent.py" style={{ color: "#4F46E5" }}>
                pulstock_agent.py
              </a>
              ) y ejecutarlo directamente con Python 3.8+.
            </FAQ>
            <FAQ q="Me sale un error">
              Escribime a{" "}
              <a href="mailto:soporte@pulstock.cl" style={{ color: "#4F46E5" }}>
                soporte@pulstock.cl
              </a>{" "}
              con un screenshot. Te respondo en horas.
            </FAQ>
          </div>
        </details>

        {/* Footer */}
        <div
          style={{
            marginTop: 48,
            textAlign: "center",
            fontSize: 12,
            color: "#9CA3AF",
          }}
        >
          Pulstock · Versión 1.0 ·{" "}
          <Link href="/" style={{ color: "#9CA3AF" }}>
            Inicio
          </Link>
        </div>
      </div>
    </div>
  );
}

/* ── Styles ──────────────────────────────────────────────────────── */

const codeStyle: React.CSSProperties = {
  background: "#F3F4F6",
  padding: "2px 6px",
  borderRadius: 4,
  fontSize: "0.9em",
  fontFamily: "'JetBrains Mono', monospace",
  color: "#4F46E5",
};

const listStyle: React.CSSProperties = {
  paddingLeft: 24,
  fontSize: 15,
  lineHeight: 1.9,
  color: "#374151",
  margin: 0,
};

const warningBox: React.CSSProperties = {
  marginTop: 10,
  padding: "10px 14px",
  background: "#FEF3C7",
  border: "1px solid #FDE68A",
  borderRadius: 8,
  fontSize: 13,
  color: "#92400E",
  lineHeight: 1.5,
};

function FAQ({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <details style={{ marginBottom: 10 }}>
      <summary
        style={{
          cursor: "pointer",
          fontWeight: 600,
          fontSize: 14,
          padding: "8px 0",
          listStyle: "none",
          color: "#1F2937",
        }}
      >
        ▸ {q}
      </summary>
      <div
        style={{
          padding: "4px 0 8px 14px",
          fontSize: 13.5,
          color: "#4B5563",
          lineHeight: 1.6,
        }}
      >
        {children}
      </div>
    </details>
  );
}
