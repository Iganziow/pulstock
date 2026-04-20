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

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasTenant, IsManager
from .models import AgentPrinter, PrintAgent, PrintJob

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
                    }
                    for p in a.printers.all() if p.is_active
                ],
            }
            for a in qs
        ])

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "El nombre es obligatorio."}, status=400)
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

        job = PrintJob.objects.create(
            tenant_id=request.user.tenant_id,
            agent=agent,
            printer_name=(request.data.get("printer_name") or "").strip(),
            data_b64=data_b64,
            html=html,
            source=(request.data.get("source") or "")[:30],
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

    def get(self, request):
        agent = _resolve_agent_by_key(request)
        if not agent:
            return Response({"detail": "api_key inválida."}, status=401)

        agent.touch()

        # Fetch one pending job (FIFO)
        job = PrintJob.objects.filter(
            agent=agent, status=PrintJob.STATUS_PENDING,
        ).order_by("created_at").first()

        if not job:
            return Response({"job": None})

        # Mark as printing (atomic — prevent double pickup)
        from django.db import transaction
        with transaction.atomic():
            updated = PrintJob.objects.filter(
                pk=job.pk, status=PrintJob.STATUS_PENDING,
            ).update(
                status=PrintJob.STATUS_PRINTING,
                picked_at=timezone.now(),
            )
            if not updated:
                # Someone else picked it (shouldn't happen with single agent but safe)
                return Response({"job": None})

        job.refresh_from_db()
        return Response({
            "job": {
                "id": job.pk,
                "printer_name": job.printer_name,
                "data_b64": job.data_b64,
                "html": job.html,
                "source": job.source,
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

            obj, _ = AgentPrinter.objects.update_or_create(
                agent=agent, name=name,
                defaults={
                    "display_name": (p.get("display_name") or "")[:150],
                    "paper_width": paper_width,
                    "connection_type": ct,
                    "network_address": (p.get("network_address") or "")[:100],
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
