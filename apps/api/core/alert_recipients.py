"""
core.alert_recipients — a quien le llega cada alerta por correo.

El problema que resuelve
------------------------
Los dos comandos de alerta hacian `User.objects.filter(role="owner").first()`:
le llegaba a UNA sola persona. En Marbrava eso significaba que Mario recibia
todo y sus cuatro encargados activos, nada — cuando el que hace las compras
suele ser el encargado, no el dueno. La persona que puede actuar se enteraba
por WhatsApp.

Ademas el modelo `AlertPreference` ya tenia toggles POR USUARIO y una pantalla
en Configuracion para marcarlos, pero el envio no los miraba: solo servian para
que el unico dueno apagara su propia alerta. Media funcion.

Aca vive la regla, en un solo lugar, para que los dos comandos —y los que
vengan— no la reimplementen distinto.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Quienes pueden recibir alertas operativas. Un cajero no compra insumos ni
# decide reposicion: mandarle la alerta seria ruido para el y una fuga de
# informacion de margenes que su rol no necesita.
ROLES_QUE_RECIBEN = ("owner", "manager")


def destinatarios(tenant, preferencia: str) -> list:
    """Usuarios del tenant que deben recibir la alerta `preferencia`.

    `preferencia` es el nombre del campo en AlertPreference (p.ej. "stock_bajo").
    Si el usuario todavia no tiene fila de preferencias se usa el default del
    modelo: no lo excluimos por no haber entrado nunca a Configuracion.
    """
    from core.models import AlertPreference, User

    usuarios = (
        User.objects
        .filter(tenant=tenant, is_active=True, role__in=ROLES_QUE_RECIBEN)
        .exclude(email="")
        .exclude(email__isnull=True)
        .order_by("id")
    )
    if not usuarios:
        return []

    prefs = {
        p.user_id: p
        for p in AlertPreference.objects.filter(user__in=usuarios)
    }
    default = getattr(AlertPreference, preferencia).field.default

    elegidos = []
    for u in usuarios:
        p = prefs.get(u.id)
        quiere = getattr(p, preferencia) if p else default
        if quiere:
            elegidos.append(u)

    # Un mismo correo puede estar en dos cuentas (el dueno que ademas figura
    # como encargado). Mandar dos veces lo mismo se lee como sistema roto.
    vistos, unicos = set(), []
    for u in elegidos:
        clave = u.email.strip().lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(u)
    return unicos
