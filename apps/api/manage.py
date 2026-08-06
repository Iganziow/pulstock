#!/usr/bin/env python
import os
import sys


def _make_console_unbreakable():
    """Que un carácter raro NUNCA tumbe un comando.

    La consola de Windows usa cp1252 y no soporta los símbolos tipográficos que
    varios comandos usan en su salida: →, ✓, Σ, ≤, ∞, ─. Al imprimirlos salta
    UnicodeEncodeError.

    Eso no es cosmético. Encontrado dos veces en dos días, siempre igual: el
    comando hace su trabajo (borra registros, actualiza etiquetas) y MUERE
    DESPUÉS, al escribir el resumen. El operador ve un traceback, no sabe si se
    aplicó, y lo natural es reintentar. En un comando destructivo eso es
    peligroso — y perseguir cada carácter archivo por archivo no escala, porque
    el próximo comando que alguien escriba lo reintroduce.

    En Linux (producción) la consola es UTF-8 y esto no cambia nada.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass  # stream redirigido o ya cerrado: no es crítico


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
    _make_console_unbreakable()
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Couldn't import Django. Is it installed?") from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
