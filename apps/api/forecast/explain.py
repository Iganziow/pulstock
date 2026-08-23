"""
forecast.explain — de dónde sale cada predicción, en castellano.

Mario lo pidió textual: "en predicciones ver de dónde sale cada cosa".

La sugerencia de compra ya se explica sola desde hace rato (`_natural_reasoning`
en services.py, con frases como "te quedan 2 unidades y vendes alrededor de 1 al
día"). Lo que faltaba era la otra mitad: por qué el sistema cree que se van a
vender 12 el martes.

Toda la información ya estaba guardada —algoritmo, avg_daily, correcciones por
día de semana, productos padre, multiplicadores de receta, confianza medida—
pero en forma de JSON que solo sirve para depurar. Este módulo la traduce.

Por qué importa más allá de la curiosidad
-----------------------------------------
Un dueño que no entiende de dónde sale un número no lo usa: o lo obedece a
ciegas —y ahí el sistema no le enseña nada— o lo ignora. La referencia de la
industria es 7-Eleven Japón: su pantalla de pedido muestra el CONTEXTO (clima,
eventos, ventas recientes) y deja que la persona decida. Sus tiendas venden más
que las de la competencia automatizada.

También es defensa: cuando el modelo se equivoca —y se equivoca— la explicación
convierte "el sistema falló" en "ah, no sabía que ese día había partido". Eso
mantiene la confianza en vez de quemarla.
"""
from __future__ import annotations

from decimal import Decimal

# Cómo se llama cada familia de algoritmo para alguien que no es estadístico.
FAMILIAS = {
    "ingredient_derived": "receta",
    "simple_avg": "promedio",
    "moving_avg": "promedio",
    "weighted_moving_average": "promedio_ponderado",
    "adaptive_ma": "promedio_adaptativo",
    "croston": "intermitente",
    "croston_sba": "intermitente",
    "croston_bootstrap": "intermitente",
    "theta": "tendencia",
    "ets": "tendencia",
    "holt_winters": "estacional",
    "holt_winters_damped": "estacional",
    "category_prior": "categoria",
    "ensemble": "combinado",
}

DIAS = {
    "0": "los lunes", "1": "los martes", "2": "los miércoles",
    "3": "los jueves", "4": "los viernes", "5": "los sábados",
    "6": "los domingos",
}


