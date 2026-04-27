"""
Printing agent HTTP endpoints.

Endpoints público-de-agente (autenticación por api_key en header o query):
  POST /api/printing/agents/pair/       → agent canjea pairing_code → api_key
  GET  /api/printing/agents/poll/       → agent busca próximo job
  POST /api/printing/agents/printers/   → agent reporta sus impresoras
  POST /api/printing/jobs/<id>/complete/→ agent reporta resultado

Endpoints de usuario (JWT auth normal):
  POST /api/printing/agents/            → crea nuevo agente + pairing_code
  GET  /api/printing/agents/            → lista agentes del tenant
  DELETE /api/printing/agents/<id>/     → eliminar agente
  POST /api/printing/jobs/queue/        → encolar un print job
"""
from __future__ import annotations

import base64
import logging
import re

from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView


class AgentPairThrottle(AnonRateThrottle):
    """Throttle separado para el endpoint de pair. Si alguien intenta hacer
    brute-force de códigos de emparejado, lo bloquea tras 20 intentos/hora
    por IP."""
    scope = "agent_pair"


class AgentPollThrottle(AnonRateThrottle):
    """Throttle para poll del agente — protege contra agente defectuoso
    que pollea en bucle sin delay."""
    scope = "agent_poll"

# printer_name debe ser un nombre "seguro" — sin guiones iniciales (evita flags
# tipo `lp -d -oraw`), sin caracteres de control.
_PRINTER_NAME_RE = re.compile(r"^[A-Za-z0-9 _\-\.\(\)\#/]{1,150}$")

def _is_safe_printer_name(name: str) -> bool:
    if not name:
        return True  # vacío = usar default (permitido)
    if name.startswith("-"):
        return False
    return bool(_PRINTER_NAME_RE.match(name))


# network_address: solo IPv4/hostname con puerto opcional. Bloquea inyección
# de shell, paths, IPv6 raros, etc. Formato: "host[:port]" donde:
#   - host = letras/dígitos/guiones/puntos (1-100 chars)
#   - port = 1-65535 (opcional, default 9100)
_NETWORK_ADDR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-\.]{0,99}(?::([1-9]\d{0,4}))?$")

def _is_safe_network_address(addr: str) -> bool:
    if not addr:
        return True  # vacío = OK (no es impresora de red)
    m = _NETWORK_ADDR_RE.match(addr)
    if not m:
        return False
    if m.group(1):  # tiene puerto explícito
        port = int(m.group(1))
        if not (1 <= port <= 65535):
            return False
    return True

# Whitelist de orígenes válidos para PrintJob.source (evita basura en DB)
_VALID_JOB_SOURCES = {"pos", "mesa", "manual", "test", "web", "api", "receipt", "precuenta", "comanda", ""}

# Límite de agentes activos por tenant (anti-abuso + UX razonable)
MAX_AGENTS_PER_TENANT = 20

from core.permissions import HasTenant, IsManager
from .models import AgentPrinter, PrintAgent, PrintJob, PrintStation

logger = logging.getLogger(__name__)


# ─── Auth helpers ────────────────────────────────────────────────

def _resolve_agent_by_key(request) -> PrintAgent | None:
    """Get agent from X-Agent-Key header or ?key=... query param."""
    key = request.headers.get("X-Agent-Key") or request.GET.get("key") or ""
    key = key.strip()
    if not key or len(key) < 20:
        return None
    return PrintAgent.objects.filter(api_key=key, is_active=True).first()


# ═══════════════════════════════════════════════════════════════════
# USER-FACING ENDPOINTS (JWT auth)
# ═══════════════════════════════════════════════════════════════════


