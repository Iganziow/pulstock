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
                No los estamos prediciendo. Es el caso de la deslactosada.
  sin_puntaje — se vendieron en la ventana y no tienen NINGUNA fila de
                accuracy en ella. Puede que se pronostiquen recién desde hoy
                (recuperándose) o que se pronostiquen y no se puntúen.

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
        return {"con_ventas": 0, "ciegos": [], "sin_puntaje": [],
                "ventana_dias": days, "desde": desde, "hasta": hoy}

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

    return {
        "con_ventas": len(vendidos),
        "ciegos": ciegos,
        "sin_puntaje": sin_puntaje,
        "ventana_dias": days,
        "desde": desde,
        "hasta": hoy,
    }
