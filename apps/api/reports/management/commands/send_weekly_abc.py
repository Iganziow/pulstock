"""
send_weekly_abc — el reporte ABC semanal por correo.

La tarea `reports.tasks.send_weekly_abc_report` existe y esta declarada en
CELERY_BEAT_SCHEDULE desde hace meses, pero **Celery no corre en produccion**:
todo el trabajo periodico se dispara por cron, igual que billing. Resultado:
el correo nunca se envio, mientras la pagina de ventas lo prometia cada lunes.

Este comando es el disparador que faltaba. Mismo patron que
billing_process_renewals: invoca la tarea sin depender del broker.

Uso (cron, lunes 8:00 Chile = 12:00 UTC):
    cd /var/www/pulstock/apps/api && venv/bin/python manage.py send_weekly_abc
"""
from django.core.management.base import BaseCommand

from core.cron_utils import cron_wrapper


class Command(BaseCommand):
    help = "Envia el reporte ABC semanal a los duenos de cada tenant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="No envia: solo informa a quien le llegaria.",
        )

    def handle(self, *args, **options):
        # 8 dias de tolerancia: es semanal, no diario.
        with cron_wrapper("reports.weekly_abc", max_age_min=8 * 24 * 60):
            self._run(options)

    def _run(self, options):
        if options["dry_run"]:
            from core.models import Tenant, User
            from stores.models import Store
            n = 0
            for t in Tenant.objects.filter(is_active=True):
                owner = User.objects.filter(
                    tenant=t, role="owner", is_active=True,
                ).values("email").first()
                store = Store.objects.filter(tenant=t, is_active=True).first()
                if owner and owner["email"] and store:
                    self.stdout.write("  [dry] %s -> %s" % (t.name, owner["email"]))
                    n += 1
                else:
                    self.stdout.write("  [dry] %s -> SALTADO (sin dueno o sin local)" % t.name)
            self.stdout.write("Se enviarian %d correo(s)." % n)
            return

        from reports.tasks import send_weekly_abc_report
        resultado = send_weekly_abc_report()
        self.stdout.write(self.style.SUCCESS("ABC semanal: %s" % resultado))