class AgentListCreateView(APIView):
    """
    GET  /api/printing/agents/
         Lista agentes del tenant (owner/manager).
    POST /api/printing/agents/
         Body: { "name": "PC Caja Principal", "store_id": 1 (optional) }
         Crea un nuevo agente con pairing_code.
         Devuelve el pairing_code (solo 1 vez) para que el user lo ingrese
         en el software del agente.
    """

    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    def get(self, request):
        qs = PrintAgent.objects.filter(
            tenant_id=request.user.tenant_id,
            is_active=True,
        ).prefetch_related("printers").order_by("-created_at")
        return Response([
            {
                "id": a.pk,
                "name": a.name,
                "store_id": a.store_id,
                "is_active": a.is_active,
                "is_online": a.is_online,
                "is_pairing_pending": a.is_pairing_pending,
                "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
                "version": a.version,
                "os_info": a.os_info,
                "created_at": a.created_at.isoformat(),
                "printers_count": sum(1 for p in a.printers.all() if p.is_active),
                "printers": [
                    {
                        "id": p.pk,
                        "name": p.name,
                        "display_name": p.display_name,
                        "connection_type": p.connection_type,
                        "paper_width": p.paper_width,
                        "network_address": p.network_address,
                        "is_default": p.is_default,
                        # station_id permite al frontend mostrar a qué estación
                        # está asignada cada impresora sin un fetch adicional.
                        "station_id": p.station_id,
                    }
                    for p in a.printers.all() if p.is_active
                ],
            }
            for a in qs
        ])

    def post(self, request):
        name = (request.data.get("name") or "").strip()[:100]
        if not name:
            return Response({"detail": "El nombre es obligatorio."}, status=400)

        # Cap de agentes activos por tenant — anti-abuso
        active_count = PrintAgent.objects.filter(
            tenant_id=request.user.tenant_id, is_active=True,
        ).count()
        if active_count >= MAX_AGENTS_PER_TENANT:
            return Response(
                {"detail": f"Máximo {MAX_AGENTS_PER_TENANT} agentes por cuenta. "
                           "Elimina alguno antes de crear uno nuevo."},
                status=400,
            )

        store_id = request.data.get("store_id") or None

        # Optional: verify store belongs to tenant
        if store_id:
            from stores.models import Store
            if not Store.objects.filter(
                id=store_id, tenant_id=request.user.tenant_id,
            ).exists():
                return Response({"detail": "Local inválido."}, status=400)

        agent = PrintAgent.objects.create(
            tenant_id=request.user.tenant_id,
            store_id=store_id,
            name=name,
        )
        code = agent.generate_pairing_code()
        logger.info("Agent created: id=%d tenant=%d", agent.pk, request.user.tenant_id)

        return Response({
            "id": agent.pk,
            "name": agent.name,
            "pairing_code": code,
            "pairing_expires_at": agent.pairing_code_expires_at.isoformat(),
            "instructions": (
                "1. Descarga el Pulstock Printer Agent en el PC del local\n"
                "2. Ejecuta el instalador\n"
                "3. Cuando pida el código, escribe: " + code
            ),
        }, status=201)


class AgentDetailView(APIView):
    """DELETE /api/printing/agents/<id>/ → soft-delete (desactiva)"""

    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    def delete(self, request, pk):
        agent = get_object_or_404(
            PrintAgent, pk=pk, tenant_id=request.user.tenant_id,
        )
        agent.is_active = False
        agent.save(update_fields=["is_active"])
        # Cancela cualquier job pendiente/en curso — evita huérfanos que
        # quedan vivos para siempre si el agente desaparece.
        PrintJob.objects.filter(
            agent=agent,
            status__in=[PrintJob.STATUS_PENDING, PrintJob.STATUS_PRINTING],
        ).update(
            status=PrintJob.STATUS_CANCELLED,
            completed_at=timezone.now(),
            error_msg="Agente eliminado",
        )
        # Desactiva AgentPrinters del agente — para que no sigan apareciendo
        # en listados si alguien olvidó filtrar por agent.is_active
        AgentPrinter.objects.filter(agent=agent).update(is_active=False)
        return Response(status=204)


class AgentRegenerateCodeView(APIView):
    """POST /api/printing/agents/<id>/regenerate-code/ → nuevo pairing code"""

    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    def post(self, request, pk):
        agent = get_object_or_404(
            PrintAgent, pk=pk, tenant_id=request.user.tenant_id,
        )
        code = agent.generate_pairing_code()
        return Response({
            "pairing_code": code,
            "pairing_expires_at": agent.pairing_code_expires_at.isoformat(),
        })


