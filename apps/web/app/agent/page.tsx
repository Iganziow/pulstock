"use client";

import { useState } from "react";
import Link from "next/link";

/**
 * Página pública de descarga del Pulstock Printer Agent.
 * URL: https://pulstock.cl/agent
 */
export default function AgentDownloadPage() {
  const [os, setOs] = useState<"windows" | "mac" | "linux">("windows");

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #FAFBFF 0%, #F4F6FB 100%)",
        fontFamily: "'DM Sans', system-ui, sans-serif",
        color: "#1F2937",
      }}
    >
      {/* Header simple */}
      <header
        style={{
          padding: "18px 32px",
          borderBottom: "1px solid #E5E7EB",
          background: "#fff",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Link href="/" style={{ textDecoration: "none", color: "#1F2937" }}>
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
        <Link
          href="/dashboard"
          style={{
            fontSize: 13,
            color: "#4F46E5",
            textDecoration: "none",
            fontWeight: 600,
          }}
        >
          Volver al dashboard →
        </Link>
      </header>

      <div
        style={{
          maxWidth: 820,
          margin: "0 auto",
          padding: "48px 24px",
        }}
      >
        {/* Hero */}
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🖨️</div>
          <h1
            style={{
              fontSize: 34,
              fontWeight: 800,
              letterSpacing: "-0.04em",
              margin: "0 0 12px",
            }}
          >
            Pulstock Printer Agent
          </h1>
          <p
            style={{
              fontSize: 16,
              color: "#6B7280",
              lineHeight: 1.6,
              maxWidth: 560,
              margin: "0 auto",
            }}
          >
            Instala este pequeño programa en el PC del local para que
            cualquier celular o tablet pueda imprimir boletas directamente
            en las impresoras del local — sin emparejar cada dispositivo.
          </p>
        </div>

        {/* OS selector */}
        <div
          style={{
            display: "flex",
            gap: 8,
            justifyContent: "center",
            marginBottom: 24,
          }}
        >
          {([
            { key: "windows", label: "Windows", icon: "🪟" },
            { key: "mac", label: "macOS", icon: "🍎" },
            { key: "linux", label: "Linux", icon: "🐧" },
          ] as const).map((o) => (
            <button
              key={o.key}
              onClick={() => setOs(o.key)}
              style={{
                padding: "10px 18px",
                border: `1.5px solid ${
                  os === o.key ? "#4F46E5" : "#E5E7EB"
                }`,
                background: os === o.key ? "#EEF2FF" : "#fff",
                color: os === o.key ? "#4F46E5" : "#6B7280",
                borderRadius: 10,
                cursor: "pointer",
                fontSize: 14,
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                gap: 6,
                transition: "all 0.15s",
              }}
            >
              <span>{o.icon}</span> {o.label}
            </button>
          ))}
        </div>

        {/* Installation card */}
        <div
          style={{
            background: "#fff",
            border: "1px solid #E5E7EB",
            borderRadius: 16,
            padding: 32,
            boxShadow: "0 2px 12px rgba(0,0,0,0.04)",
            marginBottom: 24,
          }}
        >
          <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 20px" }}>
            Instalación en {os === "windows" ? "Windows" : os === "mac" ? "macOS" : "Linux"}
          </h2>

          <ol
            style={{
              paddingLeft: 0,
              listStyle: "none",
              margin: 0,
              counterReset: "step",
            }}
          >
            {/* Paso 1: Python */}
            <Step num={1} title="Instala Python 3.8 o superior">
              {os === "windows" && (
                <>
                  <p style={{ margin: "0 0 8px" }}>
                    Descarga el instalador desde{" "}
                    <a
                      href="https://www.python.org/downloads/"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#4F46E5" }}
                    >
                      python.org/downloads
                    </a>
                    .
                  </p>
                  <p style={{ margin: 0, color: "#92400E", fontSize: 13 }}>
                    ⚠ <strong>Importante:</strong> en el instalador, marca la
                    opción <em>&quot;Add Python to PATH&quot;</em> antes de hacer Install.
                  </p>
                </>
              )}
              {os === "mac" && (
                <p style={{ margin: 0 }}>
                  Ya viene instalado. Si necesitás actualizar:{" "}
                  <Code>brew install python3</Code>
                </p>
              )}
              {os === "linux" && (
                <p style={{ margin: 0 }}>
                  Ya viene instalado en la mayoría de distros. Si no:{" "}
                  <Code>sudo apt install python3 python3-pip</Code>
                </p>
              )}
            </Step>

            {/* Paso 2: Descargar */}
            <Step num={2} title="Descarga el agente">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 10 }}>
                <a
                  href="/agent/pulstock_agent.py"
                  download="pulstock_agent.py"
                  style={{
                    padding: "10px 16px",
                    background: "#4F46E5",
                    color: "#fff",
                    borderRadius: 8,
                    textDecoration: "none",
                    fontSize: 14,
                    fontWeight: 600,
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  📄 pulstock_agent.py
                </a>
                <a
                  href="/agent/requirements.txt"
                  download="requirements.txt"
                  style={{
                    padding: "10px 16px",
                    background: "#fff",
                    color: "#4F46E5",
                    border: "1.5px solid #C7D2FE",
                    borderRadius: 8,
                    textDecoration: "none",
                    fontSize: 14,
                    fontWeight: 600,
                  }}
                >
                  📄 requirements.txt
                </a>
              </div>
              <p style={{ margin: 0, fontSize: 13, color: "#6B7280" }}>
                Guarda ambos archivos en una carpeta, por ejemplo{" "}
                <Code>
                  {os === "windows"
                    ? "C:\\Pulstock\\"
                    : "~/pulstock/"}
                </Code>
              </p>
            </Step>

            {/* Paso 3: Instalar dependencias */}
            <Step num={3} title="Instala las dependencias">
              {os === "windows" ? (
                <>
                  <p style={{ margin: "0 0 8px" }}>
                    Abre <strong>PowerShell</strong> (menú Inicio → escribe
                    &quot;PowerShell&quot;) y ejecuta:
                  </p>
                  <CodeBlock>
{`cd C:\\Pulstock
pip install -r requirements.txt`}
                  </CodeBlock>
                </>
              ) : (
                <>
                  <p style={{ margin: "0 0 8px" }}>
                    Abre una terminal en la carpeta donde guardaste el agente:
                  </p>
                  <CodeBlock>
{`cd ~/pulstock
pip3 install -r requirements.txt`}
                  </CodeBlock>
                </>
              )}
            </Step>

            {/* Paso 4: Emparejar */}
            <Step num={4} title="Empareja con tu cuenta Pulstock">
              <p style={{ margin: "0 0 8px" }}>
                Ejecuta el agente en modo emparejado:
              </p>
              <CodeBlock>
                {os === "windows" ? "python pulstock_agent.py --pair" : "python3 pulstock_agent.py --pair"}
              </CodeBlock>
              <p
                style={{
                  margin: "10px 0 0",
                  fontSize: 13,
                  color: "#6B7280",
                }}
              >
                Te va a pedir el código de 8 caracteres que te da Pulstock en{" "}
                <Link href="/dashboard/settings?tab=impresoras" style={{ color: "#4F46E5" }}>
                  Configuración → Impresoras → Agregar agente PC
                </Link>
                .
              </p>
            </Step>

            {/* Paso 5: Dejarlo corriendo */}
            <Step num={5} title="Déjalo corriendo">
              <p style={{ margin: "0 0 8px" }}>
                Ejecuta el agente para que escuche trabajos de impresión:
              </p>
              <CodeBlock>
                {os === "windows" ? "python pulstock_agent.py" : "python3 pulstock_agent.py"}
              </CodeBlock>
              <p style={{ margin: "10px 0 0", fontSize: 13, color: "#6B7280" }}>
                Deja esa ventana abierta. Para que arranque automáticamente al
                prender el PC, revisa la sección de abajo.
              </p>
            </Step>
          </ol>
        </div>

        {/* Auto-start */}
        <div
          style={{
            background: "#F9FAFB",
            border: "1px solid #E5E7EB",
            borderRadius: 16,
            padding: 24,
            marginBottom: 24,
          }}
        >
          <h3 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 12px" }}>
            🔄 Que arranque automáticamente al prender el PC
          </h3>
          {os === "windows" && (
            <ol style={{ margin: 0, paddingLeft: 20, fontSize: 14, lineHeight: 1.7 }}>
              <li>Abre el <strong>&quot;Programador de tareas&quot;</strong> de Windows</li>
              <li>Click en <strong>&quot;Crear tarea básica&quot;</strong></li>
              <li>Nombre: <Code>Pulstock Agent</Code></li>
              <li>Desencadenador: <strong>&quot;Al iniciar sesión&quot;</strong></li>
              <li>
                Acción: <strong>Iniciar programa</strong> →{" "}
                <Code>python.exe</Code> con argumento{" "}
                <Code>C:\Pulstock\pulstock_agent.py</Code>
              </li>
            </ol>
          )}
          {os === "mac" && (
            <CodeBlock>
{`# Crear ~/Library/LaunchAgents/com.pulstock.agent.plist:
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>com.pulstock.agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/TU_USUARIO/pulstock/pulstock_agent.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>

# Activar:
launchctl load ~/Library/LaunchAgents/com.pulstock.agent.plist`}
            </CodeBlock>
          )}
          {os === "linux" && (
            <CodeBlock>
{`# Crear ~/.config/systemd/user/pulstock-agent.service:
[Unit]
Description=Pulstock Printer Agent

[Service]
ExecStart=/usr/bin/python3 /home/TU_USUARIO/pulstock/pulstock_agent.py
Restart=always

[Install]
WantedBy=default.target

# Activar:
systemctl --user enable --now pulstock-agent`}
            </CodeBlock>
          )}
        </div>

        {/* FAQ */}
        <div
          style={{
            background: "#fff",
            border: "1px solid #E5E7EB",
            borderRadius: 16,
            padding: 24,
            marginBottom: 24,
          }}
        >
          <h3 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 16px" }}>
            💡 Preguntas frecuentes
          </h3>
          <FAQ q="¿Dónde se guarda la configuración?">
            En <Code>
              {os === "windows"
                ? "C:\\Users\\TU_USUARIO\\.pulstock_agent\\"
                : "~/.pulstock_agent/"}
            </Code>
            — ahí también están los logs (<Code>agent.log</Code>).
          </FAQ>
          <FAQ q="¿El agente consume muchos recursos?">
            No. Usa ~15-30 MB de RAM y casi 0% de CPU. Hace un pequeño
            chequeo cada 3 segundos.
          </FAQ>
          <FAQ q="¿Funciona con cualquier impresora?">
            Sí — cualquier impresora instalada en Windows/macOS/Linux (ej:
            POS-801, Epson TM-T20, Xprinter), impresoras USB ESC/POS
            directas, o impresoras de red (IP + puerto 9100).
          </FAQ>
          <FAQ q="¿Los celulares de los garzones tienen que estar en la misma red?">
            <strong>No</strong>. Pueden estar en datos móviles o en otra
            red WiFi. El agente escucha por internet.
          </FAQ>
          <FAQ q="¿Y si el PC se apaga?">
            Los trabajos se encolan. Cuando el PC prende de nuevo, el
            agente los toma y los imprime.
          </FAQ>
          <FAQ q="¿Es seguro?">
            Sí. El agente usa una API key única de 64 caracteres para
            autenticarse. No abre puertos en tu PC — solo hace salidas
            HTTPS hacia Pulstock.
          </FAQ>
        </div>

        {/* Soporte */}
        <div
          style={{
            textAlign: "center",
            fontSize: 13,
            color: "#6B7280",
          }}
        >
          ¿Algún problema? Escríbenos a{" "}
          <a href="mailto:soporte@pulstock.cl" style={{ color: "#4F46E5" }}>
            soporte@pulstock.cl
          </a>
        </div>
      </div>
    </div>
  );
}

