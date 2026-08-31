"""
Procesa las capturas del manual: recorta el navegador y las deja listas.

Cómo se usa
-----------
1. En Chrome, abre la pantalla que quieras documentar.
2. Aprieta **Win + Shift + S** (recorte) o **Win + PrtScr** (pantalla completa).
   Las capturas de Windows caen solas en `Pictures/Screenshots/`.
3. Corre esto:

       python tools/traspaso/procesar_capturas.py dashboard pos mesas stock

   Toma las capturas MÁS RECIENTES de esa carpeta, en orden cronológico, y las
   asocia a los nombres que le pases. Con el ejemplo de arriba: la más antigua
   de las cuatro últimas es `dashboard.png`, la siguiente `pos.png`, etc.

Qué hace con cada una
---------------------
- **Recorta el cromo del navegador**: detecta dónde empieza el fondo claro de
  la app y corta todo lo de arriba (pestañas, barra de direcciones,
  marcadores). También quita los bordes negros del escritorio.
- **Comprime** sin perder legibilidad.
- Las deja en `docs/img/` con el nombre que corresponde.

Por qué existe
--------------
Las capturas que toma el asistente por la extensión de Chrome no quedan como
archivos accesibles desde el proyecto, así que no se pueden insertar en el
manual. Las de Windows sí. Este script cierra ese hueco: tú disparas, esto
procesa.
"""
import os
import sys
from pathlib import Path

from PIL import Image

CARPETA_WINDOWS = Path.home() / "Pictures" / "Screenshots"
DESTINO = Path(__file__).resolve().parents[2] / "docs" / "img"

# Un pixel se considera "de la app" si es claro en los tres canales. El cromo
# de Chrome en tema oscuro y el fondo del escritorio no lo son.
UMBRAL_CLARO = 200
PROPORCION_FILA = 0.8


def _es_fila_clara(rgb, y, w):
    muestras = [rgb.getpixel((x, y)) for x in range(0, w, max(1, w // 40))]
    claros = sum(1 for p in muestras if all(c > UMBRAL_CLARO for c in p[:3]))
    return claros > len(muestras) * PROPORCION_FILA


def _es_columna_clara(rgb, x, h, desde):
    muestras = [rgb.getpixel((x, y)) for y in range(desde, h, max(1, (h - desde) // 30))]
    claros = sum(1 for p in muestras if all(c > UMBRAL_CLARO for c in p[:3]))
    return claros > len(muestras) * 0.5


def recortar(ruta_origen, ruta_destino):
    im = Image.open(ruta_origen).convert("RGB")
    w, h = im.size

    # Arriba: primera fila que ya es de la app.
    arriba = 0
    for y in range(0, min(500, h)):
        if _es_fila_clara(im, y, w):
            arriba = y
            break

    # Abajo: última fila de la app (descarta el escritorio negro).
    abajo = h
    for y in range(h - 1, arriba, -1):
        if _es_fila_clara(im, y, w):
            abajo = y + 1
            break

    # Derecha: última columna de la app.
    derecha = w
    for x in range(w - 1, 0, -1):
        if _es_columna_clara(im, x, abajo, arriba):
            derecha = x + 1
            break

    recorte = im.crop((0, arriba, derecha, abajo))
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    recorte.save(ruta_destino, optimize=True)
    return recorte.size, ruta_destino.stat().st_size // 1024


def main(nombres):
    if not nombres:
        print(__doc__)
        return 1
    if not CARPETA_WINDOWS.exists():
        print("No existe %s — ¿tomaste alguna captura con Win+Shift+S?" % CARPETA_WINDOWS)
        return 1

    capturas = sorted(
        CARPETA_WINDOWS.glob("*.png"), key=lambda p: p.stat().st_mtime,
    )[-len(nombres):]

    if len(capturas) < len(nombres):
        print("Pediste %d nombres pero solo hay %d capturas." % (len(nombres), len(capturas)))
        return 1

    print("Procesando %d capturas -> %s\n" % (len(capturas), DESTINO))
    for captura, nombre in zip(capturas, nombres):
        destino = DESTINO / ("%s.png" % nombre)
        tam, kb = recortar(captura, destino)
        print("  %-22s %sx%s  %s KB" % (nombre + ".png", tam[0], tam[1], kb))
    print("\nListo. Reviselas antes de commitear: pueden traer nombres de personas.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
