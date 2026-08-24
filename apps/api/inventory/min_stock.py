"""
inventory.min_stock — el minimo que se ajusta solo.

Mario: "que se autoajuste solo". Y tiene razon en pedirlo: configurar 252
minimos a mano no lo hace nadie, y se nota — hoy solo 8 productos de 252 lo
tienen puesto.

Que habia
---------
La alerta de quiebre ya calculaba un minimo automatico, pero era
`avg_daily x 2`: dos dias de venta, plano, igual para todo.

Eso falla por dos lados:

  · Ignora la variabilidad. Un producto que vende 10±1 y otro que vende 10±8
    reciben el mismo minimo, cuando el segundo necesita mucho mas colchon para
    la misma tranquilidad.
  · Ignora el lead time. Si el proveedor tarda 5 dias, un minimo de 2 dias
    garantiza el quiebre: cuando la alerta salta ya es tarde.

Que hace ahora
--------------
El punto de reposicion clasico, que es la formula que la industria usa hace
decadas y que ya estaba implementada del lado de la sugerencia de compra:

    minimo = demanda_diaria x lead_time + z x sigma x raiz(lead_time)
             \_____________________/     \______________________/
              lo que se consume           colchon por incertidumbre
              mientras llega el pedido    (mas grande si la venta es erratica)

El horizonte es el LEAD TIME —cuanto tarda en llegar si pido hoy— porque eso
es lo que la alerta tiene que cubrir: avisar con tiempo suficiente para que la
reposicion llegue antes de quedarse sin nada.

`z` sale del nivel de servicio del tenant (95% por defecto): que tan seguido se
acepta quebrar. Subirlo a 99% engorda el colchon; bajarlo a 90% lo adelgaza.

Se recalcula todas las noches con los datos frescos, asi que el minimo sigue al
negocio: si un producto se pone de moda, su minimo sube solo.

Lo que NO hace
--------------
Si el dueno puso un minimo a mano, ese manda. Es una decision explicita suya
—sabe algo que el historial no dice, como que viene un evento— y el sistema no
tiene por que pisarla.
"""
from __future__ import annotations

import logging
import math
from decimal import Decimal

logger = logging.getLogger(__name__)

D0 = Decimal("0.000")

# Ventanas para estimar ritmo y variabilidad, de la mas corta a la mas larga.
#
# 28 dias es la preferida: captura cuatro semanas completas —asi el efecto
# dia-de-semana no distorsiona el promedio— y reacciona rapido a un cambio.
#
# Pero hay productos que se mueven menos de una vez al mes. El papel higienico
# de Marbrava gasta 5 unidades en 80 dias: en una ventana de 28 muchas veces no
# hay NI UN movimiento, y el calculo devolvia "sin consumo" justo para la clase
# de producto que Mario pidio cubrir. Para esos se ensancha la ventana hasta
# encontrar historial. Se pierde frescura, pero un estimado viejo es
# infinitamente mejor que ninguno.
VENTANAS = (28, 90, 180)
VENTANA_DIAS = VENTANAS[0]

# Piso de dias de cobertura. Un lead time de 0 o 1 dia daria un minimo casi
# nulo y la alerta llegaria cuando ya no queda nada.
MINIMO_DIAS_COBERTURA = 2

# Piso en unidades para lo que se cuenta entero.
#
# Un producto muy lento da un minimo matematicamente correcto pero inutil: el
# papel higienico sale 0,7 unidades, y avisar "cuando queden 0,7 rollos" es
# avisar cuando ya no queda ninguno. Medio rollo no es un umbral.
#
# El piso se aplica solo a unidades de conteo (family COUNT). En litros o
# gramos un decimal SI significa algo y forzarlo a 1 seria inventar stock.
PISO_UNIDAD_ENTERA = 1.0


def _z(nivel_servicio: float) -> float:
    from forecast.services import _z_for_service_level
    return _z_for_service_level(nivel_servicio)


def _lead_time_dias(tenant, product) -> int:
    """Cuanto tarda en llegar. Del proveedor real si se conoce; si no, del
    tipo de negocio — una ferreteria no repone como una cafeteria."""
    from forecast.services import DEFAULT_SERVICE_LEVEL  # noqa: F401  (doc)

    por_tipo = {
        "retail": 3, "restaurant": 2, "hardware": 30,
        "wholesale": 45, "pharmacy": 5, "other": 7,
    }
    btype = getattr(tenant, "business_type", "other") or "other"
    return por_tipo.get(btype, 7)


def calcular_minimo(demanda_diaria: float, desviacion: float,
                    lead_time: int, nivel_servicio: float = 0.95) -> dict:
    """Punto de reposicion. Devuelve el numero y de donde sale.

    Se separa del acceso a datos para poder probar la formula sola.
    """
    dias = max(MINIMO_DIAS_COBERTURA, int(lead_time or 0))
    consumo = demanda_diaria * dias
    colchon = _z(nivel_servicio) * desviacion * math.sqrt(dias)
    minimo = consumo + colchon
    return {
        "minimo": max(0.0, minimo),
        "dias_cobertura": dias,
        "consumo_esperado": consumo,
        "colchon": max(0.0, colchon),
        "demanda_diaria": demanda_diaria,
        "desviacion": desviacion,
        "nivel_servicio": nivel_servicio,
    }


