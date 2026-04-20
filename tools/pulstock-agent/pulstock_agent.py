#!/usr/bin/env python3
"""
Pulstock Printer Agent
======================
Agente liviano que corre en el PC del local, enlaza impresoras locales
(USB, sistema o LAN) y ejecuta trabajos de impresión recibidos desde la
nube de Pulstock.

Uso:
    # Primera vez (emparejar con Pulstock)
    python pulstock_agent.py --pair

    # Corriendo normalmente
    python pulstock_agent.py

    # Con URL custom (testing)
    python pulstock_agent.py --api-url http://localhost:8000/api

Requisitos: Python 3.8+ y los paquetes de requirements.txt
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import platform
import signal
import socket
import sys
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

__version__ = "1.0.0"

# ─── Config ──────────────────────────────────────────────────────────────

DEFAULT_API_URL = os.environ.get("PULSTOCK_API_URL", "http://65.108.148.200/api")
DEFAULT_POLL_INTERVAL = 3  # seconds between polls when idle
DEFAULT_ERROR_BACKOFF = 10  # seconds to wait after an error

CONFIG_DIR = Path.home() / ".pulstock_agent"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "agent.log"

# ─── Logging ─────────────────────────────────────────────────────────────

def _setup_logging(verbose: bool = False) -> logging.Logger:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)s: %(message)s"
    logging.basicConfig(
        level=level, format=fmt,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
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
    # chmod 0o600 en POSIX — evita que otras cuentas del mismo PC lean
    # la api_key. En Windows os.chmod es no-op (ACLs manejan esto).
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass
    log.debug("Config guardada en %s", CONFIG_FILE)


# ─── HTTP helpers ────────────────────────────────────────────────────────

def http_json(method: str, url: str, data: dict | None = None,
              headers: dict | None = None, timeout: int = 30) -> tuple[int, dict]:
    """Simple HTTP JSON client using stdlib (no external deps)."""
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
                # Mark default
                default = win32print.GetDefaultPrinter()
                for p in out:
                    if p["name"] == default:
                        p["is_default"] = True
                        break
            except ImportError:
                log.warning("win32print no instalado — usa `pip install pywin32`")
        elif system in ("Darwin", "Linux"):
            import subprocess
            result = subprocess.run(
                ["lpstat", "-p"], capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("printer "):
                    name = line.split()[1]
                    out.append({
                        "name": name,
                        "display_name": name,
                        "connection_type": "system",
                        "paper_width": 80,
                        "is_default": False,
                    })
            # Default
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
    """Print raw ESC/POS bytes to a system printer."""
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
        import subprocess
        # Defensa en profundidad: aunque el server valida printer_name,
        # rechazamos localmente cualquier cosa que empiece con "-" (flag)
        if printer_name.startswith("-"):
            raise RuntimeError(f"printer_name inválido: {printer_name!r}")
        proc = subprocess.Popen(
            ["lp", "-d", printer_name, "-o", "raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            out, err = proc.communicate(data, timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("lp timeout (>30s) imprimiendo")
        if proc.returncode != 0:
            err_txt = (err or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"lp exited with {proc.returncode}: {err_txt or '(sin stderr)'}")
    else:
        raise RuntimeError(f"OS no soportado: {system}")


def print_bytes_network(address: str, data: bytes) -> None:
    """Print to network printer via TCP 9100 (ESC/POS raw)."""
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


# ─── Commands ────────────────────────────────────────────────────────────

def cmd_pair(api_url: str) -> int:
    """Interactive pairing: user enters code, agent saves api_key."""
    print("\n" + "=" * 60)
    print("  PULSTOCK PRINTER AGENT — Emparejamiento")
    print("=" * 60)
    print()
    print("Pídele al administrador de Pulstock que cree un agente para este")
    print("PC desde: Configuración → Impresoras → Agregar agente PC")
    print()
    print("Él te entregará un código de 8 caracteres (ej: ABCD-1234).")
    print()

    code = input("Ingresa el código de emparejamiento: ").strip().upper()
    if not code:
        print("✗ Código vacío. Abortando.")
        return 1

    os_info = f"{platform.system()} {platform.release()}"
    status, resp = http_json("POST", f"{api_url}/printing/agents/pair/", data={
        "pairing_code": code,
        "version": __version__,
        "os_info": os_info,
    })

    if status != 200:
        print(f"\n✗ Error emparejando: {resp.get('detail', 'Código inválido')}")
        return 1

    cfg = {
        "api_url": api_url,
        "api_key": resp["api_key"],
        "agent_id": resp["agent_id"],
        "agent_name": resp["agent_name"],
        "tenant_name": resp["tenant_name"],
        "poll_interval": resp.get("poll_interval_seconds", DEFAULT_POLL_INTERVAL),
    }
    save_config(cfg)

    print()
    print("=" * 60)
    print(f"  ✓ Emparejado exitosamente")
    print("=" * 60)
    print(f"  Agente:  {cfg['agent_name']}")
    print(f"  Tenant:  {cfg['tenant_name']}")
    print(f"  Config:  {CONFIG_FILE}")
    print()
    print("Ahora puedes correr el agente sin argumentos para empezar:")
    print("    python pulstock_agent.py")
    return 0


def cmd_run() -> int:
    """Main loop: report printers, poll for jobs, print, repeat."""
    cfg = load_config()
    if not cfg.get("api_key"):
        print("✗ Agente no emparejado. Corre con --pair primero.")
        return 1

    api_url = cfg["api_url"]
    api_key = cfg["api_key"]
    poll_interval = cfg.get("poll_interval", DEFAULT_POLL_INTERVAL)

    log.info("Pulstock Printer Agent v%s iniciando", __version__)
    log.info("Agente: %s (tenant=%s)", cfg["agent_name"], cfg["tenant_name"])
    log.info("API: %s", api_url)

    # Report printers on startup
    _report_printers(api_url, api_key)

    # Graceful shutdown
    _running = {"v": True}
    def _shutdown(signum, frame):
        log.info("Señal recibida, deteniendo...")
        _running["v"] = False
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    last_printers_report = time.time()
    PRINTERS_REPORT_INTERVAL = 300  # re-scan printers every 5 min

    while _running["v"]:
        try:
            # Re-report printers periodically (in case user added new ones)
            if time.time() - last_printers_report > PRINTERS_REPORT_INTERVAL:
                _report_printers(api_url, api_key)
                last_printers_report = time.time()

            # Poll for jobs
            status, resp = http_json(
                "GET", f"{api_url}/printing/agents/poll/?key={api_key}",
                timeout=15,
            )
            if status != 200:
                if status == 401:
                    log.error("API key rechazada — el agente fue eliminado del panel. Saliendo.")
                    return 1
                log.warning("Poll falló: status=%s resp=%s", status, resp)
                time.sleep(DEFAULT_ERROR_BACKOFF)
                continue

            job = resp.get("job")
            if not job:
                time.sleep(poll_interval)
                continue

            # Process the job
            _process_job(api_url, api_key, job)

        except Exception as e:
            log.exception("Error en loop principal: %s", e)
            time.sleep(DEFAULT_ERROR_BACKOFF)

    log.info("Agente detenido.")
    return 0


def _report_printers(api_url: str, api_key: str) -> None:
    printers = list_system_printers()
    log.info("Impresoras detectadas: %d", len(printers))
    for p in printers:
        log.info("  - %s (default=%s)", p["name"], p["is_default"])

    status, resp = http_json(
        "POST", f"{api_url}/printing/agents/printers/?key={api_key}",
        data={"printers": printers},
    )
    if status == 200:
        log.info("Impresoras reportadas correctamente")
    else:
        log.warning("Error reportando impresoras: status=%s resp=%s", status, resp)


def _process_job(api_url: str, api_key: str, job: dict) -> None:
    job_id = job["id"]
    printer_name = (job.get("printer_name") or "").strip()
    data_b64 = job.get("data_b64") or ""
    html = job.get("html") or ""

    log.info(
        "Job #%s recibido (printer=%r, bytes=%d, html_len=%d, source=%s)",
        job_id, printer_name, len(data_b64) * 3 // 4, len(html), job.get("source"),
    )

    # Find target printer
    if not printer_name:
        printers = list_system_printers()
        default = next((p for p in printers if p["is_default"]), None)
        if default:
            printer_name = default["name"]

    if not printer_name:
        _report_result(api_url, api_key, job_id, False, "No hay impresora configurada")
        return

    try:
        if data_b64:
            raw = base64.b64decode(data_b64)
            print_bytes_system(printer_name, raw)
        elif html:
            # HTML via system → not implemented yet in agent; request future
            raise NotImplementedError("Impresión HTML no implementada aún; envía ESC/POS bytes")
        else:
            raise ValueError("Job sin payload (data_b64 o html)")

        log.info("Job #%s impreso correctamente", job_id)
        _report_result(api_url, api_key, job_id, True, "")
    except Exception as e:
        log.exception("Error imprimiendo job #%s", job_id)
        _report_result(api_url, api_key, job_id, False, str(e))


def _report_result(api_url: str, api_key: str, job_id: int,
                   success: bool, error: str) -> None:
    body = {"success": success}
    if error:
        body["error"] = error
    status, _ = http_json(
        "POST", f"{api_url}/printing/jobs/{job_id}/complete/?key={api_key}",
        data=body,
    )
    if status != 200:
        log.warning("Error reportando resultado: status=%s", status)


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Pulstock Printer Agent")
    parser.add_argument("--pair", action="store_true",
                        help="Emparejar con Pulstock (primera vez)")
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help=f"URL base del API (default: {DEFAULT_API_URL})")
    parser.add_argument("--verbose", action="store_true",
                        help="Logs en modo debug")
    parser.add_argument("--version", action="version",
                        version=f"Pulstock Agent {__version__}")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.pair:
        return cmd_pair(args.api_url)
    return cmd_run()


if __name__ == "__main__":
    sys.exit(main())
