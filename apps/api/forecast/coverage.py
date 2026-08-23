"""
forecast.coverage — ¿a qué le estamos errando y a qué ni siquiera le apuntamos?

El agujero
----------
`track_forecast_accuracy` solo puntúa productos que tengan una fila en
`Forecast` para ese día. Si un producto deja de pronosticarse, no aparece como
error en el tablero: **desaparece**. La métrica no puede ver su propia
cobertura, así que un WAPE bajo puede significar "el modelo anda bien" o
"medimos cada vez menos cosas" y desde afuera se ven idénticos.

Caso real (Marbrava, detectado el 20/08/26): `Leche deslactosada` estuvo
2,5 meses —del 6-jun al 20-ago— sin una sola fila de accuracy, vendiendo entre
200 y 1290 unidades diarias. Su modelo activo era `category_prior` con
data_points=0 y avg_daily=0,873: como producto de venta directa casi no tiene
historia porque se consume dentro de recetas, así que el pipeline la salteaba.
El WAPE del período no se movió un punto, porque el producto no estaba en el
denominador ni en el numerador.

Qué mide esto
-------------
Dos agujeros distintos, que se arreglan distinto:

  ciegos      — se vendieron en la ventana y NO tienen pronóstico a futuro.
                No los estamos prediciendo.
  mudos       — se vendieron, TIENEN pronóstico, y aun así no tienen una sola
                fila de accuracy en 30 días. Es el caso peor: el sistema cree
                que los está midiendo y no los mide. Así estuvo Leche
                deslactosada desde el 6-jun, con pronóstico vigente y
                vendiendo 4.170 unidades cada 14 días.
  sin_puntaje — se vendieron y no tienen accuracy en la ventana corta. Puede
                ser un producto que recién empieza a pronosticarse; por eso
                avisa pero no falla.

No mira productos sin ventas: que no se pronostique algo que nadie compra no
es un agujero, es lo correcto.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Ventana para decidir "esto se vende". Corta pero no tanto como para que una
# semana floja borre un producto estacional del radar.
COVERAGE_WINDOW_DAYS = 14

# Ventana larga para detectar mudos. Un producto que vende hace un mes y nunca
# se midio no es un caso de "recien empieza": es una falla.
MUTE_WINDOW_DAYS = 30


def find_coverage_gaps(tenant_id: int, days: int = COVERAGE_WINDOW_DAYS,
                       today: date | None = None) -> dict:
    """Productos que se venden pero que el forecast no está mirando.

    Devuelve {"ciegos": [...], "sin_puntaje": [...], "con_ventas": n, ...},
    ordenados por volumen vendido: el primero de la lista es el que más caro
    sale ignorar.
    """
    from django.db.models import Sum
    from catalog.models import Product
    from forecast.models import DailySales, Forecast, ForecastAccuracy

    hoy = today or date.today()
    desde = hoy - timedelta(days=days)

    vendidos = {
        r["product_id"]: float(r["q"] or 0)
        for r in DailySales.objects
        .filter(tenant_id=tenant_id, date__gte=desde, date__lt=hoy, qty_sold__gt=0)
        .values("product_id").annotate(q=Sum("qty_sold"))
    }
    if not vendidos:
        return {"con_ventas": 0, "ciegos": [], "mudos": [], "sin_puntaje": [],
                "ventana_dias": days, "ventana_mudos_dias": MUTE_WINDOW_DAYS,
                "desde": desde, "hasta": hoy}

    # Con pronóstico vigente: de hoy en adelante. Mirar el futuro y no el
    # pasado es a propósito — las filas de Forecast se purgan, así que su
    # ausencia en fechas viejas no prueba nada.
    con_pronostico = set(
        Forecast.objects
        .filter(tenant_id=tenant_id, product_id__in=vendidos, forecast_date__gte=hoy)
        .values_list("product_id", flat=True)
    )
    con_puntaje = set(
        ForecastAccuracy.objects
        .filter(tenant_id=tenant_id, product_id__in=vendidos, date__gte=desde)
        .values_list("product_id", flat=True)
    )

    nombres = dict(
        Product.objects.filter(id__in=vendidos).values_list("id", "name")
    )

    def _filas(ids):
        return [
            {"product_id": pid, "nombre": nombres.get(pid, f"#{pid}"),
             "unidades": round(vendidos[pid], 1)}
            for pid in sorted(ids, key=lambda p: -vendidos[p])
        ]

    ciegos = _filas(set(vendidos) - con_pronostico)
    sin_puntaje = _filas(set(vendidos) - con_puntaje)

    # Mudos: tienen pronóstico y venden, pero llevan 30 días sin una sola
    # medición. El sistema cree que los mide y no los mide — y como no falla
    # nada, nadie se entera. Es exactamente el agujero que costó 2,5 meses
    # descubrir la primera vez.
    desde_largo = hoy - timedelta(days=MUTE_WINDOW_DAYS)
    medidos_largo = set(
        ForecastAccuracy.objects
        .filter(tenant_id=tenant_id, product_id__in=vendidos, date__gte=desde_largo)
        .values_list("product_id", flat=True)
    )
    mudos = _filas((set(vendidos) & con_pronostico) - medidos_largo)

    return {
        "con_ventas": len(vendidos),
        "ciegos": ciegos,
        "mudos": mudos,
        "sin_puntaje": sin_puntaje,
        "ventana_dias": days,
        "ventana_mudos_dias": MUTE_WINDOW_DAYS,
        "desde": desde,
        "hasta": hoy,
    }
