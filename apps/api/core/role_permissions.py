"""
Permisos por rol — editables por el dueño (estilo Fudo).

Modelo:
  - DEFAULT_ROLE_PERMISSIONS: el mapa base de fábrica (rol → permiso → bool).
  - Cada tenant puede sobrescribir permisos de los roles editables vía
    Tenant.role_permissions_overrides (JSON {role: {perm: bool}}).
  - effective_permissions(tenant, role) = base MERGE overrides.

Reglas de seguridad:
  - El rol OWNER siempre tiene TODO y NO es editable.
  - Los permisos `settings` y `users` NO son editables por la matriz
    (quedan solo para el dueño) — otorgarlos permitiría a otro rol editar
    la propia matriz de permisos = escalación de privilegios.
"""

# Orden y metadatos de los permisos, para que el frontend arme la matriz.
PERMISSION_META = [
    {"key": "pos",             "label": "Punto de venta",      "group": "Ventas"},
    {"key": "sales",           "label": "Ver ventas",          "group": "Ventas"},
    {"key": "caja",            "label": "Caja / arqueos",      "group": "Ventas"},
    {"key": "catalog",         "label": "Ver catálogo",        "group": "Productos"},
    {"key": "catalog_write",   "label": "Editar catálogo / precios / ofertas", "group": "Productos"},
    {"key": "inventory",       "label": "Ver inventario",      "group": "Inventario"},
    {"key": "inventory_write", "label": "Editar inventario",   "group": "Inventario"},
    {"key": "purchases",       "label": "Ver compras",         "group": "Inventario"},
    {"key": "purchases_write", "label": "Editar compras",      "group": "Inventario"},
    {"key": "reports",         "label": "Reportes",            "group": "Análisis"},
    {"key": "forecast",        "label": "Predicción de demanda", "group": "Análisis"},
]

ALL_PERMISSION_KEYS = [m["key"] for m in PERMISSION_META] + ["settings", "users"]

# Permisos que NO se pueden togglear desde la matriz (solo el dueño los tiene).
LOCKED_PERMISSIONS = {"settings", "users"}

# Roles cuyos permisos se pueden editar (owner queda fijo con todo).
EDITABLE_ROLES = ["manager", "cashier", "inventory"]

DEFAULT_ROLE_PERMISSIONS = {
    "owner": {
        "pos": True, "sales": True, "catalog": True, "catalog_write": True,
        "inventory": True, "inventory_write": True, "purchases": True,
        "purchases_write": True, "reports": True, "forecast": True,
        "settings": True, "users": True, "caja": True,
    },
    "manager": {
        "pos": True, "sales": True, "catalog": True, "catalog_write": True,
        "inventory": True, "inventory_write": True, "purchases": True,
        "purchases_write": True, "reports": True, "forecast": True,
        "settings": False, "users": False, "caja": True,
    },
    "cashier": {
        "pos": True, "sales": True, "catalog": True, "catalog_write": False,
        "inventory": False, "inventory_write": False, "purchases": False,
        "purchases_write": False, "reports": False, "forecast": False,
        "settings": False, "users": False, "caja": True,
    },
    "inventory": {
        # caja=True (Mario 27-jul): el rol Inventario necesita acceso a caja
        # sin tener que quedar como Administrador. Editable por el dueño.
        "pos": False, "sales": False, "catalog": True, "catalog_write": True,
        "inventory": True, "inventory_write": True, "purchases": True,
        "purchases_write": True, "reports": True, "forecast": False,
        "settings": False, "users": False, "caja": True,
    },
}


def _base_for(role):
    return dict(DEFAULT_ROLE_PERMISSIONS.get(role, DEFAULT_ROLE_PERMISSIONS["cashier"]))


def effective_permissions(tenant, role):
    """Permisos efectivos de un rol para un tenant: base de fábrica + overrides.

    El owner nunca se sobrescribe. Los permisos bloqueados (settings/users)
    tampoco. Los overrides solo aplican a claves conocidas.
    """
    role = (role or "owner").lower()
    base = _base_for(role)
    if role == "owner":
        return base
    overrides = {}
    raw = getattr(tenant, "role_permissions_overrides", None) or {}
    if isinstance(raw, dict):
        overrides = raw.get(role, {}) or {}
    if isinstance(overrides, dict):
        for k, v in overrides.items():
            if k in base and k not in LOCKED_PERMISSIONS:
                base[k] = bool(v)
    return base


def sanitize_overrides(payload):
    """Normaliza un payload {role: {perm: bool}} a solo roles/claves editables.

    Descarta el owner, claves desconocidas y claves bloqueadas. Devuelve el
    dict listo para guardar en Tenant.role_permissions_overrides.
    """
    clean = {}
    if not isinstance(payload, dict):
        return clean
    for role, perms in payload.items():
        if role not in EDITABLE_ROLES or not isinstance(perms, dict):
            continue
        role_clean = {}
        for k, v in perms.items():
            if k in ALL_PERMISSION_KEYS and k not in LOCKED_PERMISSIONS:
                role_clean[k] = bool(v)
        if role_clean:
            clean[role] = role_clean
    return clean