class AutoPrintView(APIView):
    """
    POST /api/printing/print/
    Body: { "data_b64": "...", "html": "...", "source": "pos" }

    Endpoint "fácil" para el frontend. Encola el job en el primer agente
    online del tenant (priorizando el de la tienda activa del usuario, si
    aplica), eligiendo su impresora por defecto.

    Pensado para que celulares/tablets puedan imprimir sin tener que
    seleccionar manualmente un agente y una impresora — el flujo típico
    en un local con un único PC con impresora térmica conectada.

    Devuelve:
      201 + {job_id, agent_name, printer_name}  → encolado OK
      404 + {detail}                            → no hay agente disponible
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request):
        data_b64 = (request.data.get("data_b64") or "").strip()
        html = (request.data.get("html") or "").strip()
        if not data_b64 and not html:
            return Response(
                {"detail": "data_b64 o html requerido."}, status=400,
            )

        # Validar tamaño del payload
        if data_b64:
            try:
                raw = base64.b64decode(data_b64, validate=True)
                if len(raw) > 200_000:
                    return Response({"detail": "Payload demasiado grande."}, status=400)
            except Exception:
                return Response({"detail": "data_b64 inválido."}, status=400)
        if html and len(html) > 100_000:
            return Response({"detail": "HTML demasiado grande."}, status=400)

        source = (request.data.get("source") or "")[:30].lower()
        if source not in _VALID_JOB_SOURCES:
            source = "api"

        # Estación opcional: si viene, rutea a impresoras de esa estación.
        station_id = request.data.get("station_id")
        station = None
        if station_id not in (None, "", 0):
            try:
                station = PrintStation.objects.get(
                    pk=int(station_id),
                    tenant_id=request.user.tenant_id,
                    is_active=True,
                )
            except (PrintStation.DoesNotExist, ValueError, TypeError):
                return Response(
                    {"detail": "station_id inválido o estación inactiva."},
                    status=400,
                )

        # Buscar agente online: prioridad por store activa del user, después
        # cualquier agente del tenant. "Online" = polleó en los últimos 2 min.
        from datetime import timedelta
        online_cutoff = timezone.now() - timedelta(seconds=120)
        agents_qs = PrintAgent.objects.filter(
            tenant_id=request.user.tenant_id,
            is_active=True,
            paired_at__isnull=False,
            last_seen_at__gt=online_cutoff,
        )

        # Si se pidió estación: buscar impresora online asignada a ella.
        # NO hacemos fallback automático a otra estación porque imprimir
        # un ticket de cocina en la barra rompe el flujo de trabajo.
        if station is not None:
            station_printers = (
                AgentPrinter.objects.filter(
                    station=station,
                    is_active=True,
                    agent__is_active=True,
                    agent__paired_at__isnull=False,
                    agent__last_seen_at__gt=online_cutoff,
                )
                .select_related("agent")
                .order_by("-is_default", "id")
            )
            ap = station_printers.first()
            if ap is None:
                any_assigned = AgentPrinter.objects.filter(
                    station=station, is_active=True,
                ).exists()
                if not any_assigned:
                    return Response({
                        "detail": (
                            f"La estación '{station.name}' no tiene impresoras "
                            "asignadas. Asigna al menos una en Configuración → Impresoras."
                        ),
                    }, status=404)
                return Response({
                    "detail": (
                        f"No hay impresoras online en la estación '{station.name}'. "
                        "Verifica que el PC con esa impresora esté encendido y conectado."
                    ),
                }, status=404)
            agent = ap.agent
            logger.info(
                "AutoPrint(station=%s): job will go to agent=%s printer=%s",
                station.name, agent.name, ap.name,
            )
        else:
            active_store_id = getattr(request.user, "active_store_id", None)
            agent = None
            if active_store_id:
                agent = agents_qs.filter(store_id=active_store_id).first()
            if agent is None:
                agent = agents_qs.first()

            if agent is None:
                return Response({
                    "detail": (
                        "No hay agentes de impresión conectados. Instala el "
                        "Pulstock Printer Agent en el PC del local o "
                        "configura una impresora local en este dispositivo."
                    ),
                }, status=404)

            ap_qs = AgentPrinter.objects.filter(agent=agent, is_active=True)
            ap = ap_qs.filter(is_default=True).first() or ap_qs.first()
            if ap is None:
                return Response({
                    "detail": (
                        f"El agente '{agent.name}' no tiene impresoras "
                        "configuradas. Verifica que el PC tenga al menos "
                        "una impresora instalada."
                    ),
                }, status=404)

        job = PrintJob.objects.create(
            tenant_id=request.user.tenant_id,
            agent=agent,
            printer_name=ap.name,
            data_b64=data_b64,
            html=html,
            source=source,
            created_by=request.user,
        )
        logger.info(
            "AutoPrint: job=#%d agent=%s printer=%s user=%d",
            job.pk, agent.name, ap.name, request.user.pk,
        )
        return Response({
            "job_id": job.pk,
            "agent_name": agent.name,
            "agent_id": agent.pk,
            "printer_name": ap.display_name or ap.name,
            "connection_type": ap.connection_type,
        }, status=201)


class JobQueueView(APIView):
    """
    POST /api/printing/jobs/queue/
    Body: {
        "agent_id": 1,
        "printer_name": "EPSON TM-T20III" (optional, usa default si vacío),
        "data_b64": "<base64 ESC/POS>" | "html": "<html>...",
        "source": "pos"  (optional)
    }
    Encola un trabajo para que el agente lo imprima.
    """

    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request):
        agent_id = request.data.get("agent_id")
        if not agent_id:
            return Response({"detail": "agent_id requerido."}, status=400)

        try:
            agent = PrintAgent.objects.get(
                pk=int(agent_id),
                tenant_id=request.user.tenant_id,
                is_active=True,
            )
        except (PrintAgent.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Agente no encontrado."}, status=404)

        data_b64 = (request.data.get("data_b64") or "").strip()
        html = (request.data.get("html") or "").strip()
        if not data_b64 and not html:
            return Response({"detail": "data_b64 o html requerido."}, status=400)

        # Validate data_b64 format if provided
        if data_b64:
            try:
                raw = base64.b64decode(data_b64, validate=True)
                if len(raw) > 200_000:
                    return Response({"detail": "Payload demasiado grande."}, status=400)
            except Exception:
                return Response({"detail": "data_b64 inválido."}, status=400)

        # Bound HTML payload (evita llenar la DB con MB de HTML)
        if html and len(html) > 100_000:
            return Response({"detail": "HTML demasiado grande."}, status=400)

        # Sanitizar printer_name — evita flags maliciosas hacia lp/lpr en Linux
        printer_name = (request.data.get("printer_name") or "").strip()[:150]
        if not _is_safe_printer_name(printer_name):
            return Response(
                {"detail": "printer_name contiene caracteres inválidos."},
                status=400,
            )

        # Whitelist de source — si vienen cosas raras, las descartamos
        source = (request.data.get("source") or "")[:30].lower()
        if source not in _VALID_JOB_SOURCES:
            source = "api"

        # Rechazar si el agente está offline (no polleó en >2min). Antes
        # encolábamos y el job se quedaba pendiente para siempre — el user
        # apretaba "imprimir" y nunca salía nada. Mejor avisar al toque.
        # Permitimos `force=true` para casos en que el caller QUIERE que se
        # quede encolado igual (raro, pero útil para schedule).
        # IMPORTANTE: este check va DESPUÉS de las validaciones de input
        # (data_b64, printer_name, etc.) para que un payload mal-formado
        # siempre se rechace con 400 independiente del estado del agente.
        force = bool(request.data.get("force"))
        if not agent.is_online and not force:
            return Response({
                "detail": (
                    f"El PC '{agent.name}' está desconectado. "
                    "Asegúrate de que esté encendido y con internet, después "
                    "vuelve a presionar Imprimir."
                ),
                "code": "agent_offline",
            }, status=503)

        job = PrintJob.objects.create(
            tenant_id=request.user.tenant_id,
            agent=agent,
            printer_name=printer_name,
            data_b64=data_b64,
            html=html,
            source=source,
            created_by=request.user,
        )
        logger.info(
            "Job queued: #%d agent=%d user=%d source=%s",
            job.pk, agent.pk, request.user.pk, job.source,
        )
        return Response({"id": job.pk, "status": job.status}, status=201)


# ═══════════════════════════════════════════════════════════════════
# AGENT-FACING ENDPOINTS (api_key auth)
# ═══════════════════════════════════════════════════════════════════


class AgentPairView(APIView):
    """
    POST /api/printing/agents/pair/
    Body: { "pairing_code": "ABCD-1234", "version": "1.0.0", "os_info": "Windows 11" }
    Exchange a short pairing code for a long-lived api_key.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AgentPairThrottle]

    def post(self, request):
        code = (request.data.get("pairing_code") or "").strip().upper()
        version = (request.data.get("version") or "")[:20]
        os_info = (request.data.get("os_info") or "")[:100]

        if not code:
            return Response({"detail": "pairing_code requerido."}, status=400)

        agent = PrintAgent.objects.filter(
            pairing_code=code,
            is_active=True,
            pairing_code_expires_at__gt=timezone.now(),
            paired_at__isnull=True,
        ).first()

        if not agent:
            return Response(
                {"detail": "Código inválido o expirado."},
                status=404,
            )

        agent.version = version
        agent.os_info = os_info
        agent.save(update_fields=["version", "os_info"])
        agent.mark_paired()
        agent.touch()

        logger.info("Agent paired: id=%d version=%s os=%s", agent.pk, version, os_info)
        return Response({
            "api_key": agent.api_key,
            "agent_id": agent.pk,
            "agent_name": agent.name,
            "tenant_name": agent.tenant.name,
            "poll_interval_seconds": 3,
        })


