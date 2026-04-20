"""
Utilidades compartidas para management commands que se corren desde cron.

Patrón principal:
    from core.cron_utils import cron_wrapper

    class Command(BaseCommand):
        def handle(self, *args, **options):
            with cron_wrapper("billing.process_renewals", max_age_min=90):
                from billing.tasks import process_renewals
                result = process_renewals.apply()
                if result.failed():
                    raise RuntimeError(result.traceback)
"""
from __future__ import annotations

import contextlib
import logging
import time
from typing import Iterator

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def cron_wrapper(task_name: str, max_age_min: int = 90) -> Iterator[None]:
    """
    Registra heartbeat al terminar exitosamente; marca failed si hay excepción.
    La excepción se re-propaga para que cron la registre y el runtime retorne
    non-zero.
    """
    from core.models import record_cron_heartbeat

    started = time.monotonic()
    try:
        yield
    except Exception as exc:
        duration = time.monotonic() - started
        try:
            record_cron_heartbeat(
                task_name, duration, "failed", repr(exc)[:500],
                expected_max_age_minutes=max_age_min,
            )
        except Exception as hb_exc:
            logger.exception("No se pudo registrar heartbeat de %s: %s",
                             task_name, hb_exc)
        raise
    else:
        duration = time.monotonic() - started
        try:
            record_cron_heartbeat(
                task_name, duration, "ok", "",
                expected_max_age_minutes=max_age_min,
            )
        except Exception as hb_exc:
            logger.exception("No se pudo registrar heartbeat de %s: %s",
                             task_name, hb_exc)
