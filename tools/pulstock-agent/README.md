# Pulstock Printer Agent

Agente liviano que corre en el PC del local y enlaza impresoras locales (USB, sistema o LAN) con Pulstock en la nube.

## ¿Para qué sirve?

- El PC con agente detecta las impresoras del local y las reporta a Pulstock
- Cuando cualquier celular/tablet/PC pide imprimir una boleta, el agente la imprime en la impresora local
- No requiere emparejamiento individual por dispositivo
- Los dispositivos (celulares) pueden estar en otra red (datos móviles)

## Instalación

### Opción 1 — Python (cualquier OS)

1. Instala Python 3.8 o superior
2. Descarga/clona este directorio
3. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. Empareja con tu cuenta Pulstock:
   ```bash
   python pulstock_agent.py --pair
   ```
   Te pedirá el código que te entregó Pulstock (Configuración → Impresoras → Agregar agente PC).
5. Corre el agente:
   ```bash
   python pulstock_agent.py
   ```

### Opción 2 — Windows .exe (próximamente)

Pronto vamos a entregar un `PulstockAgent.exe` que instala todo automáticamente.

## Configuración

Una vez emparejado, el agente guarda su config en:
- Windows: `C:\Users\TU_USUARIO\.pulstock_agent\config.json`
- Mac/Linux: `~/.pulstock_agent/config.json`

Los logs quedan en el mismo directorio en `agent.log`.

## Dejarlo corriendo 24/7

### Windows — Tarea programada al inicio

1. Abre "Programador de tareas"
2. Crear tarea → Nombre: "Pulstock Agent"
3. Desencadenador: "Al iniciar sesión"
4. Acción: Iniciar programa → `python.exe`
   - Argumentos: `C:\ruta\a\pulstock_agent.py`
5. Listo

### Mac — launchd

```bash
# Crear ~/Library/LaunchAgents/com.pulstock.agent.plist con:
# <Program>/usr/bin/python3</Program>
# <ProgramArguments><string>/ruta/a/pulstock_agent.py</string></ProgramArguments>
# <RunAtLoad>true</RunAtLoad>
launchctl load ~/Library/LaunchAgents/com.pulstock.agent.plist
```

### Linux — systemd user service

```ini
# ~/.config/systemd/user/pulstock-agent.service
[Unit]
Description=Pulstock Printer Agent

[Service]
ExecStart=/usr/bin/python3 /ruta/a/pulstock_agent.py
Restart=always

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now pulstock-agent
```

## Diagnóstico

Si algo no funciona:

1. Mira el log:
   ```bash
   tail -f ~/.pulstock_agent/agent.log
   ```
2. Verifica que la URL del API esté bien:
   ```bash
   python pulstock_agent.py --pair  # vuelve a emparejar si cambió
   ```
3. Verifica conectividad:
   ```bash
   curl -s http://65.108.148.200/api/core/health/
   ```

## Cómo funciona

```
┌──────── PC con agente ────────┐
│                               │
│   pulstock_agent.py           │
│        ↓ poll cada 3s         │
│   API Pulstock (internet)     │
│        ↓ hay trabajo?         │
│   sí → imprime localmente     │
│        ├─ win32print (Win)    │
│        ├─ lp (Mac/Linux)      │
│        └─ socket TCP 9100     │
│           (impresoras LAN)    │
└───────────────────────────────┘
```

## Soporte

- Email: soporte@pulstock.cl
- Dashboard: https://pulstock.cl/dashboard
