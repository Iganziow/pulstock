"""
purge_nonoperative_accuracy
===========================
Borra los registros de ForecastAccuracy de días en que el negocio NO OPERÓ.

Problema que resuelve
---------------------
`track_forecast_accuracy` puntuaba todos los días por igual. Si el local no
abrió (domingo, feriado, caída del sistema), cada producto quedaba con un
"predijo X, real 0". Eso no es un error del modelo — es un día que no existió.

Medido en Marbrava el 04/08/26 sobre 30 días:
  - error real medido:              71,9% WAPE, sesgo +30,7%
  - sin domingos (local cerrado):   61,0% WAPE, sesgo +19,8%
  - sin domingos ni el 28-jul:      55,3% WAPE, sesgo +14,1%
O sea más de la mitad del sesgo eran días no operativos.

Además de ensuciar la métrica, esos falsos errores alimentan el breaker (que
fuerza reentrenamientos) y la recalibración de `confidence_label`: al modelo
le bajaba la confianza por días en que era imposible vender.

`track_forecast_accuracy` ya no crea estos registros. Este comando limpia los
que quedaron de antes.

Criterio
--------
El mismo que aplica `track_forecast_accuracy` de aquí en adelante:
`forecast.services.business_operated_on`. Distingue "no abrió" de "abrió y no
vendió nada de este producto" — lo segundo SÍ es un error del modelo y se sigue
puntuando.

NO toca ventas, stock ni modelos: solo la tabla de precisión.

Uso:
    python manage.py purge_nonoperative_accuracy --tenant 1            # DRY-RUN
    python manage.py purge_nonoperative_accuracy --tenant 1 --apply
    python manage.py purge_nonoperative_accuracy --tenant 1 --days 90 --apply
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant
from forecast.models import ForecastAccuracy
from forecast.services import business_operated_on

DEFAULT_DAYS = 180


class Command(BaseCommand):
    help = "Borra ForecastAccuracy de días en que el negocio no operó (domingos, feriados, caídas)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: todos)")
        parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"Ventana hacia atrás (default: {DEFAULT_DAYS})")
        parser.add_argument("--apply", action="store_true", help="Persistir el borrado (sin esto es dry-run)")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        hoy = timezone.localdate()
        desde = hoy - timedelta(days=opts["days"])
        tenants = (
            Tenant.objects.filter(id=opts["tenant"]) if opts["tenant"]
            else Tenant.objects.all()
        )

        for tenant in tenants:
            self._purge(tenant, desde, hoy, apply)

    def _purge(self, tenant, desde, hoy, apply):
        fechas_con_precision = set(
            ForecastAccuracy.objects
            .filter(tenant=tenant, date__gte=desde, date__lte=hoy)
            .values_list("date", flat=True)
            .distinct()
        )
        if not fechas_con_precision:
            self.stdout.write(f"[tenant {tenant.id}] sin registros de precisión en la ventana.")
            return

        # Mismo criterio que usa track_forecast_accuracy, para que la limpieza
        # retroactiva y la de aquí en adelante no discrepen.
        no_operativos = sorted(
            d for d in fechas_con_precision
            if not business_operated_on(tenant.id, d)
        )

        if not no_operativos:
            self.stdout.write(
                f"[tenant {tenant.id}] los {len(fechas_con_precision)} días con precisión "
                f"tuvieron movimiento — nada que borrar."
            )
            return

        qs = ForecastAccuracy.objects.filter(tenant=tenant, date__in=no_operativos)
        n = qs.count()

        self.stdout.write(
            f"[tenant {tenant.id}] {len(no_operativos)} días NO operativos "
            f"de {len(fechas_con_precision)} con precisión — {n} registros"
        )
        for d in no_operativos[:15]:
            dow = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][d.weekday()]
            cnt = ForecastAccuracy.objects.filter(tenant=tenant, date=d).count()
            self.stdout.write(f"    {d} ({dow}): {cnt} registros")
        if len(no_operativos) > 15:
            self.stdout.write(f"    … y {len(no_operativos) - 15} días más")

        if not apply:
            self.stdout.write(self.style.WARNING("\n  DRY-RUN — no se borró nada. Usa --apply."))
            return

        qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f"\n  APLICADO ✅ — {n} registros borrados. "
            f"El WAPE real y la recalibración de confianza dejan de contar días "
            f"en que el local no abrió.\n"
            f"  (No se tocaron ventas, stock ni modelos.)"
        ))
