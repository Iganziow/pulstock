"""
run_nightly_pipeline — los pasos de la noche, en orden y esperando a cada uno.

El problema que resuelve
------------------------
Los cinco pasos estaban encadenados por RELOJ, no por terminacion:

    04:30  aggregate_daily_sales
    05:30  track_forecast_accuracy
    06:30  compute_category_profiles + train_forecast_models
    07:00  generate_purchase_suggestions
    07:30  backup

Cada uno arranca a su hora **pase lo que pase**. Con un cliente sobra tiempo;
medido el 24-ago-2026, el pipeline entero tarda 28,7 s por negocio (el 98% es
el entrenamiento). Pero la ventana entre el entrenamiento y las sugerencias es
de 30 minutos, asi que:

    30 min / 28,7 s  =  ~62 negocios

Pasado ese numero, las sugerencias arrancan con el entrenamiento a medias y se
calculan sobre modelos parcialmente actualizados. **Sin fallar y sin avisar** —
la misma familia de error que venimos sacando del sistema.

Encadenando por terminacion el tiempo total deja de importar: tarda lo que
tenga que tardar y el orden queda garantizado por construccion, no por suerte.

Que hace con los errores
------------------------
Los pasos dependen unos de otros: sin demanda agregada no hay nada que
entrenar, y sin modelos no hay sugerencia que generar.

  · Falla TOTAL de un paso (ningun negocio se proceso) -> se corta la cadena.
    Se rompio algo comun y seguir solo produciria resultados basura sobre
    datos incompletos.

  · Falla PARCIAL (algunos negocios si) -> sigue. Los sanos tienen derecho a
    su entrenamiento y a su sugerencia aunque un local tenga una receta rota.

Cada paso conserva su propio heartbeat, asi que se puede ver cual fallo sin
leer el log.

Uso:
    python manage.py run_nightly_pipeline
    python manage.py run_nightly_pipeline --tenant 1     # un solo negocio
    python manage.py run_nightly_pipeline --dry-run      # solo lista los pasos
"""
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from core.heartbeat import with_heartbeat
from core.multi_tenant import FallaParcial

# El orden importa y no es arbitrario:
#   1. agregar la demanda del dia anterior      (base de todo lo demas)
#   2. recalcular los minimos de stock          (necesita 1)
#   3. medir que tan bien predijimos ayer       (necesita 1)
#   4. calcular los priors por categoria        (necesita 1)
#   5. entrenar los modelos                     (necesita 1 y 4)
#   6. convertir pronostico en sugerencia       (necesita 5)
#
# Los minimos van temprano y no al final: la alerta de quiebre corre a las
# 12:00 y tiene que leer los numeros de esta madrugada, no los de ayer.
PASOS = [
    ("aggregate_daily_sales", {}),
    ("recalcular_minimos", {}),
    ("track_forecast_accuracy", {"days": 1}),
    ("compute_category_profiles", {}),
    ("train_forecast_models", {"horizon": 30}),
    ("generate_purchase_suggestions", {}),
]


class Command(BaseCommand):
    help = "Corre el pipeline nocturno completo, en orden y esperando a cada paso."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int,
                            help="Correr solo para este negocio.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Listar los pasos sin ejecutarlos.")

    # 8 horas de margen: el pipeline corre una vez por noche y con muchos
    # clientes puede tardar. Mas vale un margen amplio que una falsa alarma
    # todas las madrugadas.
    @with_heartbeat("forecast.pipeline_nocturno", expected_max_age_minutes=30 * 60)
    def handle(self, *args, **options):
        if options["dry_run"]:
            self.stdout.write("Pasos, en orden:")
            for i, (nombre, extra) in enumerate(PASOS, 1):
                args_txt = " ".join(f"--{k.replace('_', '-')} {v}"
                                    for k, v in extra.items())
                self.stdout.write(f"  {i}. {nombre} {args_txt}".rstrip())
            return

        comunes = {"verbosity": options.get("verbosity", 1)}
        if options.get("tenant"):
            comunes["tenant"] = options["tenant"]

        arranque = time.monotonic()
        parciales = []

        for i, (nombre, extra) in enumerate(PASOS, 1):
            t0 = time.monotonic()
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n[{i}/{len(PASOS)}] {nombre}"
            ))
            try:
                call_command(nombre, **{**comunes, **extra})
                dur = time.monotonic() - t0
                self.stdout.write(self.style.SUCCESS(
                    f"    ✓ {nombre} en {dur:.1f}s"
                ))
            except FallaParcial as exc:
                # Algunos negocios fallaron pero otros terminaron bien: la
                # cadena sigue, porque los sanos necesitan los pasos de abajo.
                dur = time.monotonic() - t0
                parciales.append((nombre, exc))
                self.stderr.write(self.style.WARNING(
                    f"    ! {nombre} en {dur:.1f}s — parcial: {exc}"
                ))
            except Exception as exc:
                # Falla total: nada de lo que viene despues tendria sentido.
                dur = time.monotonic() - t0
                total = time.monotonic() - arranque
                self.stderr.write(self.style.ERROR(
                    f"    ✗ {nombre} en {dur:.1f}s — se corta el pipeline"
                ))
                raise CommandError(
                    f"El pipeline se detuvo en el paso {i}/{len(PASOS)} "
                    f"({nombre}) tras {total:.1f}s: {exc}"
                ) from exc

        total = time.monotonic() - arranque
        self.stdout.write(self.style.SUCCESS(
            f"\nPipeline completo en {total:.1f}s."
        ))

        if parciales:
            detalle = "; ".join(f"{n}: {e}" for n, e in parciales)
            raise FallaParcial(
                f"{len(parciales)} paso(s) con fallas parciales. {detalle}",
                ok=len(PASOS) - len(parciales),
                fallidos=len(parciales),
            )
