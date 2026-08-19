"""
Reconcilia pagos cuyo webhook nunca llegó (B25).

Si Flow confirma el pago pero el webhook se pierde —un deploy, un 502, una
caída de minutos— la sesión de checkout queda PENDING para siempre: el cliente
pagó y se queda sin cuenta. Esta tarea consulta el estado real en Flow y
completa la cuenta.

Corre desde cron (no depende de Celery), igual que el resto del billing:
    cd /var/www/pulstock/apps/api && venv/bin/python manage.py reconcile_checkouts
"""
from django.core.management.base import BaseCommand

from core.cron_utils import cron_wrapper


class Command(BaseCommand):
    help = "Recupera pagos confirmados en Flow cuyo webhook no llegó (B25)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50,
                            help="Máximo de sesiones a revisar por corrida")

    def handle(self, *args, **options):
        with cron_wrapper("billing.reconcile_checkouts", max_age_min=120):
            from billing.reconcile import reconcile_pending_checkouts
            r = reconcile_pending_checkouts(limit=options["limit"])
            msg = (f"revisadas={r['revisadas']} recuperadas={r['recuperadas']} "
                   f"errores={r['errores']}")
            if r["recuperadas"]:
                self.stdout.write(self.style.SUCCESS(
                    msg + "  <- habia pagos huerfanos, cuentas creadas"))
            else:
                self.stdout.write(msg)
