# -*- coding: utf-8 -*-
"""
backtest_forecast — el backtest FIEL a produccion, como comando del sistema.

Por que existe
--------------
El motor de pronostico es una red de compensaciones (el cero de hoy, el
guard de colapso, la seleccion por patron de demanda, la ventana del perfil
de negocio...). Un backtest "de laboratorio" que no replica ese
preprocesamiento da veredictos equivocados: en septiembre de 2026 uno asi
recomendo quitar el cero de hoy, y el backtest fiel mostro que empeoraba la
cola un 22% (WAPE total 132% -> 154%). Se revirtio antes de desplegar. Sin
esta disciplina cada arreglo del modelo es una apuesta.

Que hace
--------
Para cada producto con historia, simula la corrida nocturna de `semanas`
dias D pasados (uno por semana, hacia atras desde `--hasta`):

  1. arma la serie con `armar_serie_entrenamiento`, el MISMO codigo que usa
     train_product_model (ventas hasta D-1, cero de D, mermas si el negocio
     las cuenta, stockouts, promos, dias cerrados, patron, factores de mes);
  2. elige modelo con select_best_model y aplica el guard de colapso, como
     la noche real;
  3. pronostica D+1..D+horizonte y compara con lo que se vendio esos dias
     (los dias cerrados detectados no se evaluan).

Acumula error absoluto, real y con signo por producto y resume por segmento
(nucleo = los productos que hacen el 90% de la venta de los ultimos 30
dias; cola = el resto) y por patron de demanda.

Uso
---
  python manage.py backtest_forecast --tenant 1
  python manage.py backtest_forecast --tenant 1 --semanas 4 --salida base.json
  # ... se cambia algo del motor ...
  python manage.py backtest_forecast --tenant 1 --semanas 4 --comparar base.json

Lo que NO replica, a proposito: el kept-path (en produccion un modelo viejo
se conserva si el fresco no le gana), la correccion de sesgo y la
calibracion de bandas (no mueven el punto medio que se evalua aqui) ni los
modelos derivados de receta. Mide el motor de seleccion, que es lo que
cambia cuando se toca un algoritmo. En produccion correrlo con
`SENTRY_DSN=` delante para no ensuciar Sentry con diagnosticos.
"""
import json
import time
import warnings
from collections import Counter, defaultdict
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

from catalog.models import Product
from core.models import Tenant
from forecast.engine import select_best_model
from forecast.models import DailySales, ForecastModel
from forecast.services import armar_serie_entrenamiento, _collapse_guard

NUCLEO_FRACCION = 0.90
VENTANA_NUCLEO_DIAS = 30
SEGMENTOS_FIJOS = ("TOTAL", "nucleo", "cola")


def _perfil(tenant):
    from forecast.management.commands.train_forecast_models import Command as Entrenar
    perfiles = Entrenar.BUSINESS_PROFILES
    return perfiles.get(getattr(tenant, "business_type", "other") or "other", perfiles["other"])


def productos_a_evaluar(tenant, hasta, solo_producto=None):
    """(product_id, warehouse_id, nombre) con historia en el tenant. Se saltan
    los ingredientes cuyo modelo activo es el derivado de receta: a esos no
    los pronostica el motor de seleccion."""
    pares = (
        DailySales.objects.filter(tenant=tenant, date__lte=hasta)
        .values_list("product_id", "warehouse_id").distinct()
    )
    if solo_producto:
        pares = pares.filter(product_id=solo_producto)
    derivados = set(
        ForecastModel.objects.filter(
            tenant=tenant, is_active=True, algorithm="ingredient_derived",
        ).values_list("product_id", "warehouse_id")
    )
    nombres = dict(Product.objects.filter(tenant=tenant).values_list("id", "name"))
    return sorted(
        (pid, wh, nombres[pid]) for pid, wh in pares
        if pid in nombres and (pid, wh) not in derivados
    )


def nucleo_de_ventas(tenant, hasta, dias=VENTANA_NUCLEO_DIAS, fraccion=NUCLEO_FRACCION):
    """Los productos que, ordenados por venta, acumulan `fraccion` de la venta
    de los ultimos `dias`. Misma regla que forecast.coverage.calidad_por_peso."""
    desde = hasta - timedelta(days=dias - 1)
    por_prod = defaultdict(float)
    for pid, q in DailySales.objects.filter(
        tenant=tenant, date__gte=desde, date__lte=hasta,
    ).values_list("product_id", "qty_sold"):
        por_prod[pid] += float(q or 0)
    total = sum(por_prod.values())
    nucleo, acum = set(), 0.0
    for pid, q in sorted(por_prod.items(), key=lambda kv: -kv[1]):
        nucleo.add(pid)
        acum += q
        if total and acum >= fraccion * total:
            break
    return nucleo