class AgentPollView(APIView):
    """
    GET /api/printing/agents/poll/?key=<api_key>
    Returns the next pending print job for this agent, or {}.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AgentPollThrottle]

    def get(self, request):
        agent = _resolve_agent_by_key(request)
        if not agent:
            return Response({"detail": "api_key inválida."}, status=401)

        agent.touch()

        # (El cleanup de jobs terminales >30d ya lo hace Celery beat
        # en printing.tasks.cleanup_old_jobs — corre diario 03:30.)

        # Watchdog: jobs que quedaron en "printing" por >60s (agente crasheó
        # entre poll y complete) → devolverlos a pending para reintento.
        from datetime import timedelta
        stale_cutoff = timezone.now() - timedelta(seconds=60)
        PrintJob.objects.filter(
            agent=agent,
            status=PrintJob.STATUS_PRINTING,
            picked_at__lt=stale_cutoff,
            retry_count__lt=3,
        ).update(
            status=PrintJob.STATUS_PENDING,
            picked_at=None,
            retry_count=models.F("retry_count") + 1,
        )
        # Jobs con retry_count >=3 se marcan failed definitivamente.
        PrintJob.objects.filter(
            agent=agent,
            status=PrintJob.STATUS_PRINTING,
            picked_at__lt=stale_cutoff,
            retry_count__gte=3,
        ).update(
            status=PrintJob.STATUS_FAILED,
            completed_at=timezone.now(),
            error_msg="Agente no completó el trabajo tras 3 reintentos",
        )

        # Claim next pending job (FIFO) — con retry si otro proceso lo robó.
        # El UPDATE ... WHERE status=PENDING es atómico a nivel de fila.
        job = None
        for _ in range(5):  # hasta 5 candidatos
            candidate = PrintJob.objects.filter(
                agent=agent, status=PrintJob.STATUS_PENDING,
            ).order_by("created_at").first()
            if not candidate:
                return Response({"job": None})
            updated = PrintJob.objects.filter(
                pk=candidate.pk, status=PrintJob.STATUS_PENDING,
            ).update(
                status=PrintJob.STATUS_PRINTING,
                picked_at=timezone.now(),
            )
            if updated:
                job = candidate
                break
            # otro poll lo tomó — prueba con el siguiente
        if not job:
            return Response({"job": None})
        job.refresh_from_db()

        # Buscar la AgentPrinter asociada al printer_name del job para que el
        # agente sepa cómo imprimir (system / network / usb). Si printer_name
        # está vacío, usar la default del agente.
        connection_type = "system"
        network_address = ""
        ap_qs = AgentPrinter.objects.filter(agent=agent, is_active=True)
        if job.printer_name:
            ap = ap_qs.filter(name=job.printer_name).first()
        else:
            ap = ap_qs.filter(is_default=True).first() or ap_qs.first()
        if ap:
            connection_type = ap.connection_type or "system"
            network_address = ap.network_address or ""

        return Response({
            "job": {
                "id": job.pk,
                "printer_name": job.printer_name,
                "data_b64": job.data_b64,
                "html": job.html,
                "source": job.source,
                # NUEVO: el agente usa estos campos para decidir si imprimir
                # vía API del sistema o vía socket TCP a la IP de la impresora.
                "connection_type": connection_type,
                "network_address": network_address,
            }
        })


class AgentPrintersView(APIView):
    """
    POST /api/printing/agents/printers/?key=<api_key>
    Body: {
        "printers": [
            {
                "name": "EPSON TM-T20III",
                "display_name": "Caja Principal",
                "connection_type": "system",
                "paper_width": 80,
                "network_address": "",
                "is_default": true
            }, ...
        ]
    }
    Agent replaces its printer list every time it starts up.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        agent = _resolve_agent_by_key(request)
        if not agent:
            return Response({"detail": "api_key inválida."}, status=401)

        agent.touch()
        printers_data = request.data.get("printers") or []
        if not isinstance(printers_data, list):
            return Response({"detail": "'printers' debe ser una lista."}, status=400)

        # Replace strategy: mark all inactive, then upsert
        AgentPrinter.objects.filter(agent=agent).update(is_active=False)

        saved = []
        for p in printers_data:
            if not isinstance(p, dict):
                continue
            name = (p.get("name") or "").strip()
            if not name:
                continue
            ct = (p.get("connection_type") or "system").strip()
            if ct not in {"system", "usb", "network"}:
                ct = "system"
            paper_width = p.get("paper_width") or 80
            try:
                paper_width = int(paper_width)
                if paper_width not in (58, 80):
                    paper_width = 80
            except (ValueError, TypeError):
                paper_width = 80

            # Sanitizar network_address (anti-injection, defensa en profundidad).
            # Si la impresora dice ser network pero la IP es inválida, la
            # marcamos como system (caería al spooler local del agente).
            net_addr = (p.get("network_address") or "").strip()[:100]
            if not _is_safe_network_address(net_addr):
                logger.warning(
                    "Agent %d intentó registrar network_address inválido: %r — ignorado",
                    agent.pk, net_addr,
                )
                net_addr = ""
                if ct == "network":
                    ct = "system"  # downgrade: sin IP válida no puede usar TCP

            obj, _ = AgentPrinter.objects.update_or_create(
                agent=agent, name=name,
                defaults={
                    "display_name": (p.get("display_name") or "")[:150],
                    "paper_width": paper_width,
                    "connection_type": ct,
                    "network_address": net_addr,
                    "is_default": bool(p.get("is_default")),
                    "is_active": True,
                },
            )
            saved.append(obj.pk)

        # Ensure at most one is_default per agent
        defaults = AgentPrinter.objects.filter(agent=agent, is_active=True, is_default=True)
        if defaults.count() > 1:
            first = defaults.first()
            AgentPrinter.objects.filter(agent=agent, is_default=True).exclude(pk=first.pk).update(is_default=False)

        return Response({"ok": True, "count": len(saved)})


