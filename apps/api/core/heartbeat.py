"""
Dead man's switch para los crons.

El problema que resuelve: hoy nadie detecta si el pipeline nocturno NO corrió.
`CronHeartbeat` y el chequeo en /api/core/health/deep/ existen desde abril,
pero ningún comando escribía heartbeats — el monitor vigilaba un pulso que
nadie emitía, así que "cron ok" era verdad vacía con 0 registrados.

Y ahora todo vive en ese pipeline: el calendario de días cerrados, la
recalibración de confianza, el corte de demanda detenida y las sugerencias de
compra. Si muere en silencio, el sistema entero deja de aprender y nadie se
entera hasta que Mario pregunta por qué la sugerencia está vieja.

Uso:
    from core.heartbeat import with_heartbeat

    class Command(BaseCommand):
        @with_heartbeat("train_forecast_models", expected_max_age_minutes=26 * 60)
        def handle(self, *args, **opts):
            ...

El decorador registra inicio/fin/duración y si falló, guarda el error y
RE-LANZA la excepción — el cron log conserva su traceback de siempre.
El endpoint /api/core/health/deep/ marca "degraded" si un heartbeat está stale
o failed; un monitor externo que lo consulte cada ~5 min cierra el circuito.
"""
import functools
import time

from django.utils import timezone


def with_heartbeat(task_name: str, expected_max_age_minutes: int = 26 * 60):
    """Envuelve el handle() de un management command con un CronHeartbeat.

    26h de max_age por defecto: los crons corren diario y un margen de 2h
    absorbe variaciones sin dar falsas alarmas.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from core.models import CronHeartbeat

            start = time.monotonic()
            CronHeartbeat.objects.update_or_create(
                task_name=task_name,
                defaults={
                    "last_result": "running",
                    "last_error": "",
                    "expected_max_age_minutes": expected_max_age_minutes,
                },
            )
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                CronHeartbeat.objects.update_or_create(
                    task_name=task_name,
                    defaults={
                        "last_result": "failed",
                        "last_error": str(e)[:500],
                        "last_duration_s": round(time.monotonic() - start, 1),
                        "expected_max_age_minutes": expected_max_age_minutes,
                    },
                )
                raise  # el cron log conserva el traceback
            CronHeartbeat.objects.update_or_create(
                task_name=task_name,
                defaults={
                    "last_result": "ok",
                    "last_error": "",
                    "last_duration_s": round(time.monotonic() - start, 1),
                    "expected_max_age_minutes": expected_max_age_minutes,
                },
            )
            return result
        return wrapper
    return decorator