def backtest_producto(tenant, product, warehouse_id, hasta, horizonte, semanas,
                      window, min_days, ventas, es_nucleo, avisar=None):
    """Simula `semanas` corridas nocturnas de un producto y acumula su error."""
    acum = {"abs": 0.0, "real": 0.0, "signed": 0.0}
    algoritmos, patrones, folds = [], [], 0
    for f in range(semanas, 0, -1):
        dia_corrida = hasta - timedelta(days=horizonte * f)   # f=1 -> evalua hasta `hasta`
        serie = armar_serie_entrenamiento(tenant, product, warehouse_id, dia_corrida, min_days)
        if serie is None:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                best = select_best_model(
                    serie["cleaned"], window=window, horizon=horizonte, test_days=7,
                    month_factors=serie["month_factors"],
                    demand_pattern=serie["demand_pattern"],
                    stockout_dates=serie["stockout_dates"],
                )
        except Exception as exc:  # un producto roto no tumba el backtest
            if avisar:
                avisar("  %s: fallo la seleccion el %s: %s" % (product.name, dia_corrida, exc))
            continue
        if best.get("algorithm") == "none" or not best.get("forecasts"):
            continue
        best = _collapse_guard(best, serie["raw_series"], dia_corrida, horizonte, product=product)
        pron = {x["date"]: float(x["qty_predicted"]) for x in best["forecasts"]}
        folds += 1
        algoritmos.append(best["algorithm"])
        patrones.append(serie["demand_pattern"])
        for i in range(1, horizonte + 1):
            d = dia_corrida + timedelta(days=i)
            if d.weekday() in serie["closed_dows"]:
                continue
            real = ventas.get((product.id, warehouse_id, d), 0.0)
            pred = pron.get(d, 0.0)
            acum["abs"] += abs(pred - real)
            acum["real"] += real
            acum["signed"] += pred - real
    if not folds:
        return None
    return {
        "product_id": product.id,
        "warehouse_id": warehouse_id,
        "nombre": product.name,
        "seg": "nucleo" if es_nucleo else "cola",
        "semanas": folds,
        "abs": round(acum["abs"], 3),
        "real": round(acum["real"], 3),
        "signed": round(acum["signed"], 3),
        "alg": Counter(algoritmos).most_common(1)[0][0],
        "pat": Counter(patrones).most_common(1)[0][0],
    }


def agregar(productos):
    """{segmento: [abs, real, signed, n]} para TOTAL, nucleo/cola y pat:<patron>."""
    agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
    for p in productos:
        for s in ("TOTAL", p["seg"], "pat:" + p["pat"]):
            agg[s][0] += p["abs"]
            agg[s][1] += p["real"]
            agg[s][2] += p["signed"]
            agg[s][3] += 1
    return agg


def _wape(x):
    return x[0] / x[1] * 100 if x[1] else None


def _sesgo(x):
    return x[2] / x[1] * 100 if x[1] else None


def _pct(v, signo=False):
    if v is None:
        return "     -"
    return ("%+6.1f%%" if signo else "%6.1f%%") % v


def _orden_segmentos(claves):
    return sorted(claves, key=lambda s: (SEGMENTOS_FIJOS.index(s) if s in SEGMENTOS_FIJOS else 9, s))


