#!/usr/bin/env bash
# ==========================================================
#  Pulstock Printer Agent - Instalador para Mac/Linux
# ==========================================================
# Uso: doble click en el archivo, o desde terminal:
#   bash instalar-pulstock.sh

set -e

# Moverse a la carpeta donde está este script
cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "  Pulstock Printer Agent - Instalador"
echo "========================================"
echo ""

# ─── Paso 1: verificar Python ─────────────────────────────────
echo "[1/4] Verificando Python..."
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "    Python 3 no está instalado."
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "    Abrí una terminal y ejecutá:"
        echo "      xcode-select --install"
        echo "    O instalá con Homebrew:"
        echo "      brew install python3"
    else
        echo "    Instalá Python con:"
        echo "      sudo apt install python3 python3-pip      # Ubuntu/Debian"
        echo "      sudo dnf install python3 python3-pip      # Fedora"
    fi
    echo ""
    read -p "Presioná Enter para cerrar..."
    exit 1
fi
echo "    ✓ Python instalado."
echo ""

# ─── Paso 2: instalar dependencias ────────────────────────────
echo "[2/4] Instalando dependencias..."
python3 -m pip install --user --quiet --upgrade pip 2>/dev/null || true
python3 -m pip install --user --quiet -r requirements.txt
echo "    ✓ Dependencias OK."
echo ""

# ─── Paso 3: emparejar ────────────────────────────────────────
echo "[3/4] Emparejar con tu cuenta Pulstock"
echo ""
echo "    Abriremos el agente para que escribas tu código de emparejado."
echo "    El código lo obtenés en Pulstock → Configuración → Impresoras"
echo "    → Agregar agente PC."
echo ""
read -p "Presioná Enter para continuar..."
python3 pulstock_agent.py --pair
echo ""
echo "    ✓ Agente emparejado."
echo ""

# ─── Paso 4: auto-start ───────────────────────────────────────
echo "[4/4] Configurando inicio automático..."

INSTALL_DIR="$(pwd)"

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS: launchd
    PLIST="$HOME/Library/LaunchAgents/com.pulstock.agent.plist"
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.pulstock.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(command -v python3)</string>
        <string>${INSTALL_DIR}/pulstock_agent.py</string>
    </array>
    <key>WorkingDirectory</key><string>${INSTALL_DIR}</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>${INSTALL_DIR}/agent.log</string>
    <key>StandardErrorPath</key><string>${INSTALL_DIR}/agent.log</string>
</dict>
</plist>
EOF
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "    ✓ Registrado con launchd (arranca al iniciar sesión)."
else
    # Linux: systemd user service
    SERVICE_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SERVICE_DIR"
    cat > "$SERVICE_DIR/pulstock-agent.service" <<EOF
[Unit]
Description=Pulstock Printer Agent
After=network-online.target

[Service]
WorkingDirectory=${INSTALL_DIR}
ExecStart=$(command -v python3) ${INSTALL_DIR}/pulstock_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable pulstock-agent.service
    systemctl --user start pulstock-agent.service
    echo "    ✓ Registrado con systemd (arranca al iniciar sesión)."
fi
echo ""

# ─── Arrancar ahora en segundo plano ──────────────────────────
nohup python3 pulstock_agent.py >/dev/null 2>&1 &
echo ""
echo "========================================"
echo "  ¡Instalación completa!"
echo "========================================"
echo ""
echo "  El agente está corriendo en segundo plano."
echo "  Abrí Pulstock y verás el agente como \"En línea\"."
echo ""
read -p "Presioná Enter para cerrar..."