class JobCompleteView(APIView):
    """
    POST /api/printing/jobs/<id>/complete/?key=<api_key>
    Body: { "success": true } | { "success": false, "error": "..." }
    Agent reports job result.
    """

    permission_classes = [AllowAny]

    def post(self, request, pk):
        agent = _resolve_agent_by_key(request)
        if not agent:
            return Response({"detail": "api_key inválida."}, status=401)

        agent.touch()

        try:
            job = PrintJob.objects.get(pk=pk, agent=agent)
        except PrintJob.DoesNotExist:
            return Response({"detail": "Job no encontrado."}, status=404)

        if job.status in (PrintJob.STATUS_DONE, PrintJob.STATUS_FAILED, PrintJob.STATUS_CANCELLED):
            # Idempotent — job already completed
            return Response({"ok": True, "detail": "already completed"})

        success = bool(request.data.get("success"))
        if success:
            job.mark_done()
        else:
            err = (request.data.get("error") or "")[:500]
            job.mark_failed(err)

        return Response({"ok": True, "status": job.status})


# ═══════════════════════════════════════════════════════════════════
# PRINT STATIONS (estaciones de impresión)
# ═══════════════════════════════════════════════════════════════════

_STATION_NAME_RE = re.compile(r"^[\w \-\.\(\)/áéíóúÁÉÍÓÚñÑüÜ]{1,100}$")


