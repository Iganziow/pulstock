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
- Techo acotado a 3,0 veces la predicción: una banda de 50x no dice nada.
- La banda SIEMPRE contiene a su predicción (07/09/26). Medido en producción
  el 07-09: 953 de 2.659 filas futuras (40 productos) tenían la predicción
  POR ENCIMA de su propio techo, porque en un modelo que sobre-predice de
  forma sistemática hasta el cuantil 90 del cociente queda bajo 1 y el techo
  colapsaba a 0,25x. La pantalla decía "vas a vender 70 g" y debajo "entre 0
  y 18 g"; el proyector de stock y la sugerencia leen ese techo. El intervalo
  se ensancha hasta contener la predicción (nunca se angosta: la cobertura
  medida sólo puede mejorar) y se deja la marca `sesgo` con el cuantil crudo,
  porque un intervalo que no contiene al 1 no es un problema de la banda sino
  del punto: ese modelo predice sistemáticamente de más o de menos, y eso se
  corrige en la predicción, con backtest fiel, no ensanchando la banda.
- El piso del intervalo nunca es negativo y nunca supera al techo.
- Los días con predicción 0 (cerrados, demanda detenida) quedan en 0.
- Apagado de emergencia: variable de entorno FORECAST_CALIBRACION_OFF=1.
"""
from decimal import Decimal

from .utils import _q3

Q_LO = 0.10
Q_HI = 0.90
MIN_N = 10
CAP_HI = 3.0
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
                            cap_hi=CAP_HI):
    """Piso y techo como múltiplos de la predicción, o None si no hay datos.

    `razones` son cocientes real / predicho de días pasados (predicho > 0).

    El intervalo devuelto siempre contiene al 1, o sea a la predicción (ver
    el encabezado del módulo). Cuando el cuantil crudo dice otra cosa, el
    intervalo se ensancha y queda la marca `sesgo`: "sobre" si el modelo
    predice de más todos los días, "bajo" si predice de menos.
    """
    limpias = [float(r) for r in razones if r is not None and float(r) >= 0]
    if len(limpias) < min_n:
        return None
    lo = max(0.0, cuantil(limpias, q_lo))
    hi = min(cap_hi, cuantil(limpias, q_hi))
    lo = min(lo, hi)

    # La banda contiene a la predicción. Ensancha, nunca angosta.
    f = {"q_lo": round(min(lo, 1.0), 3), "q_hi": round(max(hi, 1.0), 3),
         "n": len(limpias)}
    if hi < 1.0:
        f["sesgo"] = "sobre"
        f["q_crudo"] = round(hi, 3)
    elif lo > 1.0:
        f["sesgo"] = "bajo"
        f["q_crudo"] = round(lo, 3)
    return f


def aplicar_calibracion(forecasts, factores):
    """Reemplaza piso y techo de cada día por predicción x cuantil. In place.

    Aunque `factores_de_calibracion` ya garantiza que el intervalo contiene
    al 1, el recorte se repite acá sobre los números finales: es la última
    línea antes de la tabla, y unos factores viejos guardados en
    `model_params` no pueden romper la invariante piso <= predicción <= techo.
    """
    if not factores:
        return forecasts
    lo = Decimal(str(factores["q_lo"]))
    hi = Decimal(str(factores["q_hi"]))
    for fc in forecasts:
        p = fc.get("qty_predicted")
        if p is None or p <= 0:
            continue  # cerrado o demanda detenida: la banda queda en 0
        fc["lower_bound"] = min(_q3(p * lo), _q3(p))
        fc["upper_bound"] = max(_q3(p * hi), _q3(p))
    return forecasts
