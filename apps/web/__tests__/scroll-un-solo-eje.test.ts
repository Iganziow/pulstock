/**
 * Definir un solo eje de overflow trae una barra que nadie pidió.
 *
 * Por especificación de CSS, si `overflow-y` es `auto` y `overflow-x` queda
 * sin definir, el navegador convierte `overflow-x` de `visible` a `auto`. El
 * resultado es una barra horizontal en cuanto el contenido sobra por un píxel
 * — aunque nada necesite scrollear de lado.
 *
 * Se vio en la lista de Recetas: nombre y etiqueta, con el nombre truncando
 * en puntos suspensivos, y una barra horizontal abajo.
 *
 * Estos tests cubren los lugares donde el eje horizontal NO tiene sentido:
 * una lista de nombres y los menús desplegables. En una tabla ancha sí se
 * quiere scroll lateral, así que no se generaliza a toda la app.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const leer = (ruta: string) => readFileSync(join(process.cwd(), ruta), "utf8");

describe("la lista de Recetas", () => {
  const src = leer("components/catalog/recetas/ProductListPanel.tsx");

  it("cierra el eje horizontal de forma explícita", () => {
    expect(src).toMatch(/overflowY:\s*"auto",\s*overflowX:\s*"hidden"/);
  });

  it("el nombre sigue truncando en vez de empujar el ancho", () => {
    // Si se pierde el ellipsis, cerrar el overflow ESCONDE el nombre en vez
    // de acortarlo — peor que la barra que estamos sacando.
    expect(src).toMatch(/textOverflow:\s*"ellipsis"/);
    expect(src).toMatch(/minWidth:\s*0/);
  });
});

describe("los menús desplegables del layout", () => {
  const src = leer("app/(dashboard)/layout.tsx");

  it("cada contenedor con scroll vertical declara también el horizontal", () => {
    // Con minWidth 220 contra maxWidth calc(100vw - 32px), en un teléfono
    // angosto el menú se desbordaba.
    //
    // Se cuentan las declaraciones, no su posición: algunos objetos de estilo
    // las tienen en líneas separadas y eso es igual de correcto.
    const conY = src.match(/overflowY:\s*"auto"/g)?.length ?? 0;
    const conX = src.match(/overflowX:\s*"hidden"/g)?.length ?? 0;
    expect(conY).toBeGreaterThan(0);
    expect(conX).toBeGreaterThanOrEqual(conY);
  });
});
