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

# Ventana para juzgar CALIDAD (no cobertura). Mas larga: el WAPE de una semana
# en demanda intermitente es ruido.
CALIDAD_WINDOW_DAYS = 30

# Que fraccion de la venta define el "nucleo". Pareto, no un umbral de
# unidades fijo: 90% del volumen significa lo mismo en una cafeteria que en
# una ferreteria, y se adapta solo cuando el negocio cambia.
NUCLEO_FRACCION = 0.90


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


def calidad_por_peso(tenant_id: int, days: int = CALIDAD_WINDOW_DAYS,
                     today: date | None = None,
                     fraccion: float = NUCLEO_FRACCION) -> dict:
    """Precision del forecast separando el catalogo que pesa del que no.

    Por que existe
    --------------
    El WAPE global de un catalogo real esta dominado por productos que casi no
    venden, y eso lo vuelve ilegible en las dos direcciones: exagera el error
    cuando todo anda bien, y —peor— puede TAPAR una degradacion real del
    nucleo bajo el ruido de la cola.

    Medido en Marbrava el 02/09/26, ventana de 30 dias:

        segmento   prod   medic   sesgo    WAPE   unidades
        nucleo        4      74    +13%     43%     31.103
        cola        188   4.545   +116%    246%      3.448
        total       192   4.619    +23%     63%     34.551

    CUATRO productos son el 90% de la venta. Los otros 188 aportan el 10% --
    y se llevan el 98% de las mediciones. Lo que reportabamos como calidad
    del forecast (63%) era, en los hechos, la calidad sobre el 10% del
    negocio: el nucleo esta en 43% y +13%, que es defendible.

    Errarle a un producto que vende 1 unidad al mes pesa en el WAPE global lo
    mismo que errarle al que vende 3.000. 38 productos no vendieron NADA en
    el mes, y el 89% de las mediciones de `adaptive_ma` se toman contra un
    real de cero: de ahi salia su +198% de sesgo aparente.

    Esto no arregla el modelo: arregla el termometro. Sin separar, nadie puede
    distinguir "el forecast se degrado" de "entraron productos nuevos a la
    cola", y una alarma que no distingue eso termina ignorandose.

    Devuelve {"nucleo": {...}, "cola": {...}, "total": {...}, ...} donde cada
    segmento trae n_productos, n_mediciones, sesgo_pct, wape_pct y unidades.
    """
    from forecast.models import ForecastAccuracy

    hoy = today or date.today()
    desde = hoy - timedelta(days=days)

    filas = list(
        ForecastAccuracy.objects
        .filter(tenant_id=tenant_id, date__gte=desde, date__lt=hoy)
        .values_list("product_id", "qty_predicted", "qty_actual")
    )
    vacio = {"n_productos": 0, "n_mediciones": 0, "unidades": 0.0,
             "sesgo_pct": None, "wape_pct": None}
    if not filas:
        return {"nucleo": dict(vacio), "cola": dict(vacio), "total": dict(vacio),
                "ventana_dias": days, "fraccion_nucleo": fraccion,
                "desde": desde, "hasta": hoy}

    real_por_prod: dict[int, float] = {}
    for pid, _p, r in filas:
        real_por_prod[pid] = real_por_prod.get(pid, 0.0) + float(r or 0)

    # Pareto: ordenar por volumen y cortar donde se acumula la fraccion.
    # Los productos con venta 0 nunca entran al nucleo (aportan 0 al acumulado).
    total_real = sum(real_por_prod.values())
    nucleo: set[int] = set()
    if total_real > 0:
        acum = 0.0
        for pid, v in sorted(real_por_prod.items(), key=lambda kv: -kv[1]):
            if v <= 0:
                break
            nucleo.add(pid)
            acum += v
            if acum >= total_real * fraccion:
                break

    def _seg(ids):
        n = pred = real = aerr = 0
        prods = set()
        for pid, p, r in filas:
            if ids is not None and pid not in ids:
                continue
            p, r = float(p or 0), float(r or 0)
            n += 1; prods.add(pid); pred += p; real += r; aerr += abs(p - r)
        return {
            "n_productos": len(prods),
            "n_mediciones": n,
            "unidades": round(real, 1),
            "sesgo_pct": round((pred - real) / real * 100, 1) if real else None,
            "wape_pct": round(aerr / real * 100, 1) if real else None,
        }

    cola_ids = set(real_por_prod) - nucleo
    return {
        "nucleo": _seg(nucleo),
        "cola": _seg(cola_ids),
        "total": _seg(None),
        "ventana_dias": days,
        "fraccion_nucleo": fraccion,
        "desde": desde,
        "hasta": hoy,
    }