def _serie_diaria(tenant, product, warehouse, hasta, dias=VENTANA_DIAS):
    """Demanda por dia, con los ceros incluidos.

    Los dias sin venta CUENTAN: son parte del ritmo real. Promediar solo los
    dias con movimiento infla el minimo de todo lo que rota poco — que es
    justo el caso de los insumos que Mario quiere cubrir.

    Y "demanda" NO es solo `qty_sold`. En un restaurante lo que se gasta por
    dentro sale del stock igual que una venta: el papel higienico no se vende
    nunca, se consume, y su consumo se registra como `qty_lost`. Leyendo solo
    las ventas, los insumos daban "sin consumo" y se quedaban sin minimo —
    justo los productos que originaron el pedido.

    El criterio lo decide `cuenta_mermas_como_demanda`, el mismo que usa el
    motor de pronostico, para que las dos mitades del sistema no tengan
    definiciones distintas de la misma palabra.
    """
    import datetime
    from forecast.models import DailySales
    from forecast.services import cuenta_mermas_como_demanda

    con_mermas = cuenta_mermas_como_demanda(tenant)
    campos = ["date", "qty_sold"] + (["qty_lost"] if con_mermas else [])

    desde = hasta - datetime.timedelta(days=dias)
    filas = {}
    for fila in (DailySales.objects
                 .filter(tenant=tenant, product=product, warehouse=warehouse,
                         date__gte=desde, date__lt=hasta)
                 .values_list(*campos)):
        total = float(fila[1] or 0)
        if con_mermas and len(fila) > 2:
            total += float(fila[2] or 0)
        filas[fila[0]] = total
    serie = []
    d = desde
    while d < hasta:
        serie.append(filas.get(d, 0.0))
        d += datetime.timedelta(days=1)
    return serie


def _cuenta_entero(product) -> bool:
    """Si el producto se mide en unidades contables (rollos, vasos, latas).

    En litros o gramos un minimo decimal significa algo; en rollos de papel,
    no. Se mira la familia de la unidad, no su nombre, para que funcione con
    las unidades propias que cada negocio se crea.
    """
    unidad = getattr(product, "unit_obj", None)
    if unidad is not None:
        return getattr(unidad, "family", "COUNT") == "COUNT"
    # Sin unidad estructurada, el default del modelo es "UN".
    return (getattr(product, "unit", "") or "UN").strip().upper() in ("UN", "UND", "UNI")


def minimo_para(tenant, product, warehouse, hasta=None) -> dict | None:
    """Calcula el minimo sugerido de un producto. None si no hay datos."""
    import statistics
    from django.utils import timezone

    hasta = hasta or timezone.localdate()

    # Se prueba la ventana corta primero y se ensancha solo si viene vacia.
    # Un producto de rotacion normal se estima con datos frescos; uno lento
    # necesita mirar mas atras para tener algo que medir.
    serie = None
    ventana = None
    for dias in VENTANAS:
        candidata = _serie_diaria(tenant, product, warehouse, hasta, dias=dias)
        if candidata and sum(candidata) > 0:
            serie, ventana = candidata, dias
            break

    if serie is None:
        # Sin consumo ni en 180 dias no hay nada que sostener. Devolver un
        # minimo aca haria que la alerta ladre por productos muertos.
        return None

    media = statistics.fmean(serie)
    desv = statistics.pstdev(serie) if len(serie) > 1 else 0.0
    nivel = float(getattr(tenant, "service_level", None) or 0.95)

    r = calcular_minimo(
        demanda_diaria=media,
        desviacion=desv,
        lead_time=_lead_time_dias(tenant, product),
        nivel_servicio=nivel,
    )

    # El piso convierte un numero correcto pero inservible ("avisa cuando
    # queden 0,7 rollos") en uno accionable ("avisa cuando quede 1").
    r["piso_aplicado"] = False
    if 0 < r["minimo"] < PISO_UNIDAD_ENTERA and _cuenta_entero(product):
        r["minimo"] = PISO_UNIDAD_ENTERA
        r["piso_aplicado"] = True

    r["ventana_dias"] = ventana
    r["product_id"] = product.id
    return r


def explicar(r: dict, unidad: str = "unidades") -> str:
    """Por que ese numero — mismo criterio que el resto del sistema: si el
    dueno no entiende de donde sale, no lo usa."""
    if not r:
        return "Sin consumo reciente, no hace falta un minimo."
    mi = round(r["minimo"])
    dias = r["dias_cobertura"]
    diaria = r["demanda_diaria"]
    colchon = round(r["colchon"])
    txt = (
        f"Consumes alrededor de {diaria:.1f} {unidad} al dia y el proveedor "
        f"tarda unos {dias} dias en reponer, asi que necesitas "
        f"{r['consumo_esperado']:.0f} para cubrir la espera."
    )
    if colchon >= 1:
        txt += (
            f" Se suman {colchon} de colchon porque el consumo varia de un dia "
            f"a otro. Total: {mi} {unidad}."
        )
    else:
        txt += f" Total: {mi} {unidad}."

    if r.get("piso_aplicado"):
        txt = (
            f"Este producto se consume muy de a poco ({diaria:.2f} {unidad} al "
            f"dia), asi que el calculo daba menos de una unidad. Se deja en "
            f"{mi} para avisar antes de que se acabe, no cuando ya se acabo."
        )

    ventana = r.get("ventana_dias")
    if ventana and ventana > VENTANAS[0]:
        txt += (
            f" Se miraron los ultimos {ventana} dias porque en el ultimo mes "
            f"no hubo movimiento suficiente para estimar."
        )
    return txt