def _is_safe_station_name(name: str) -> bool:
    return bool(name) and bool(_STATION_NAME_RE.match(name))


class PrintStationListCreateView(APIView):
    """GET /api/printing/stations/ — lista, POST — crea."""
    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    def get(self, request):
        qs = PrintStation.objects.filter(
            tenant_id=request.user.tenant_id, is_active=True,
        ).prefetch_related("printers__agent").order_by("sort_order", "name")

        return Response([
            {
                "id": s.pk,
                "name": s.name,
                "is_default_for_receipts": s.is_default_for_receipts,
                "sort_order": s.sort_order,
                "printers": [
                    {
                        "id": p.pk, "name": p.name,
                        "display_name": p.display_name,
                        "agent_id": p.agent_id,
                        "agent_name": p.agent.name if p.agent_id else "",
                        "agent_online": p.agent.is_online if p.agent_id else False,
                        "connection_type": p.connection_type,
                        "paper_width": p.paper_width,
                    }
                    for p in s.printers.all() if p.is_active
                ],
            }
            for s in qs
        ])

    def post(self, request):
        name = (request.data.get("name") or "").strip()[:100]
        if not _is_safe_station_name(name):
            return Response({"detail": "Nombre inválido. Usa solo letras, números, espacios y guiones."}, status=400)

        active_count = PrintStation.objects.filter(
            tenant_id=request.user.tenant_id, is_active=True,
        ).count()
        if active_count >= 30:
            return Response({"detail": "Máximo 30 estaciones por cuenta. Elimina alguna antes de crear una nueva."}, status=400)

        is_default = bool(request.data.get("is_default_for_receipts"))
        if is_default:
            PrintStation.objects.filter(
                tenant_id=request.user.tenant_id,
                is_default_for_receipts=True,
            ).update(is_default_for_receipts=False)

        try:
            station = PrintStation.objects.create(
                tenant_id=request.user.tenant_id,
                name=name,
                is_default_for_receipts=is_default,
                sort_order=int(request.data.get("sort_order") or 0),
            )
        except Exception:
            return Response({"detail": f"Ya existe una estación con el nombre '{name}'."}, status=409)

        return Response({
            "id": station.pk,
            "name": station.name,
            "is_default_for_receipts": station.is_default_for_receipts,
            "sort_order": station.sort_order,
        }, status=201)


