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

from django.core.management.base import CommandError



class FallaParcial(CommandError):
    """Algunos negocios fallaron, pero otros terminaron bien.

    Hereda de CommandError a proposito: sigue siendo un fallo del comando y
    tiene que devolver exit != 0 para que el cron lo registre. Lo que cambia
    es la LECTURA que hace la salud de la plataforma.

    Existe para que el heartbeat pueda distinguir "un cliente tiene un
    problema" de "la tarea entera se cayo". Sin esa distincion, un solo local
    con una receta rota pone en rojo la salud de toda la plataforma, y una
    alarma que suena siempre es una alarma que nadie mira.
    """

    def __init__(self, mensaje, ok=0, fallidos=0):
        super().__init__(mensaje)
        self.ok = ok
        self.fallidos = fallidos


def tenants_a_procesar(options, command=None):
    """Los negocios que el pipeline nocturno debe recorrer.

    Filtra los inactivos —un negocio dado de baja no necesita modelos— para
    que el pipeline coincida con `send_low_stock_alerts`, que ya filtraba.
    Antes no coincidian: las alertas salteaban inactivos y el forecast no.

    Reporta cuantos saltea. Eso NO es cosmetico: si alguien desactiva un
    negocio por error, su pronostico deja de calcularse, y sin esta linea el
    silencio seria identico al de todo funcionando bien.
    """
    from core.models import Tenant

    todos = Tenant.objects.all()
    if options.get("tenant"):
        # Con --tenant explicito se respeta la eleccion aunque este inactivo:
        # el flag se usa justamente para reprocesar casos raros a mano.
        elegidos = todos.filter(id=options["tenant"])
        if command is not None and not elegidos.exists():
            command.stderr.write(command.style.WARNING(
                f"No existe el negocio {options['tenant']}."
            ))
        return elegidos

    activos = todos.filter(is_active=True)
    salteados = todos.count() - activos.count()
    if salteados and command is not None:
        command.stdout.write(
            f"Se saltean {salteados} negocio(s) inactivo(s)."
        )
    return activos


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
    total = ok + len(fallidos)
    if command is not None:
        command.stdout.write(
            f"Negocios procesados: {ok} de {total}"
            + (f" — {len(fallidos)} con error" if fallidos else "")
        )

    if not fallidos:
        return

    detalle = "; ".join(f"{t.name} (id {t.id}): {e}" for t, e in fallidos[:5])
    if len(fallidos) > 5:
        detalle += f" … y {len(fallidos) - 5} mas"
    mensaje = f"{len(fallidos)} de {total} negocios fallaron. {detalle}"

    # La distincion que decide si esto despierta a alguien de madrugada.
    #
    # Si NINGUNO se proceso, la tarea esta caida: se rompio algo comun —la
    # base, una migracion a medias, un import— y hay que mirarlo ya.
    #
    # Si algunos terminaron bien, el problema es de esos clientes puntuales.
    # Importa y hay que arreglarlo, pero la plataforma esta de pie y no
    # justifica una alarma de caida.
    if ok == 0:
        raise CommandError(mensaje)
    raise FallaParcial(mensaje, ok=ok, fallidos=len(fallidos))
