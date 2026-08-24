"""
registrar_heartbeat — deja constancia de que una tarea de shell corrio.

El pipeline de Python registra sus latidos con el decorador `with_heartbeat`.
Pero el respaldo diario es un script de bash --`/var/backups/pulstock/backup.sh`--
y no tenia forma de anotarse. Resultado: **el backup era la unica tarea critica
que podia fallar en silencio**, y es la peor candidata posible para eso, porque
el fallo se descubre el dia que hay que restaurar.

Escribia su resultado en `backup.log`, un archivo que nadie abre.

Uso desde bash:

    manage.py registrar_heartbeat backup.diario --duracion 12
    manage.py registrar_heartbeat backup.diario --fallo "pg_dump devolvio 1"

Un nombre que empiece con `backup.` cuenta como CRITICO en
/api/core/health/deep/: si el respaldo no corre, eso si justifica una alarma.
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Registra el latido de una tarea externa (scripts de shell)."

    def add_arguments(self, parser):
        parser.add_argument("tarea", help="Nombre, ej: backup.diario")
        parser.add_argument("--duracion", type=float, default=0,
                            help="Segundos que tardo.")
        parser.add_argument("--fallo", default="",
                            help="Mensaje de error. Si viene, se marca como fallida.")
        parser.add_argument("--max-edad-min", type=int, default=36 * 60,
                            help="Minutos maximos entre corridas esperadas.")

    def handle(self, *args, **options):
        from core.models import CronHeartbeat

        tarea = options["tarea"].strip()
        if not tarea:
            raise CommandError("Falta el nombre de la tarea.")

        fallo = (options["fallo"] or "").strip()
        CronHeartbeat.objects.update_or_create(
            task_name=tarea,
            defaults={
                "last_result": "failed" if fallo else "ok",
                "last_error": fallo[:500],
                "last_duration_s": round(options["duracion"], 1),
                "expected_max_age_minutes": options["max_edad_min"],
            },
        )
        estado = "FALLIDA" if fallo else "ok"
        self.stdout.write(f"{tarea}: {estado}")