class Command(BaseCommand):
    help = ("Backtest fiel a produccion: re-corre la seleccion nocturna semana a "
            "semana sobre la historia real y mide el error por segmento.")

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="ID del tenant")
        parser.add_argument("--semanas", type=int, default=4, help="Corridas simuladas, una por semana (default 4)")
        parser.add_argument("--horizonte", type=int, default=7, help="Dias evaluados por corrida (default 7)")
        parser.add_argument("--hasta", help="Ultimo dia evaluado, YYYY-MM-DD (default: ayer)")
        parser.add_argument("--producto", type=int, help="Solo este product_id")
        parser.add_argument("--salida", help="Guarda el detalle por producto en este JSON")
        parser.add_argument("--comparar", help="JSON de una corrida anterior: imprime la diferencia")
        parser.add_argument("--etiqueta", default="", help="Nombre de la corrida (aparece en el titulo)")

    def handle(self, *args, **o):
        tenant = Tenant.objects.filter(id=o["tenant"]).first()
        if tenant is None:
            raise CommandError("No existe el tenant %s" % o["tenant"])
        hasta = date.fromisoformat(o["hasta"]) if o.get("hasta") else date.today() - timedelta(days=1)
        horizonte, semanas = max(1, o["horizonte"]), max(1, o["semanas"])
        perfil = _perfil(tenant)
        window, min_days = max(7, perfil["window"]), max(7, perfil["min_days"])

        t0 = time.time()
        productos = productos_a_evaluar(tenant, hasta, o.get("producto"))
        nucleo = nucleo_de_ventas(tenant, hasta)
        desde_eval = hasta - timedelta(days=horizonte * semanas - 1)
        ventas = defaultdict(float)
        for pid, wh, d, q in DailySales.objects.filter(
            tenant=tenant, date__gte=desde_eval, date__lte=hasta,
        ).values_list("product_id", "warehouse_id", "date", "qty_sold"):
            ventas[(pid, wh, d)] += float(q or 0)

        resultados = []
        for k, (pid, wh, nombre) in enumerate(productos, 1):
            product = Product.objects.get(id=pid)
            r = backtest_producto(
                tenant, product, wh, hasta, horizonte, semanas, window, min_days,
                ventas, pid in nucleo, avisar=self.stderr.write,
            )
            if r:
                resultados.append(r)
            if o.get("verbosity", 1) >= 2 and k % 20 == 0:
                self.stdout.write("  %d/%d productos (%.0fs)" % (k, len(productos), time.time() - t0))

        salida = {
            "meta": {
                "tenant": tenant.id, "etiqueta": o["etiqueta"], "hasta": hasta.isoformat(),
                "semanas": semanas, "horizonte": horizonte, "window": window,
                "min_days": min_days, "productos": len(resultados),
                "generado": date.today().isoformat(),
            },
            "productos": resultados,
        }
        self._imprimir(salida, o.get("comparar"), time.time() - t0)
        if o.get("salida"):
            with open(o["salida"], "w", encoding="utf-8") as fh:
                json.dump(salida, fh, ensure_ascii=False, indent=1)
            self.stdout.write("  detalle guardado en %s" % o["salida"])

    # ── salida ───────────────────────────────────────────────────────────
    def _imprimir(self, salida, ruta_base, segundos):
        m = salida["meta"]
        titulo = "=== Backtest fiel%s | tenant %s | %d semanas de %d dias hasta %s | %d productos | %.0fs ===" % (
            (" [%s]" % m["etiqueta"]) if m["etiqueta"] else "", m["tenant"], m["semanas"],
            m["horizonte"], m["hasta"], m["productos"], segundos,
        )
        self.stdout.write(titulo)
        ahora = agregar(salida["productos"])
        if not ruta_base:
            self.stdout.write("  %-18s %5s | %7s %7s" % ("segmento", "n", "WAPE", "sesgo"))
            for s in _orden_segmentos(ahora):
                x = ahora[s]
                self.stdout.write("  %-18s %5d | %s %s" % (s, x[3], _pct(_wape(x)), _pct(_sesgo(x), signo=True)))
        else:
            with open(ruta_base, encoding="utf-8") as fh:
                base_json = json.load(fh)
            base = agregar(base_json["productos"])
            bm = base_json.get("meta", {})
            self.stdout.write("  base: %s (%s, hasta %s, %s productos)" % (
                ruta_base, bm.get("etiqueta") or "sin etiqueta", bm.get("hasta"), bm.get("productos")))
            self.stdout.write("  %-18s %5s | %7s %7s %9s | %7s %7s" % (
                "segmento", "n", "base", "ahora", "delta", "sesgo b", "sesgo a"))
            for s in _orden_segmentos(set(ahora) | set(base)):
                a, b = ahora.get(s), base.get(s)
                wa, wb = (_wape(a) if a else None), (_wape(b) if b else None)
                delta = ("%+8.1f pt" % (wa - wb)) if (wa is not None and wb is not None) else "         -"
                self.stdout.write("  %-18s %5d | %s %s %s | %s %s" % (
                    s, (a or b)[3], _pct(wb), _pct(wa), delta,
                    _pct(_sesgo(b) if b else None, signo=True), _pct(_sesgo(a) if a else None, signo=True)))
            por_clave = {(p["product_id"], p["warehouse_id"]): p for p in base_json["productos"]}
            mejoran = empeoran = iguales = 0
            for p in salida["productos"]:
                q = por_clave.get((p["product_id"], p["warehouse_id"]))
                if q is None:
                    continue
                if p["abs"] < q["abs"] - 1e-6:
                    mejoran += 1
                elif p["abs"] > q["abs"] + 1e-6:
                    empeoran += 1
                else:
                    iguales += 1
            self.stdout.write("  productos que mejoran: %d | empeoran: %d | iguales: %d" % (mejoran, empeoran, iguales))
        ganadores = Counter(p["alg"] for p in salida["productos"]).most_common(8)
        self.stdout.write("  algoritmos elegidos: %s" % ", ".join("%s=%d" % kv for kv in ganadores))
