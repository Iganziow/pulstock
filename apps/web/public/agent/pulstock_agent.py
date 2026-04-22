#!/usr/bin/env python3
"""
Pulstock Printer Agent
======================
Agente liviano que corre en el PC del local, enlaza impresoras locales
(USB, sistema o LAN) y ejecuta trabajos de impresión recibidos desde la
nube de Pulstock.

Modos de uso:
    # GUI normal (doble click al .exe en Windows)
    pulstock_agent.py

    # CLI tradicional (sin ventanas, todo por terminal)
    pulstock_agent.py --cli

    # Re-emparejar manualmente desde CLI
    pulstock_agent.py --cli --pair

Requisitos: Python 3.8+ y los paquetes de requirements.txt
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import logging
import os
import platform
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

__version__ = "2.0.0"


class AgentUnauthorized(Exception):
    """El servidor rechazó la api_key (HTTP 401). Disparado por cualquier
    request del agente. El loop principal lo captura y lanza el flujo de
    re-pair (gráfico en GUI, interactivo en CLI)."""


# ─── Config ──────────────────────────────────────────────────────────────

DEFAULT_API_URL = os.environ.get("PULSTOCK_API_URL", "https://api.pulstock.cl/api")
DEFAULT_POLL_INTERVAL = 3   # seconds between polls when idle
DEFAULT_ERROR_BACKOFF = 10  # seconds to wait after an error

CONFIG_DIR = Path.home() / ".pulstock_agent"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "agent.log"

# Color de marca (indigo Pulstock)
BRAND_PRIMARY = "#4F46E5"
BRAND_PRIMARY_DARK = "#4338CA"
BRAND_BG = "#FAFBFF"
BRAND_TEXT = "#1F2937"
BRAND_MUTED = "#6B7280"
BRAND_GREEN = "#16A34A"
BRAND_RED = "#DC2626"
BRAND_AMBER = "#D97706"


# ─── Logging ─────────────────────────────────────────────────────────────

def _setup_logging(verbose: bool = False) -> logging.Logger:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)s: %(message)s"
    handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    # Solo agregar StreamHandler si la consola es escribible. En el .exe sin
    # consola (PyInstaller --windowed), sys.stdout puede ser None y crashea.
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    return logging.getLogger("pulstock-agent")


log = _setup_logging()


# ─── Config persistence ──────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Config corrupta: %s — se ignora", e)
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass
    log.debug("Config guardada en %s", CONFIG_FILE)


def invalidate_config() -> None:
    """Mover config a backup .invalid_<ts>.json. Llamado ante 401."""
    if not CONFIG_FILE.exists():
        return
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONFIG_FILE.with_name(f"config.invalid_{ts}.json")
    try:
        CONFIG_FILE.rename(backup)
        log.warning("Config inválido movido a: %s", backup)
    except OSError as e:
        log.warning("No se pudo mover el config viejo: %s", e)


# ─── HTTP helpers ────────────────────────────────────────────────────────

def http_json(method: str, url: str, data: dict | None = None,
              headers: dict | None = None, timeout: int = 30) -> tuple[int, dict]:
    body = None
    hdrs = {"Content-Type": "application/json", "User-Agent": f"PulstockAgent/{__version__}"}
    if headers:
        hdrs.update(headers)
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urlrequest.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, {"raw": raw}
    except urlerror.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, {"detail": raw or str(e)}
    except urlerror.URLError as e:
        return 0, {"detail": f"Network error: {e.reason}"}
    except socket.timeout:
        return 0, {"detail": "Timeout"}


# ─── Printer discovery ───────────────────────────────────────────────────

def list_system_printers() -> list[dict]:
    """Return list of system-installed printers. Works on Windows/Mac/Linux."""
    system = platform.system()
    out: list[dict] = []
    try:
        if system == "Windows":
            try:
                import win32print  # noqa
                flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                for p in win32print.EnumPrinters(flags, None, 2):
                    out.append({
                        "name": p["pPrinterName"],
                        "display_name": p["pPrinterName"],
                        "connection_type": "system",
                        "paper_width": 80,
                        "is_default": False,
                    })
                default = win32print.GetDefaultPrinter()
                for p in out:
                    if p["name"] == default:
                        p["is_default"] = True
                        break
            except ImportError:
                log.warning("win32print no instalado — usa `pip install pywin32`")
        elif system in ("Darwin", "Linux"):
            result = subprocess.run(
                ["lpstat", "-p"], capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("printer "):
                    name = line.split()[1]
                    out.append({
                        "name": name, "display_name": name,
                        "connection_type": "system", "paper_width": 80,
                        "is_default": False,
                    })
            dr = subprocess.run(
                ["lpstat", "-d"], capture_output=True, text=True, timeout=5,
            )
            for line in dr.stdout.splitlines():
                if "system default destination:" in line.lower():
                    default = line.split(":")[-1].strip()
                    for p in out:
                        if p["name"] == default:
                            p["is_default"] = True
                            break
    except Exception as e:
        log.warning("Error listando impresoras: %s", e)
    return out


# ─── Printing actions ────────────────────────────────────────────────────

def print_bytes_system(printer_name: str, data: bytes) -> None:
    system = platform.system()
    if system == "Windows":
        import win32print
        h = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(h, 1, ("Pulstock Receipt", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
    elif system in ("Darwin", "Linux"):
        if printer_name.startswith("-"):
            raise RuntimeError(f"printer_name inválido: {printer_name!r}")
        proc = subprocess.Popen(
            ["lp", "-d", printer_name, "-o", "raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            _, err = proc.communicate(data, timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("lp timeout (>30s) imprimiendo")
        if proc.returncode != 0:
            err_txt = (err or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"lp exited with {proc.returncode}: {err_txt or '(sin stderr)'}")
    else:
        raise RuntimeError(f"OS no soportado: {system}")


def print_bytes_network(address: str, data: bytes) -> None:
    if ":" in address:
        host, port_s = address.split(":", 1)
        port = int(port_s)
    else:
        host, port = address, 9100
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        sock.sendall(data)
    finally:
        sock.close()


# ─── Auto-startup (Windows) ──────────────────────────────────────────────

AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = "PulstockPrinterAgent"


def is_frozen() -> bool:
    """True si corremos como .exe empaquetado por PyInstaller."""
    return getattr(sys, "frozen", False)


def get_autostart_target() -> str:
    """Path al ejecutable que debe correr al arranque."""
    if is_frozen():
        return sys.executable  # el .exe en sí mismo
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'


def is_autostart_enabled() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY) as k:
            try:
                winreg.QueryValueEx(k, AUTOSTART_VALUE_NAME)
                return True
            except FileNotFoundError:
                return False
    except OSError:
        return False


def enable_autostart() -> None:
    if platform.system() != "Windows":
        return
    import winreg
    target = get_autostart_target()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY,
                        0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, target)
    log.info("Auto-arranque activado: %s", target)


def disable_autostart() -> None:
    if platform.system() != "Windows":
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY,
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, AUTOSTART_VALUE_NAME)
        log.info("Auto-arranque desactivado")
    except (FileNotFoundError, OSError):
        pass


# ═══════════════════════════════════════════════════════════════════════
# CORE WORKER — la lógica de polling/print no depende de UI
# ═══════════════════════════════════════════════════════════════════════


class AgentWorker:
    """Loop principal del agente corriendo en un thread separado.

    Comunica eventos hacia la UI (gráfica o CLI) vía la cola `events`. La
    UI es opcional — sin ella, el worker sigue corriendo y solo loguea.

    Eventos emitidos (cada uno es un dict {"type": str, ...payload}):
      - {"type": "started"}
      - {"type": "online", "tenant": str, "agent_name": str}
      - {"type": "printers_reported", "count": int}
      - {"type": "job_received", "id": int, "printer": str}
      - {"type": "job_done", "id": int}
      - {"type": "job_failed", "id": int, "error": str}
      - {"type": "unauthorized"}              # 401 → necesita re-pareo
      - {"type": "network_error", "msg": str} # poll falló sin 401
      - {"type": "stopped"}
    """

    PRINTERS_REPORT_INTERVAL = 300  # 5 min

    def __init__(self, events: queue.Queue | None = None):
        self.events = events
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_state = "idle"
        self.tenant_name = ""
        self.agent_name = ""
        self.printers_count = 0

    # ── Public API ──────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="agent-worker")
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── Internals ───────────────────────────────────────────────

    def _emit(self, event: dict) -> None:
        if self.events is not None:
            try:
                self.events.put_nowait(event)
            except queue.Full:
                pass  # UI lenta — se pierde el evento, no es crítico

    def _run(self) -> None:
        cfg = load_config()
        if not cfg.get("api_key"):
            log.warning("Worker arrancó sin api_key — saliendo")
            self._emit({"type": "unauthorized"})
            return

        api_url = cfg["api_url"]
        api_key = cfg["api_key"]
        poll_interval = cfg.get("poll_interval", DEFAULT_POLL_INTERVAL)
        self.tenant_name = cfg.get("tenant_name", "")
        self.agent_name = cfg.get("agent_name", "")

        log.info("Pulstock Printer Agent v%s iniciando", __version__)
        log.info("Agente: %s (tenant=%s)", self.agent_name, self.tenant_name)
        log.info("API: %s", api_url)
        log.info("API key prefix: %s… (len=%d)", api_key[:8], len(api_key))

        self._emit({"type": "started"})

        # Reportar impresoras al arrancar
        try:
            self._report_printers(api_url, api_key)
        except AgentUnauthorized:
            self._emit({"type": "unauthorized"})
            return

        self._emit({
            "type": "online",
            "tenant": self.tenant_name,
            "agent_name": self.agent_name,
        })

        last_printers_report = time.time()

        while not self._stop.is_set():
            try:
                if time.time() - last_printers_report > self.PRINTERS_REPORT_INTERVAL:
                    self._report_printers(api_url, api_key)
                    last_printers_report = time.time()

                status, resp = http_json(
                    "GET", f"{api_url}/printing/agents/poll/?key={api_key}",
                    timeout=15,
                )
                if status == 401:
                    raise AgentUnauthorized("Poll devolvió 401")
                if status != 200:
                    log.warning("Poll falló: status=%s resp=%s", status, resp)
                    self._emit({
                        "type": "network_error",
                        "msg": f"Servidor respondió {status}",
                    })
                    self._wait(DEFAULT_ERROR_BACKOFF)
                    continue

                job = resp.get("job")
                if not job:
                    self._wait(poll_interval)
                    continue

                self._process_job(api_url, api_key, job)

            except AgentUnauthorized:
                self._emit({"type": "unauthorized"})
                return
            except Exception as e:
                log.exception("Error en loop: %s", e)
                self._emit({"type": "network_error", "msg": str(e)})
                self._wait(DEFAULT_ERROR_BACKOFF)

        self._emit({"type": "stopped"})
        log.info("Worker detenido")

    def _wait(self, seconds: float) -> None:
        """Wait responsive a stop()."""
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop.is_set():
            time.sleep(min(0.5, end - time.monotonic()))

    def _report_printers(self, api_url: str, api_key: str) -> None:
        printers = list_system_printers()
        self.printers_count = len(printers)
        log.info("Impresoras detectadas: %d", len(printers))
        for p in printers:
            log.info("  - %s (default=%s)", p["name"], p["is_default"])

        status, resp = http_json(
            "POST", f"{api_url}/printing/agents/printers/?key={api_key}",
            data={"printers": printers},
        )
        if status == 401:
            raise AgentUnauthorized("printers/ devolvió 401")
        if status == 200:
            log.info("Impresoras reportadas correctamente")
            self._emit({"type": "printers_reported", "count": len(printers)})
        else:
            log.warning("Error reportando impresoras: status=%s resp=%s", status, resp)

    def _process_job(self, api_url: str, api_key: str, job: dict) -> None:
        job_id = job["id"]
        printer_name = (job.get("printer_name") or "").strip()
        data_b64 = job.get("data_b64") or ""
        html = job.get("html") or ""
        connection_type = (job.get("connection_type") or "system").strip().lower()
        network_address = (job.get("network_address") or "").strip()

        log.info(
            "Job #%s recibido (printer=%r, conn=%s, addr=%r, bytes=%d, source=%s)",
            job_id, printer_name, connection_type, network_address,
            len(data_b64) * 3 // 4, job.get("source"),
        )
        self._emit({"type": "job_received", "id": job_id, "printer": printer_name or "(default)"})

        if connection_type in ("system", "usb") and not printer_name:
            printers = list_system_printers()
            default = next((p for p in printers if p["is_default"]), None)
            if default:
                printer_name = default["name"]

        if connection_type in ("system", "usb") and not printer_name:
            err = "No hay impresora del sistema configurada"
            self._report_result(api_url, api_key, job_id, False, err)
            self._emit({"type": "job_failed", "id": job_id, "error": err})
            return

        if connection_type == "network" and not network_address:
            err = f"Impresora '{printer_name}' es de red pero no tiene IP configurada en el panel."
            self._report_result(api_url, api_key, job_id, False, err)
            self._emit({"type": "job_failed", "id": job_id, "error": err})
            return

        try:
            if not data_b64:
                if html:
                    raise NotImplementedError(
                        "Impresión HTML no implementada en este agente; envía ESC/POS en data_b64."
                    )
                raise ValueError("Job sin payload (data_b64 o html)")

            raw = base64.b64decode(data_b64)
            if connection_type == "network":
                log.info("Imprimiendo por red a %s", network_address)
                print_bytes_network(network_address, raw)
            else:
                print_bytes_system(printer_name, raw)

            log.info("Job #%s impreso correctamente", job_id)
            self._report_result(api_url, api_key, job_id, True, "")
            self._emit({"type": "job_done", "id": job_id})
        except Exception as e:
            log.exception("Error imprimiendo job #%s", job_id)
            err = str(e)
            self._report_result(api_url, api_key, job_id, False, err)
            self._emit({"type": "job_failed", "id": job_id, "error": err})

    def _report_result(self, api_url: str, api_key: str, job_id: int,
                       success: bool, error: str) -> None:
        body: dict = {"success": success}
        if error:
            body["error"] = error
        status, _ = http_json(
            "POST", f"{api_url}/printing/jobs/{job_id}/complete/?key={api_key}",
            data=body,
        )
        if status == 401:
            log.warning("complete/ devolvió 401 — re-pair en próxima iteración")
        elif status != 200:
            log.warning("Error reportando resultado: status=%s", status)


# ═══════════════════════════════════════════════════════════════════════
# PAREO — lógica común a CLI y GUI
# ═══════════════════════════════════════════════════════════════════════


def pair_with_code(code: str, api_url: str = DEFAULT_API_URL) -> tuple[bool, str, dict]:
    """Intenta canjear un código de pareo por una api_key.

    Retorna (ok, mensaje, datos). Si ok, datos contiene la config a guardar.
    Si !ok, mensaje es el error legible para mostrar al usuario.
    """
    code = (code or "").strip().upper()
    if not code:
        return False, "Por favor ingresa el código.", {}

    os_info = f"{platform.system()} {platform.release()}"
    status, resp = http_json("POST", f"{api_url}/printing/agents/pair/", data={
        "pairing_code": code,
        "version": __version__,
        "os_info": os_info,
    })

    if status == 0:
        return False, f"No hay conexión a internet. Detalle: {resp.get('detail', '?')}", {}
    if status == 429:
        return False, "Demasiados intentos. Espera unos minutos antes de volver a probar.", {}
    if status == 404:
        return False, "Código inválido o expirado. Pídele a tu admin uno nuevo en el panel.", {}
    if status != 200:
        return False, f"Error {status}: {resp.get('detail', 'desconocido')}", {}

    cfg = {
        "api_url": api_url,
        "api_key": resp["api_key"],
        "agent_id": resp["agent_id"],
        "agent_name": resp["agent_name"],
        "tenant_name": resp["tenant_name"],
        "poll_interval": resp.get("poll_interval_seconds", DEFAULT_POLL_INTERVAL),
    }
    return True, "Conectado correctamente.", cfg


# ═══════════════════════════════════════════════════════════════════════
# CLI MODE — terminal-only (para usuarios técnicos / Linux / debugging)
# ═══════════════════════════════════════════════════════════════════════


def cmd_pair_cli(api_url: str) -> int:
    """Pareo interactivo desde terminal."""
    print("\n" + "=" * 60)
    print("  PULSTOCK PRINTER AGENT — Emparejamiento")
    print("=" * 60)
    print()
    print("Pídele al admin que cree un agente para este PC desde:")
    print("  Configuración → Impresoras → Agregar agente PC")
    print()

    code = input("Ingresa el código de emparejamiento (ej: ABCD-1234): ").strip().upper()
    ok, msg, cfg = pair_with_code(code, api_url)
    if not ok:
        print(f"\n✗ {msg}")
        return 1

    save_config(cfg)
    print()
    print("=" * 60)
    print(f"  ✓ Emparejado exitosamente")
    print("=" * 60)
    print(f"  Agente:  {cfg['agent_name']}")
    print(f"  Tenant:  {cfg['tenant_name']}")
    print(f"  Config:  {CONFIG_FILE}")
    print()
    return 0


def cmd_run_cli() -> int:
    """Loop principal en CLI puro. Maneja 401 con re-pareo interactivo."""
    cfg = load_config()
    if not cfg.get("api_key"):
        rc = cmd_pair_cli(DEFAULT_API_URL)
        if rc != 0:
            return rc
        cfg = load_config()

    events: queue.Queue = queue.Queue()
    worker = AgentWorker(events=events)
    worker.start()

    _running = {"v": True}

    def _shutdown(signum, frame):
        log.info("Señal recibida, deteniendo...")
        _running["v"] = False

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    while _running["v"] and worker.is_running():
        try:
            evt = events.get(timeout=1.0)
        except queue.Empty:
            continue
        etype = evt.get("type")
        if etype == "unauthorized":
            print("\n⚠  El servidor rechazó la api_key. Re-emparejando...\n")
            invalidate_config()
            worker.stop()
            rc = cmd_pair_cli(DEFAULT_API_URL)
            if rc != 0:
                return rc
            return cmd_run_cli()  # restart
        elif etype == "job_received":
            print(f"  → Imprimiendo job #{evt['id']} en '{evt['printer']}'...")
        elif etype == "job_done":
            print(f"  ✓ Job #{evt['id']} OK")
        elif etype == "job_failed":
            print(f"  ✗ Job #{evt['id']} falló: {evt['error']}")
        elif etype == "online":
            print(f"  ✓ Conectado como '{evt['agent_name']}' (tenant: {evt['tenant']})")
        elif etype == "network_error":
            print(f"  ⚠  {evt['msg']}")

    worker.stop()
    return 0


# ═══════════════════════════════════════════════════════════════════════
# GUI MODE — ventana Tkinter + system tray (DEFAULT en Windows)
# ═══════════════════════════════════════════════════════════════════════


def _make_tray_image(color: str = BRAND_PRIMARY):
    """Genera el icono del system tray (64x64, círculo + 'P')."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Convertir hex a RGB
    c = color.lstrip("#")
    rgb = (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    draw.ellipse((4, 4, 60, 60), fill=rgb + (255,))
    # Una "P" simple
    try:
        from PIL import ImageFont
        for fpath in ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
            if os.path.exists(fpath):
                font = ImageFont.truetype(fpath, 36)
                break
        else:
            font = ImageFont.load_default()
    except Exception:
        font = None
    if font:
        bbox = draw.textbbox((0, 0), "P", font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((64 - w) // 2 - bbox[0], (64 - h) // 2 - bbox[1] - 2),
                  "P", fill=(255, 255, 255, 255), font=font)
    return img


class PulstockAgentGUI:
    """GUI principal: ventana de pareo o ventana de estado + system tray."""

    def __init__(self):
        import tkinter as tk
        self.tk = tk
        self.root: tk.Tk | None = None
        self.events: queue.Queue = queue.Queue(maxsize=200)
        self.worker: AgentWorker | None = None
        self.tray = None
        self.tray_thread: threading.Thread | None = None
        self.status_label = None
        self.printers_label = None
        self.last_event_label = None
        self.is_paired = bool(load_config().get("api_key"))

    # ── Entry point ─────────────────────────────────────────────

    def run(self) -> int:
        if self.is_paired:
            self._start_worker()
            self._start_tray()
            self._show_status_window(minimized=True)
        else:
            self._show_pair_window()

        # Tkinter mainloop bloquea hasta que la ventana se cierre.
        if self.root:
            self.root.mainloop()
        # Cuando la ventana se cierre, si el tray está activo seguimos vivos.
        # Si no hay tray, salimos.
        if self.tray and self.tray.visible:
            # Bloquea hasta que se invoque tray.stop()
            while self.tray.visible:
                time.sleep(0.5)
        if self.worker:
            self.worker.stop()
        return 0

    # ── Pair window ─────────────────────────────────────────────

    def _show_pair_window(self) -> None:
        tk = self.tk
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
        root = tk.Tk()
        self.root = root
        root.title("Pulstock — Conectar PC")
        root.configure(bg=BRAND_BG)
        root.geometry("520x520")
        root.resizable(False, False)
        try:
            root.iconbitmap(default="")  # evita el icono Tk feo
        except Exception:
            pass

        # Centrar en pantalla
        root.update_idletasks()
        w, h = 520, 520
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")

        # Header
        header = tk.Frame(root, bg=BRAND_PRIMARY, height=80)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🖨️  Pulstock", bg=BRAND_PRIMARY, fg="white",
                 font=("Segoe UI", 22, "bold")).pack(pady=(18, 0))
        tk.Label(header, text="Conectar este PC al panel",
                 bg=BRAND_PRIMARY, fg="white",
                 font=("Segoe UI", 11)).pack()

        # Body
        body = tk.Frame(root, bg=BRAND_BG)
        body.pack(fill="both", expand=True, padx=40, pady=24)

        tk.Label(body, text="Escribe el código de emparejado",
                 bg=BRAND_BG, fg=BRAND_TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(body,
                 text="Pídele a tu administrador un código en:\n"
                      "Configuración → Impresoras → Agregar PC",
                 bg=BRAND_BG, fg=BRAND_MUTED, font=("Segoe UI", 10),
                 justify="left").pack(anchor="w", pady=(0, 16))

        code_var = tk.StringVar()
        entry = tk.Entry(body, textvariable=code_var,
                         font=("Consolas", 22, "bold"),
                         justify="center",
                         bg="white", fg=BRAND_PRIMARY,
                         relief="solid", bd=2,
                         highlightcolor=BRAND_PRIMARY, highlightthickness=2)
        entry.pack(fill="x", ipady=10, pady=(0, 4))
        entry.focus_set()

        tk.Label(body, text="Ejemplo: ABCD-1234",
                 bg=BRAND_BG, fg=BRAND_MUTED,
                 font=("Segoe UI", 9, "italic")).pack(anchor="w")

        # Auto-arranque checkbox
        autostart_var = tk.BooleanVar(value=True)
        if platform.system() == "Windows":
            tk.Checkbutton(body,
                           text="Iniciar Pulstock automáticamente cuando prenda este PC",
                           variable=autostart_var,
                           bg=BRAND_BG, fg=BRAND_TEXT,
                           font=("Segoe UI", 10),
                           activebackground=BRAND_BG,
                           selectcolor="white").pack(anchor="w", pady=(20, 0))

        # Status label
        status_var = tk.StringVar(value="")
        status_lbl = tk.Label(body, textvariable=status_var, bg=BRAND_BG,
                              font=("Segoe UI", 10), wraplength=440, justify="left")
        status_lbl.pack(anchor="w", pady=(16, 0))

        # Connect button
        btn_frame = tk.Frame(body, bg=BRAND_BG)
        btn_frame.pack(fill="x", pady=(20, 0))

        connect_btn = tk.Button(btn_frame, text="Conectar",
                                bg=BRAND_PRIMARY, fg="white",
                                activebackground=BRAND_PRIMARY_DARK,
                                activeforeground="white",
                                font=("Segoe UI", 12, "bold"),
                                relief="flat", bd=0, cursor="hand2",
                                padx=24, pady=12)
        connect_btn.pack(side="left", fill="x", expand=True)

        def do_connect():
            connect_btn.config(state="disabled", text="Conectando…")
            status_lbl.config(fg=BRAND_MUTED)
            status_var.set("Conectando con el servidor…")
            root.update_idletasks()

            def _worker():
                ok, msg, cfg = pair_with_code(code_var.get(), DEFAULT_API_URL)
                root.after(0, lambda: _on_result(ok, msg, cfg))

            def _on_result(ok: bool, msg: str, cfg: dict):
                if ok:
                    save_config(cfg)
                    if autostart_var.get():
                        try:
                            enable_autostart()
                        except Exception as e:
                            log.warning("No se pudo activar auto-arranque: %s", e)
                    status_lbl.config(fg=BRAND_GREEN)
                    status_var.set(
                        f"✓ Conectado como '{cfg['agent_name']}' (tenant: {cfg['tenant_name']}).\n"
                        f"Iniciando agente…"
                    )
                    root.after(1200, self._switch_to_status)
                else:
                    connect_btn.config(state="normal", text="Conectar")
                    status_lbl.config(fg=BRAND_RED)
                    status_var.set(f"✗ {msg}")

            threading.Thread(target=_worker, daemon=True).start()

        connect_btn.config(command=do_connect)
        entry.bind("<Return>", lambda e: do_connect())

        # Footer
        footer = tk.Frame(root, bg=BRAND_BG)
        footer.pack(fill="x", side="bottom", pady=(0, 12))
        tk.Label(footer, text=f"Pulstock Printer Agent v{__version__}  ·  pulstock.cl",
                 bg=BRAND_BG, fg=BRAND_MUTED,
                 font=("Segoe UI", 8)).pack()

    def _switch_to_status(self) -> None:
        """Pareo OK → cierra ventana de pair, arranca worker + tray + status."""
        self.is_paired = True
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
        self._start_worker()
        self._start_tray()
        self._show_status_window(minimized=True)
        if self.root:
            self.root.mainloop()

    # ── Status window ───────────────────────────────────────────

    def _show_status_window(self, minimized: bool = False) -> None:
        tk = self.tk
        cfg = load_config()
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
        root = tk.Tk()
        self.root = root
        root.title("Pulstock — Estado del agente")
        root.configure(bg=BRAND_BG)
        root.geometry("520x520")
        root.resizable(False, False)

        # Centrar
        root.update_idletasks()
        w, h = 520, 520
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")

        # Header
        header = tk.Frame(root, bg=BRAND_PRIMARY, height=80)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🖨️  Pulstock", bg=BRAND_PRIMARY, fg="white",
                 font=("Segoe UI", 22, "bold")).pack(pady=(18, 0))
        tk.Label(header, text=f"Conectado a {cfg.get('tenant_name', '?')}",
                 bg=BRAND_PRIMARY, fg="white", font=("Segoe UI", 11)).pack()

        body = tk.Frame(root, bg=BRAND_BG)
        body.pack(fill="both", expand=True, padx=32, pady=20)

        # Status big indicator
        self.status_label = tk.Label(body, text="● Iniciando…",
                                     bg=BRAND_BG, fg=BRAND_AMBER,
                                     font=("Segoe UI", 16, "bold"))
        self.status_label.pack(anchor="w", pady=(0, 4))

        agent_lbl = tk.Label(body, text=f"PC: {cfg.get('agent_name', '?')}",
                             bg=BRAND_BG, fg=BRAND_MUTED, font=("Segoe UI", 10))
        agent_lbl.pack(anchor="w")

        # Divider
        tk.Frame(body, bg="#E5E7EB", height=1).pack(fill="x", pady=14)

        # Stats
        self.printers_label = tk.Label(body, text="Impresoras detectadas: —",
                                       bg=BRAND_BG, fg=BRAND_TEXT,
                                       font=("Segoe UI", 11))
        self.printers_label.pack(anchor="w", pady=2)

        self.last_event_label = tk.Label(body,
                                         text="Esperando trabajos…",
                                         bg=BRAND_BG, fg=BRAND_MUTED,
                                         font=("Segoe UI", 10),
                                         wraplength=440, justify="left")
        self.last_event_label.pack(anchor="w", pady=2)

        tk.Frame(body, bg="#E5E7EB", height=1).pack(fill="x", pady=14)

        # Buttons row 1
        btn_row = tk.Frame(body, bg=BRAND_BG)
        btn_row.pack(fill="x", pady=(4, 6))

        def _btn(parent, text, color, command, dark=False):
            return tk.Button(parent, text=text,
                             bg=color, fg="white",
                             activebackground=BRAND_PRIMARY_DARK if dark else "#374151",
                             activeforeground="white",
                             font=("Segoe UI", 10, "bold"),
                             relief="flat", bd=0, cursor="hand2",
                             padx=14, pady=8, command=command)

        _btn(btn_row, "Imprimir prueba", BRAND_PRIMARY, self._on_test_print, dark=True).pack(side="left", padx=(0, 6))
        _btn(btn_row, "Reconectar", "#374151", self._on_reconnect).pack(side="left", padx=6)

        # Buttons row 2
        btn_row2 = tk.Frame(body, bg=BRAND_BG)
        btn_row2.pack(fill="x", pady=(0, 6))

        autostart_text = (
            "Quitar inicio automático" if is_autostart_enabled()
            else "Activar inicio automático"
        )
        if platform.system() == "Windows":
            self._autostart_btn = _btn(btn_row2, autostart_text, "#6B7280", self._toggle_autostart)
            self._autostart_btn.pack(side="left", padx=(0, 6))

        _btn(btn_row2, "Cerrar sesión", BRAND_RED, self._on_logout).pack(side="left", padx=6)

        # Footer
        footer = tk.Frame(root, bg=BRAND_BG)
        footer.pack(fill="x", side="bottom", pady=(0, 10))
        tk.Label(footer,
                 text=f"v{__version__}  ·  Logs: {LOG_FILE}",
                 bg=BRAND_BG, fg=BRAND_MUTED,
                 font=("Segoe UI", 8)).pack()

        # Close → minimizar al tray (no salir)
        root.protocol("WM_DELETE_WINDOW", self._on_close_window)

        if minimized:
            root.withdraw()  # arranca oculto

        # Polling de eventos del worker (cada 250ms)
        root.after(250, self._poll_events)

    def _poll_events(self) -> None:
        if not self.root:
            return
        try:
            while True:
                evt = self.events.get_nowait()
                self._handle_event(evt)
        except queue.Empty:
            pass
        if self.root:
            self.root.after(250, self._poll_events)

    def _handle_event(self, evt: dict) -> None:
        etype = evt.get("type")
        if etype == "online":
            self.status_label.config(text="● Conectado", fg=BRAND_GREEN)
            self.last_event_label.config(text="Esperando trabajos de impresión…")
        elif etype == "started":
            self.status_label.config(text="● Iniciando…", fg=BRAND_AMBER)
        elif etype == "printers_reported":
            self.printers_label.config(text=f"Impresoras detectadas: {evt['count']}")
        elif etype == "job_received":
            self.last_event_label.config(
                text=f"📄 Imprimiendo job #{evt['id']} en '{evt['printer']}'…",
                fg=BRAND_PRIMARY,
            )
        elif etype == "job_done":
            self.last_event_label.config(
                text=f"✓ Job #{evt['id']} impreso correctamente.",
                fg=BRAND_GREEN,
            )
        elif etype == "job_failed":
            self.last_event_label.config(
                text=f"✗ Job #{evt['id']} falló: {evt['error']}",
                fg=BRAND_RED,
            )
        elif etype == "network_error":
            self.status_label.config(text="● Sin conexión", fg=BRAND_AMBER)
            self.last_event_label.config(
                text=f"Reintentando… ({evt['msg']})", fg=BRAND_AMBER,
            )
        elif etype == "unauthorized":
            # El servidor rechazó. Avisar al usuario y reabrir ventana de pair.
            self._on_unauthorized()
        elif etype == "stopped":
            self.status_label.config(text="● Detenido", fg=BRAND_MUTED)

    # ── Worker management ───────────────────────────────────────

    def _start_worker(self) -> None:
        if self.worker and self.worker.is_running():
            return
        self.worker = AgentWorker(events=self.events)
        self.worker.start()

    def _stop_worker(self) -> None:
        if self.worker:
            self.worker.stop(timeout=3)
            self.worker = None

    # ── Button actions ──────────────────────────────────────────

    def _on_test_print(self) -> None:
        """Imprime una prueba ESC/POS en la impresora default del PC."""
        printers = list_system_printers()
        default = next((p for p in printers if p["is_default"]), None)
        if not default:
            self._popup("Sin impresora",
                        "No hay impresora por defecto en este PC. Configura una en "
                        "Windows → Configuración → Impresoras y vuelve a intentar.")
            return
        # ESC/POS de prueba: init + texto + cortar
        bytes_test = (
            b"\x1b\x40"                    # ESC @ init
            b"\x1b\x61\x01"                # ESC a 1 → centrar
            b"\x1b\x21\x30"                # ESC ! 0x30 → grande+bold
            b"PULSTOCK\n"
            b"\x1b\x21\x00"                # ESC ! 0 → normal
            b"--------------------------------\n"
            b"Prueba de impresion\n"
            b"\n"
            b"Si lees esto, todo OK!\n"
            b"\n\n\n\n"
            b"\x1d\x56\x00"                # GS V 0 → cortar full
        )
        try:
            print_bytes_system(default["name"], bytes_test)
            self._popup("Prueba enviada",
                        f"Mandé la prueba a '{default['name']}'.\n"
                        f"Si no salió nada, revisa que la impresora tenga papel y esté prendida.")
        except Exception as e:
            self._popup("Error", f"No se pudo imprimir:\n\n{e}", error=True)

    def _on_reconnect(self) -> None:
        if self.worker:
            self.worker.stop(timeout=3)
        self._start_worker()
        self.last_event_label.config(text="Reconectando con el servidor…", fg=BRAND_AMBER)

    def _toggle_autostart(self) -> None:
        if is_autostart_enabled():
            disable_autostart()
            self._autostart_btn.config(text="Activar inicio automático")
            self._popup("Inicio automático",
                        "Pulstock ya no se va a iniciar automáticamente.")
        else:
            try:
                enable_autostart()
                self._autostart_btn.config(text="Quitar inicio automático")
                self._popup("Inicio automático",
                            "Listo. Pulstock se va a iniciar automáticamente cada vez "
                            "que prendas este PC.")
            except Exception as e:
                self._popup("Error", f"No se pudo activar:\n\n{e}", error=True)

    def _on_logout(self) -> None:
        if not self._confirm("Cerrar sesión",
                             "Vas a desconectar este PC del panel. "
                             "Tendrás que pedir un código nuevo para volver a conectarlo. "
                             "¿Continuar?"):
            return
        self._stop_worker()
        invalidate_config()
        self._show_pair_window()

    def _on_unauthorized(self) -> None:
        """El server rechazó la api_key — abrir ventana de re-pareo."""
        self._stop_worker()
        invalidate_config()
        self._popup("Sesión cerrada",
                    "El servidor desconectó este PC. Esto suele pasar cuando "
                    "el admin eliminó el agente del panel o regeneró el código. "
                    "Vamos a re-conectarlo ahora.",
                    error=True)
        self._show_pair_window()

    def _on_close_window(self) -> None:
        """Cerrar la X minimiza al tray, NO termina el agente."""
        if self.tray and platform.system() == "Windows":
            self.root.withdraw()
            try:
                self.tray.notify("Pulstock sigue activo en la bandeja del sistema "
                                 "(al lado del reloj).", "Pulstock minimizado")
            except Exception:
                pass
        else:
            # Sin tray (no-Windows): cerrar de verdad
            self._exit_full()

    # ── System tray ─────────────────────────────────────────────

    def _start_tray(self) -> None:
        if self.tray:
            return
        try:
            import pystray
        except ImportError:
            log.warning("pystray no disponible — sin icono de bandeja")
            return

        image = _make_tray_image()

        def _on_show(icon, item):
            if self.root:
                self.root.after(0, self._show_main)

        def _on_test(icon, item):
            if self.root:
                self.root.after(0, self._on_test_print)

        def _on_exit(icon, item):
            self.tray.stop()
            if self.root:
                self.root.after(0, self._exit_full)

        menu = pystray.Menu(
            pystray.MenuItem("Mostrar Pulstock", _on_show, default=True),
            pystray.MenuItem("Imprimir prueba", _on_test),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir del agente", _on_exit),
        )
        self.tray = pystray.Icon("pulstock", image, "Pulstock Printer Agent", menu)

        self.tray_thread = threading.Thread(target=self.tray.run, daemon=True)
        self.tray_thread.start()

    def _show_main(self) -> None:
        if self.root:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

    def _exit_full(self) -> None:
        self._stop_worker()
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
        sys.exit(0)

    # ── Helpers ─────────────────────────────────────────────────

    def _popup(self, title: str, msg: str, error: bool = False) -> None:
        from tkinter import messagebox
        if error:
            messagebox.showerror(title, msg, parent=self.root)
        else:
            messagebox.showinfo(title, msg, parent=self.root)

    def _confirm(self, title: str, msg: str) -> bool:
        from tkinter import messagebox
        return bool(messagebox.askyesno(title, msg, parent=self.root))


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pulstock Printer Agent — bridge entre Pulstock y tus impresoras",
    )
    parser.add_argument("--cli", action="store_true",
                        help="Modo terminal (sin ventana). Útil para servidores Linux/Mac.")
    parser.add_argument("--pair", action="store_true",
                        help="(Solo CLI) Forzar pareo interactivo en terminal.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help=f"URL del API (default: {DEFAULT_API_URL})")
    parser.add_argument("--verbose", action="store_true",
                        help="Logs detallados (DEBUG).")
    parser.add_argument("--version", action="version",
                        version=f"Pulstock Agent {__version__}")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # CLI mode (explicit, o cuando no estamos en Windows y no hay DISPLAY).
    if args.cli or args.pair:
        if args.pair:
            return cmd_pair_cli(args.api_url)
        return cmd_run_cli()

    # GUI mode (default en Windows + Mac + Linux con display).
    # Si Tkinter no está disponible (Linux server), caemos a CLI.
    try:
        import tkinter  # noqa: F401
    except ImportError:
        log.warning("Tkinter no disponible — corriendo en modo CLI")
        return cmd_run_cli()

    try:
        gui = PulstockAgentGUI()
        return gui.run()
    except Exception as e:
        log.exception("GUI falló: %s — fallback a CLI", e)
        return cmd_run_cli()


if __name__ == "__main__":
    sys.exit(main())
