"""
check_forecast_coverage — avisa cuando el forecast deja de mirar un producto.

Un producto que se deja de pronosticar no aparece como error en el tablero de
accuracy: desaparece del numerador y del denominador. El WAPE ni se inmuta.
Este comando existe para que ese silencio haga ruido.

Uso:
    python manage.py check_forecast_coverage
    python manage.py check_forecast_coverage --days 30
    python manage.py check_forecast_coverage --tenant 1
"""
from django.core.management.base import BaseCommand

from core.cron_utils import cron_wrapper
from forecast.coverage import COVERAGE_WINDOW_DAYS, find_coverage_gaps


class Command(BaseCommand):
    help = "Detecta productos que se venden pero que el forecast no está mirando."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=COVERAGE_WINDOW_DAYS)
        parser.add_argument("--tenant", type=int)

    def handle(self, *args, **options):
        with cron_wrapper("forecast.check_coverage", max_age_min=36 * 60):
            self._run(options)

    def _run(self, options):
        from core.models import Tenant

        tenants = Tenant.objects.all()
        if options["tenant"]:
            tenants = tenants.filter(id=options["tenant"])

        total_ciegos = 0
        for t in tenants:
            r = find_coverage_gaps(t.id, days=options["days"])
            if not r["con_ventas"]:
                continue

            ciegos = r["ciegos"]
            mudos = r.get("mudos", [])
            total_ciegos += len(ciegos) + len(mudos)
            cab = "%s — %d productos con venta en %d dias" % (
                t.name, r["con_ventas"], r["ventana_dias"])
            self.stdout.write(cab)

            if not ciegos:
                self.stdout.write(self.style.SUCCESS(
                    "  cobertura completa: todos tienen pronostico vigente"))
            else:
                self.stdout.write(self.style.ERROR(
                    "  SIN PRONOSTICO: %d producto(s) que SI se venden" % len(ciegos)))
                for f in ciegos[:15]:
                    self.stdout.write("    %-34s %10.1f unidades" % (
                        f["nombre"][:34], f["unidades"]))
                if len(ciegos) > 15:
                    self.stdout.write("    ... y %d mas" % (len(ciegos) - 15))

            if mudos:
                self.stdout.write(self.style.ERROR(
                    "  MUDOS: %d producto(s) con pronostico que NO se miden "
                    "hace %d dias" % (len(mudos), r.get("ventana_mudos_dias", 30))))
                for f in mudos[:10]:
                    self.stdout.write("    %-34s %10.1f unidades" % (
                        f["nombre"][:34], f["unidades"]))

            # Un producto puede tener pronostico desde hoy y aun asi no haber
            # sido puntuado en la ventana corta: es el que recien empieza.
            # Vale la pena verlo, pero no es la misma alarma.
            ya_reportados = {c["product_id"] for c in ciegos} | {m["product_id"] for m in mudos}
            solo_sin_puntaje = [f for f in r["sin_puntaje"]
                                if f["product_id"] not in ya_reportados]
            if solo_sin_puntaje:
                self.stdout.write(self.style.WARNING(
                    "  con pronostico pero sin puntuar en la ventana: %d" % len(solo_sin_puntaje)))
                for f in solo_sin_puntaje[:5]:
                    self.stdout.write("    %-34s %10.1f unidades" % (
                        f["nombre"][:34], f["unidades"]))

        if total_ciegos:
            # Falla para que cron/monitoreo lo registre: es una alarma, no un
            # informe. Un producto invisible se compra a ojo — y uno que el
            # sistema cree medir pero no mide es peor, porque da falsa
            # tranquilidad.
            raise RuntimeError(
                "%d producto(s) sin pronostico o sin medirse" % total_ciegos)

        self.stdout.write(self.style.SUCCESS("Cobertura de forecast OK"))
