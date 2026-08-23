"""
inventory.offline_sales — cuadrar el stock tras vender sin sistema.

El pedido de Mario, textual:

    "Se necesita poder ajustar inventario tras periodos de venta sin sistema de
    larga duracion (en caso de corte de luz, caida de sistema, etc), de manera
    que NO AFECTE LAS VENTAS DEL TURNO en que se realice la actualizacion."

Por que el ajuste normal no sirve
---------------------------------
`StockAdjust` crea un movimiento `ADJ/ADJUST` fechado HOY. Eso rompe las dos
cosas que a Mario le importan:

  1. El descuento cae en el turno actual. Si el corte fue el jueves y cuadra el
     sabado, el sabado aparece consumiendo 40 empanadas que se vendieron dos
     dias antes.

  2. El agregador del forecast lee `OUT/SALE`, `OUT/INTERNAL` y `OUT/ISSUE` —
     un `ADJ` es INVISIBLE. O sea: esas ventas nunca existieron para el modelo.
     La demanda del jueves queda en cero, el modelo aprende que ese dia se
     vende menos de lo que realmente se vende, y la sugerencia de compra pide
     de menos. El error se acumula en cada corte.

Que hace esto en cambio
-----------------------
Registra el consumo como lo que fue —una venta— con dos diferencias respecto de
una venta normal:

  · Va fechado en el DIA DEL CORTE, no hoy. El turno actual queda limpio.
  · Se marca `ref_type="OFFLINE"` para que se distinga en el kardex de una
    venta registrada por caja, y para que el agregador lo cuente como demanda.

NO crea `Sale` ni toca caja. La plata se cobro fuera del sistema y Mario la
concilia como corresponda; lo que esto arregla es el inventario y lo que el
modelo aprende. Mezclar ambas cosas obligaria a inventar medios de pago y a
reabrir sesiones de caja ya cerradas.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

REF_TYPE = "OFFLINE"
D0 = Decimal("0.000")


class ErrorVentaOffline(Exception):
    """Problema de validacion con datos que puede corregir el usuario."""


def registrar_ventas_offline(
    *, tenant, warehouse, usuario, fecha, lineas, nota: str = "",
):
    """Descuenta stock por ventas ocurridas mientras el sistema estaba caido.

    `fecha` es un `date`: el dia en que realmente se vendio.
    `lineas` es [{"product_id": int, "qty": Decimal}, ...].

    Devuelve un resumen con lo aplicado.
    """
    from catalog.models import Product
    from inventory.models import StockItem, StockMove

    hoy = timezone.localdate()
    if fecha > hoy:
        raise ErrorVentaOffline(
            "La fecha del corte no puede estar en el futuro."
        )
    # Un limite generoso pero real: mas alla de dos meses, reescribir la
    # historia hace mas dano que bien — el modelo ya se entreno con esos datos
    # y las sesiones de caja estan cerradas hace rato.
    if (hoy - fecha).days > 60:
        raise ErrorVentaOffline(
            "Solo se pueden registrar ventas de los ultimos 60 dias. "
            "Para periodos mas antiguos conviene un ajuste de inventario."
        )
    if not lineas:
        raise ErrorVentaOffline("No hay productos que registrar.")

    ids = [int(l["product_id"]) for l in lineas]
    productos = {
        p.id: p for p in Product.objects.filter(tenant=tenant, id__in=ids)
    }
    faltantes = set(ids) - set(productos)
    if faltantes:
        raise ErrorVentaOffline(
            "Hay productos que no existen o son de otro negocio: %s"
            % ", ".join(str(i) for i in sorted(faltantes))
        )

    # Se fecha al mediodia del dia del corte: cae dentro del dia en cualquier
    # huso y no compite con el cierre de caja de esa noche.
    momento = timezone.make_aware(
        timezone.datetime.combine(fecha, timezone.datetime.min.time())
    ) + timezone.timedelta(hours=12)

    aplicadas = []
    with transaction.atomic():
        for linea in lineas:
            pid = int(linea["product_id"])
            qty = Decimal(str(linea["qty"]))
            if qty <= 0:
                raise ErrorVentaOffline(
                    "La cantidad de %s debe ser mayor que cero."
                    % productos[pid].name
                )

            si, _ = StockItem.objects.select_for_update().get_or_create(
                tenant=tenant, warehouse=warehouse, product_id=pid,
                defaults={"on_hand": D0, "avg_cost": D0},
            )
            costo = si.avg_cost or D0

            # Si lo declarado supera lo que el sistema creia tener, el stock
            # NO queda negativo (hay un constraint en la base que lo prohibe, y
            # con razon: un inventario negativo corrompe costeo y valorizacion).
            #
            # Pero tampoco se recorta lo declarado: si Mario vendio 150, la
            # demanda del dia fue 150 y el modelo tiene que aprender eso. El
            # movimiento va completo y el stock queda en cero.
            #
            # La diferencia no se esconde: significa que el inventario YA estaba
            # mal antes del corte, y eso es justo lo que este flujo revela. Se
            # devuelve en `descuadres` para avisarlo.
            faltante = max(D0, qty - si.on_hand)
            si.on_hand = max(D0, si.on_hand - qty)
            si.stock_value = si.on_hand * costo
            si.save(update_fields=["on_hand", "stock_value"])

            StockMove.objects.create(
                tenant=tenant, warehouse=warehouse, product_id=pid,
                move_type=StockMove.OUT,
                qty=qty,
                unit_cost=costo,
                value_delta=-(qty * costo),
                ref_type=REF_TYPE,
                reason="VENTA_SIN_SISTEMA",
                note=nota or "Venta registrada tras caida del sistema",
                created_by=usuario,
                created_at=momento,
            )
            aplicadas.append({
                "product_id": pid,
                "nombre": productos[pid].name,
                "qty": str(qty),
                "stock_resultante": str(si.on_hand),
                "faltante": str(faltante),
            })

    logger.info(
        "Ventas offline registradas: tenant=%s fecha=%s lineas=%d usuario=%s",
        tenant.id, fecha, len(aplicadas), getattr(usuario, "username", "?"),
    )
    descuadres = [a for a in aplicadas if Decimal(a["faltante"]) > 0]
    if descuadres:
        logger.warning(
            "Ventas offline con descuadre previo: tenant=%s fecha=%s productos=%s",
            tenant.id, fecha, [d["nombre"] for d in descuadres],
        )
    return {
        "fecha": str(fecha),
        "lineas": aplicadas,
        # Productos donde lo declarado supero lo que el sistema tenia: el
        # inventario ya venia mal desde antes del corte.
        "descuadres": descuadres,
    }
