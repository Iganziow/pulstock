"""
printing/tasks.py
=================
Tareas Celery del sistema de Agente PC.

Requiere Celery + Redis (CELERY_BROKER_URL en settings.py).
Si Celery no está disponible, las funciones siguen siendo llamables
directamente (útil para dev local sin Redis).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from .models import PrintJob

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:
    # Fallback: decorator no-op para dev sin Celery
    def shared_task(func):
        return func


# Cuánto tiempo guardamos jobs completados/fallidos/cancelados antes de borrar.
# 30 días alcanza para debugging post-mortem; más que eso no aporta.
PRINT_JOB_RETENTION_DAYS = 30


@shared_task(name="printing.tasks.cleanup_old_jobs")
def cleanup_old_jobs() -> int:
    """
    Borra PrintJobs terminales (done/failed/cancelled) cuyo completed_at sea
    más antiguo que PRINT_JOB_RETENTION_DAYS.

    Corre diariamente vía Celery beat (ver CELERY_BEAT_SCHEDULE).

    Returns: cantidad de jobs borrados (para logging/monitoreo).
    """
    cutoff = timezone.now() - timedelta(days=PRINT_JOB_RETENTION_DAYS)
    terminal_statuses = [
        PrintJob.STATUS_DONE,
        PrintJob.STATUS_FAILED,
        PrintJob.STATUS_CANCELLED,
    ]
    deleted_count, _ = PrintJob.objects.filter(
        status__in=terminal_statuses,
        completed_at__lt=cutoff,
    ).delete()
    logger.info(
        "printing.cleanup_old_jobs: borrados %d jobs terminales >%dd",
        deleted_count, PRINT_JOB_RETENTION_DAYS,
    )
    return deleted_count