class PrintStationDetailView(APIView):
    """PATCH/DELETE /api/printing/stations/<id>/"""
    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    def patch(self, request, pk):
        station = get_object_or_404(
            PrintStation, pk=pk, tenant_id=request.user.tenant_id, is_active=True,
        )

        if "name" in request.data:
            name = (request.data.get("name") or "").strip()[:100]
            if not _is_safe_station_name(name):
                return Response({"detail": "Nombre inválido."}, status=400)
            if name != station.name:
                exists = PrintStation.objects.filter(
                    tenant_id=request.user.tenant_id, name=name, is_active=True,
                ).exclude(pk=station.pk).exists()
                if exists:
                    return Response({"detail": f"Ya existe una estación con el nombre '{name}'."}, status=409)
            station.name = name

        if "sort_order" in request.data:
            try:
                station.sort_order = int(request.data.get("sort_order") or 0)
            except (ValueError, TypeError):
                return Response({"detail": "sort_order debe ser un número."}, status=400)

        if "is_default_for_receipts" in request.data:
            new_default = bool(request.data.get("is_default_for_receipts"))
            if new_default and not station.is_default_for_receipts:
                PrintStation.objects.filter(
                    tenant_id=request.user.tenant_id,
                    is_default_for_receipts=True,
                ).exclude(pk=station.pk).update(is_default_for_receipts=False)
            station.is_default_for_receipts = new_default

        station.save()
        return Response({
            "id": station.pk,
            "name": station.name,
            "is_default_for_receipts": station.is_default_for_receipts,
            "sort_order": station.sort_order,
        })

    def delete(self, request, pk):
        station = get_object_or_404(
            PrintStation, pk=pk, tenant_id=request.user.tenant_id, is_active=True,
        )
        station.is_active = False
        station.is_default_for_receipts = False
        station.save(update_fields=["is_active", "is_default_for_receipts"])
        AgentPrinter.objects.filter(station=station).update(station=None)
        return Response(status=204)


class AgentPrinterStationView(APIView):
    """PATCH /api/printing/printers/<id>/station/ — asigna/desasigna estación.
    Body: {"station_id": 5}  o  {"station_id": null}
    """
    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    def patch(self, request, pk):
        printer = get_object_or_404(
            AgentPrinter,
            pk=pk,
            agent__tenant_id=request.user.tenant_id,
            agent__is_active=True,
            is_active=True,
        )

        station_id = request.data.get("station_id")
        if station_id is None or station_id == "":
            printer.station = None
        else:
            try:
                station_id_int = int(station_id)
            except (ValueError, TypeError):
                return Response({"detail": "station_id inválido."}, status=400)
            station = get_object_or_404(
                PrintStation,
                pk=station_id_int,
                tenant_id=request.user.tenant_id,
                is_active=True,
            )
            printer.station = station

        printer.save(update_fields=["station"])
        return Response({
            "id": printer.pk,
            "name": printer.name,
            "station_id": printer.station_id,
        })
