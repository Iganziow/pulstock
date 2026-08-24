"""
core.multi_tenant — recorrer todos los negocios sin que uno tumbe a los demas.

El problema que resuelve
------------------------
El pipeline nocturno recorre los tenants con un `for` pelado:

    for tenant in tenants:
        self._process_tenant(tenant, ...)

Con UN cliente eso funciona: si falla, falla el unico que hay y se ve en el
log. Con tres, la excepcion del primero corta el `for` y los otros dos **no se
procesan** — no se entrenan modelos, no se generan sugerencias, no se agrega
demanda. Y no hay error visible por ninguno de ellos: el comando muere una
sola vez, por el primero, y el resto simplemente no aparece en ningun lado.

Peor todavia: cual sobrevive depende del ORDEN del queryset. El mismo fallo
deja distintos clientes sin pronostico segun por donde empiece.

Que hace este helper
--------------------
Aisla cada tenant. Si uno explota, se anota y se sigue con el siguiente, asi
que un cliente roto nunca le quita el servicio a los demas.

Y despues **falla igual**. Eso es deliberado: `with_heartbeat` re-lanza y marca
el heartbeat como "failed", que es lo que hace que `/api/core/health/deep/`
pase a "degraded". Tragarse el error dejaria a los otros tenants andando pero
al roto invisible — cambiariamos una falla ruidosa por una silenciosa, que es
justo lo que estamos tratando de sacar del sistema.
"""
from __future__ import annotations

import traceback
from typing import Callable, Iterable


def por_tenant(
    tenants: Iterable,
    procesar: Callable,
    *,
    command=None,
) -> tuple[int, list[tuple]]:
    """Ejecuta `procesar(tenant)` para cada tenant, aislando las fallas.

    Devuelve `(procesados_ok, fallidos)` donde `fallidos` es una lista de
    tuplas `(tenant, excepcion)`.

    El que llama decide que hacer con los fallidos — normalmente
    `exigir_todos()`, que levanta para que quede registrado en el heartbeat.
    """
    ok = 0
    fallidos: list[tuple] = []

    for tenant in tenants:
        try:
            procesar(tenant)
            ok += 1
        except Exception as exc:  # noqa: BLE001 — aislar es el objetivo
            fallidos.append((tenant, exc))
            if command is not None:
                command.stderr.write(
                    command.style.ERROR(
                        f"  ERROR en tenant {tenant.id} ({tenant.name}): {exc}"
                    )
                )
            # El traceback completo va al log del cron: sin el, un fallo de un
            # solo cliente es imposible de diagnosticar despues.
            traceback.print_exc()

    return ok, fallidos


def exigir_todos(ok: int, fallidos: list[tuple], command=None) -> None:
    """Levanta si algun tenant fallo, despues de haber procesado a todos.

    Se llama al FINAL, nunca dentro del bucle: el objetivo es que los sanos
    terminen su trabajo y que el fallo igual quede visible.
    """
    from django.core.management.base import CommandError

    total = ok + len(fallidos)
    if command is not None:
        command.stdout.write(
            f"Negocios procesados: {ok} de {total}"
            + (f" — {len(fallidos)} con error" if fallidos else "")
        )

    if fallidos:
        detalle = "; ".join(
            f"{t.name} (id {t.id}): {e}" for t, e in fallidos[:5]
        )
        if len(fallidos) > 5:
            detalle += f" … y {len(fallidos) - 5} mas"
        raise CommandError(
            f"{len(fallidos)} de {total} negocios fallaron. {detalle}"
        )