/* ── helpers ─────────────────────────────────────────────────────────── */

function Step({
  num,
  title,
  children,
}: {
  num: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li
      style={{
        display: "flex",
        gap: 16,
        marginBottom: 20,
        paddingBottom: 20,
        borderBottom: "1px dashed #E5E7EB",
      }}
    >
      <div
        style={{
          flexShrink: 0,
          width: 32,
          height: 32,
          borderRadius: 99,
          background: "#EEF2FF",
          color: "#4F46E5",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontWeight: 700,
          fontSize: 14,
        }}
      >
        {num}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, marginBottom: 6, fontSize: 15 }}>
          {title}
        </div>
        <div style={{ fontSize: 14, color: "#374151", lineHeight: 1.6 }}>
          {children}
        </div>
      </div>
    </li>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code
      style={{
        background: "#F3F4F6",
        padding: "2px 6px",
        borderRadius: 4,
        fontSize: "0.9em",
        fontFamily: "'JetBrains Mono', monospace",
        color: "#4F46E5",
      }}
    >
      {children}
    </code>
  );
}

function CodeBlock({ children }: { children: React.ReactNode }) {
  const text = typeof children === "string" ? children : "";
  return (
    <pre
      style={{
        background: "#1F2937",
        color: "#F3F4F6",
        padding: 14,
        borderRadius: 8,
        fontSize: 13,
        lineHeight: 1.6,
        overflowX: "auto",
        fontFamily: "'JetBrains Mono', monospace",
        margin: 0,
      }}
    >
      <code>{text}</code>
    </pre>
  );
}

function FAQ({
  q,
  children,
}: {
  q: string;
  children: React.ReactNode;
}) {
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
      <div style={{ padding: "4px 0 8px 14px", fontSize: 13.5, color: "#4B5563", lineHeight: 1.6 }}>
        {children}
      </div>
    </details>
  );
}