def _num(v, decimales=0):
    """Formatea un número para leerlo, no para depurarlo."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    if decimales == 0:
        return f"{round(f):,}".replace(",", ".")
    return f"{f:,.{decimales}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _base(fm, unidad: str) -> str:
    """La frase de arranque: qué mira el modelo para predecir."""
    familia = FAMILIAS.get(fm.algorithm, "promedio")
    params = fm.model_params or {}
    avg = params.get("avg_daily")
    ritmo = f"{_num(avg)} {unidad} al día" if avg else "su ritmo habitual"

    if familia == "receta":
        padres = params.get("parent_products") or []
        return (
            f"Esta predicción no mira las ventas de este producto: mira los "
            f"{len(padres)} productos que lo usan como ingrediente. Estima "
            f"cuánto se va a vender de cada uno y suma lo que consumen, "
            f"lo que da alrededor de {ritmo}."
        )
    if familia == "intermitente":
        return (
            f"Este producto no se vende todos los días, así que el sistema no "
            f"usa un promedio simple —quedaría inflado por los días en cero—. "
            f"Estima por separado cada cuánto se vende y cuánto se lleva el "
            f"cliente cuando pasa, lo que equivale a unas {ritmo}."
        )
    if familia == "estacional":
        return (
            f"El sistema detectó un patrón semanal claro y lo sigue: parte de "
            f"{ritmo} y ajusta según el día."
        )
    if familia == "tendencia":
        return (
            f"Además del nivel de venta, el sistema detectó que viene subiendo "
            f"o bajando de forma sostenida y proyecta esa tendencia. Hoy está "
            f"en torno a {ritmo}."
        )
    if familia == "categoria":
        return (
            "Todavía no hay suficiente historial propio de este producto, así "
            "que la predicción se apoya en cómo se comportan los productos de "
            "su misma categoría. A medida que se acumulen ventas propias, el "
            "sistema va a dejar de necesitar ese respaldo."
        )
    if familia == "promedio_adaptativo":
        return (
            f"El sistema promedia las ventas recientes dándole más peso a los "
            f"últimos días, para reaccionar rápido si el ritmo cambia. Hoy da "
            f"cerca de {ritmo}."
        )
    if familia == "promedio_ponderado":
        return (
            f"El sistema promedia las últimas semanas, pesando más los días "
            f"recientes. Da alrededor de {ritmo}."
        )
    return f"El sistema promedia las ventas de las últimas semanas: cerca de {ritmo}."


def _dia_de_semana(fm, unidad: str) -> str | None:
    """Lo que el modelo aprendió sobre cada día — suele ser lo que más
    sorprende al dueño, porque confirma algo que intuía."""
    corr = ((fm.model_params or {}).get("bias_correction") or {}).get("dow") or {}
    if not corr:
        return None
    ordenados = sorted(corr.items(), key=lambda kv: -abs(float(kv[1] or 0)))
    piezas = []
    for dia, delta in ordenados[:2]:
        d = float(delta or 0)
        if abs(d) < 1:
            continue
        verbo = "se vende más" if d > 0 else "se vende menos"
        piezas.append(f"{DIAS.get(str(dia), 'ese día')} {verbo} ({_num(abs(d))} {unidad})")
    if not piezas:
        return None
    return (
        "Comparando lo que predijo contra lo que realmente pasó, el sistema "
        "aprendió que " + " y ".join(piezas) + " de lo que diría el promedio, "
        "y ya lo tiene incorporado."
    )


def _confianza(fm) -> str | None:
    """La confianza sale del error REAL medido, no de una estimación teórica.
    Decirlo así es la diferencia entre que el número se crea o no."""
    if not fm.confidence_label:
        return None
    etiquetas = {
        "high": "alta", "medium": "media",
        "low": "baja", "very_low": "muy baja",
    }
    nivel = etiquetas.get(fm.confidence_label, fm.confidence_label)
    razon = (fm.confidence_reason or "").strip()
    base = f"La confianza es {nivel}"
    if razon:
        # Minuscula inicial para que encadene con los dos puntos — salvo que
        # la razon empiece con una sigla (WAPE, MAPE). "wAPE real 26%" se lee
        # como un error de tipeo y le resta seriedad a todo el texto.
        primera = razon.split(" ", 1)[0]
        es_sigla = len(primera) > 1 and primera[:2].isupper()
        base += f": {razon}" if es_sigla else f": {razon[0].lower()}{razon[1:]}"
    base += "."
    if fm.confidence_label in ("low", "very_low"):
        base += (
            " Con confianza baja conviene revisar la cantidad sugerida antes "
            "de aprobarla."
        )
    return base


def _avisos(fm) -> list[str]:
    """Cosas que cambiaron la predicción y que el dueño debería saber."""
    params = fm.model_params or {}
    out = []
    if params.get("circuit_breaker"):
        out.append(
            "El sistema detectó que la predicción se había desalineado de la "
            "venta reciente y la corrigió automáticamente. Vale la pena mirar "
            "este producto los próximos días."
        )
    if fm.data_points and fm.data_points < 14:
        out.append(
            f"Solo hay {fm.data_points} días de historial. La predicción va a "
            f"afinarse sola a medida que se acumulen ventas."
        )
    return out


def explicar_modelo(fm, unidad: str = "unidades") -> dict:
    """Explica de dónde sale la predicción de un producto.

    Devuelve {"resumen": str, "detalles": [str, ...]} — el resumen es la
    frase que se muestra siempre; los detalles van en un "ver más".
    """
    if fm is None:
        return {
            "resumen": (
                "Todavía no hay una predicción para este producto. Suele pasar "
                "cuando recién se creó o cuando no registra ventas hace tiempo."
            ),
            "detalles": [],
        }

    unidad = unidad or "unidades"
    detalles = []
    for parte in (_dia_de_semana(fm, unidad), _confianza(fm)):
        if parte:
            detalles.append(parte)
    detalles.extend(_avisos(fm))

    return {"resumen": _base(fm, unidad), "detalles": detalles}


def explicar_ingredientes(fm, limite: int = 5) -> list[dict]:
    """Para productos derivados de receta: qué platos lo consumen y cuánto.

    Es la parte que a un dueño de café le resulta más obvia de verificar —
    "¿de verdad un latte lleva 170 ml?"— y por eso es la que más confianza
    genera cuando cuadra.
    """
    params = fm.model_params if fm else None
    if not params:
        return []
    mult = params.get("recipe_multipliers") or {}
    if not mult:
        return []

    from catalog.models import Product

    ids = [int(k) for k in mult.keys() if str(k).isdigit()]
    nombres = dict(Product.objects.filter(id__in=ids).values_list("id", "name"))

    filas = []
    for pid_str, cantidad in mult.items():
        if not str(pid_str).isdigit():
            continue
        pid = int(pid_str)
        if pid not in nombres:
            continue
        try:
            qty = Decimal(str(cantidad))
        except Exception:
            continue
        filas.append({"product_id": pid, "nombre": nombres[pid], "cantidad": str(qty)})

    filas.sort(key=lambda f: -float(f["cantidad"]))
    return filas[:limite]
