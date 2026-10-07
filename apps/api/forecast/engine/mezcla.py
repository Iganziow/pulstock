# -*- coding: utf-8 -*-
"""
forecast/engine/mezcla.py — lo que publica el modelo, mezclado con el nivel de
los ultimos 28 dias abiertos.

    prediccion(dia) = PESO_MODELO x modelo(dia) + (1 - PESO_MODELO) x nivel

Por que existe (medido en produccion el 21-sep-2026, ventana 30-jun a 13-sep,
demanda efectiva, lo PUBLICADO a horizonte 1 contra reglas aplicables el dia
anterior):

    producto            modelo   promedio 28 dias
    Leche entera          45%          36%
    Cafe tolva caturra    42%          38%
    Chocolate Premium     67%          62%
    TOTAL DEL NUCLEO      48%          38%     <- le gana en los SEIS productos

Y mezclando las dos con un peso k para el modelo:

    k             0      0,25    0,5    0,75     1
    nucleo       38%     39%     39%    40%     42%
    cola         57%     56%     56%    57%     60%

El modelo acierta el NIVEL (error de nivel 11-12% en los grandes) y erra la
FORMA: la correlacion entre la forma que le pone a los dias y la de la demanda
es ~0 (+0,01 en leche entera), y la media por dia de semana da 79%, peor que la
constante. Su trabajo de repartir entre dias resta en vez de sumar. A 7 dias,
que es como se compra, el nucleo pasa de 17% a 11%.

Se usa 0,25 y no el 0 del optimo: esta a un punto del optimo en el nucleo, es
el optimo en la cola, y deja algo de la forma del modelo por si la conclusion de
"no hay señal semanal" no sobrevive a que P3 destape las bebidas que estaban
censuradas cuando se midio. Ademas un promedio de 28 dias se mueve lento por
construccion, asi que esto tambien achica el salto de una noche a la otra.

CAUTELA. Los numeros son de jun-sep con un motor mas viejo, y `nivel_dia_semana`
ganaba todas sus mediciones aisladas y perdio siete noches de sombra. Esto no se
cree hasta medirlo en la sombra.

Esta parte es pura (sin base de datos). Que dias cuentan para el nivel y a que
modelos se aplica lo decide `forecast.services.nivel_para_mezcla`.
"""
from decimal import Decimal, ROUND_HALF_UP

PESO_MODELO = Decimal("0.25")
DIAS_NIVEL = 28
# De los 28 dias abiertos, cuantos tienen que tener demanda medible (no quiebre
# real, no dia todo-promo). Con menos, el nivel sale de muy pocos dias.
MIN_DIAS_MEDIBLES = 21

D0 = Decimal("0")
Q = Decimal("0.001")


def _dec(x):
    return x if isinstance(x, Decimal) else Decimal(str(x or 0))


def nivel(demandas):
    """Promedio simple de las demandas diarias dadas, o None si no hay."""
    if not demandas:
        return None
    return sum((_dec(d) for d in demandas), D0) / len(demandas)


def mezclar_con_nivel(daily_forecasts, nivel_diario, closed_dows, peso_modelo=PESO_MODELO):
    """Mezcla en el lugar cada dia del pronostico con el nivel.

    En un dia de semana cerrado del negocio el objetivo es 0, no el nivel: la
    mascara de dias cerrados de `save_forecasts` despues pone ese dia en 0 y
    reparte lo que quede en los dias abiertos, igual que con el modelo solo.

    La banda se corre junto con el punto y conserva su ancho: la mezcla cambia
    donde se centra el pronostico, no cuanta incertidumbre tiene. El piso no
    baja de 0 ni sube por encima del punto; el techo no queda por debajo.
    """
    peso = _dec(peso_modelo)
    nivel_diario = _dec(nivel_diario)
    for fc in daily_forecasts:
        pred = _dec(fc["qty_predicted"])
        objetivo = D0 if fc["date"].weekday() in (closed_dows or ()) else nivel_diario
        nuevo = (peso * pred + (1 - peso) * objetivo).quantize(Q, rounding=ROUND_HALF_UP)
        delta = nuevo - pred
        piso = _dec(fc.get("lower_bound", pred)) + delta
        techo = _dec(fc.get("upper_bound", pred)) + delta
        fc["qty_predicted"] = nuevo
        fc["lower_bound"] = max(D0, min(nuevo, piso.quantize(Q, rounding=ROUND_HALF_UP)))
        fc["upper_bound"] = max(nuevo, techo.quantize(Q, rounding=ROUND_HALF_UP))
    return daily_forecasts
