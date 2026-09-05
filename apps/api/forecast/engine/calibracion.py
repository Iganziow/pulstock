"""
Calibración empírica de las bandas de confianza.

El problema medido (Marbrava, 04/09/26, 4.599 mediciones de 30 días)
----------------------------------------------------------------------
Cada algoritmo publica un piso y un techo por día, y con ellos se decide el
stock de seguridad y el "quiebre conservador" de los modelos con confianza
baja. Nadie había medido si esas bandas aciertan. Una banda "del 80%" debería
contener el 80% de los días reales:

    algoritmo            dentro   real bajo el piso   ancho / predicción
    total                  43%          48%                 4,4x
    croston                 3%          85%                 1,1x
    theta                  61%          36%                18,4x
    derivado (núcleo)      23%          46%                 0,6x

Dos defectos a la vez: el piso está por ENCIMA de la realidad la mitad de
los días (la sobrepredicción vista desde otro ángulo), y el ancho es
arbitrario, de 0,6x a 18x según el algoritmo. El techo de 18x de theta es el
que le decía a Chocolate Premium "quiebre en 5 días" con 18 días de stock.

La técnica
----------
Intervalos conformales en su forma más simple: para cada producto se toman
los últimos 28 días de mediciones reales, se calcula el cociente
real / predicho de cada día, y los cuantiles 10 y 90 de esos cocientes son
el piso y el techo, como múltiplos de la predicción. No toca la predicción
puntual ni ningún algoritmo: corrige piso y ancho de una vez con la única
fuente de verdad que hay, los errores que el modelo cometió de verdad.

Validado FUERA DE MUESTRA sobre producción (cuantiles con los días 56..29,
evaluados en los días 28..1), 2.486 mediciones:

    algoritmo            cobertura actual   calibrada   ancho actual   calibrado
    total                      33%             92%          2,1x          0,8x
    croston                     2%             92%          1,1x          0,8x
    theta                      42%             92%          8,3x          1,0x
    derivado (núcleo)          24%             79%          0,6x          1,8x

Decisiones
----------
- Mínimo 10 mediciones; con menos, el producto conserva la banda propia del
  algoritmo. Los días de quiebre (was_stockout) no entran: la venta real
  estaba censurada.
- Techo acotado a [0,25 ; 3,0] veces la predicción. El tope evita bandas que
  no dicen nada; el piso evita que un modelo muy malo colapse su techo a
  cero y esconda un quiebre real. El piso del intervalo nunca es negativo y
  nunca supera al techo.
- Los días con predicción 0 (cerrados, demanda detenida) quedan en 0.
- Apagado de emergencia: variable de entorno FORECAST_CALIBRACION_OFF=1.
"""
from decimal import Decimal

from .utils import _q3

Q_LO = 0.10
Q_HI = 0.90
MIN_N = 10
CAP_HI = 3.0
FLOOR_HI = 0.25
VENTANA_DIAS = 28


def cuantil(valores, q):
    """Cuantil lineal (como numpy por defecto) sin depender de numpy."""
    xs = sorted(float(v) for v in valores)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    i = int(k)
    f = k - i
    if i + 1 >= len(xs):
        return xs[i]
    return xs[i] + (xs[i + 1] - xs[i]) * f


def factores_de_calibracion(razones, q_lo=Q_LO, q_hi=Q_HI, min_n=MIN_N,
                            cap_hi=CAP_HI, floor_hi=FLOOR_HI):
    """Piso y techo como múltiplos de la predicción, o None si no hay datos.

    `razones` son cocientes real / predicho de días pasados (predicho > 0).
    """
    limpias = [float(r) for r in razones if r is not None and float(r) >= 0]
    if len(limpias) < min_n:
        return None
    lo = max(0.0, cuantil(limpias, q_lo))
    hi = cuantil(limpias, q_hi)
    hi = min(cap_hi, max(floor_hi, hi))
    lo = min(lo, hi)
    return {"q_lo": round(lo, 3), "q_hi": round(hi, 3), "n": len(limpias)}


def aplicar_calibracion(forecasts, factores):
    """Reemplaza piso y techo de cada día por predicción x cuantil. In place."""
    if not factores:
        return forecasts
    lo = Decimal(str(factores["q_lo"]))
    hi = Decimal(str(factores["q_hi"]))
    for fc in forecasts:
        p = fc.get("qty_predicted")
        if p is None or p <= 0:
            continue  # cerrado o demanda detenida: la banda queda en 0
        fc["lower_bound"] = _q3(p * lo)
        fc["upper_bound"] = _q3(p * hi)
    return forecasts
