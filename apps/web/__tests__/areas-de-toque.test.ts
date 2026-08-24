/**
 * Las áreas de toque crecen con el dedo, no con el mouse.
 *
 * Los botones miden 32px (sm) y 38px (md). Eso pasa el mínimo de WCAG 2.2 AA
 * —24×24— pero queda por debajo de lo que piden las plataformas táctiles:
 * 44px Apple, 48px Material.
 *
 * Con mouse no molesta. Con el dedo sí, y el garzón usa Mesas y POS con el
 * teléfono en una mano, de pie y apurado: un toque que no registra le cuesta
 * más que a nadie.
 *
 * La regla vive bajo `pointer: coarse` justamente para NO agrandar nada en
 * escritorio. Estos tests fijan las dos mitades: que crezca donde debe y que
 * no crezca donde no.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const CSS = readFileSync(join(process.cwd(), "lib/useGlobalStyles.ts"), "utf8");

/** El bloque de una media query, para poder afirmar sobre su contenido. */
function bloque(query: string): string {
  const i = CSS.indexOf(`@media (${query})`);
  if (i === -1) return "";
  const abre = CSS.indexOf("{", i);
  let nivel = 0;
  for (let j = abre; j < CSS.length; j++) {
    if (CSS[j] === "{") nivel++;
    if (CSS[j] === "}") {
      nivel--;
      if (nivel === 0) return CSS.slice(abre, j + 1);
    }
  }
  return "";
}

describe("en pantallas táctiles", () => {
  const tactil = bloque("pointer: coarse");

  it("existe la regla", () => {
    expect(tactil).not.toBe("");
  });

  it("los botones llegan a 44px", () => {
    expect(tactil).toMatch(/\.xb\{min-height:44px\}/);
  });

  it("los campos de formulario también", () => {
    // Un select de 36px es igual de difícil de acertar que un botón.
    expect(tactil).toMatch(/input,select,textarea\{min-height:44px\}/);
  });

  it("los botones de ícono crecen a lo ancho, no solo a lo alto", () => {
    // Sin esto quedarían altos y angostos: peor que antes.
    expect(tactil).toMatch(/min-width:44px/);
  });
});

describe("en escritorio no cambia nada", () => {
  it("las reglas de toque viven SOLO dentro de la media query", () => {
    // Si min-height:44px se escapara fuera del bloque, cada botón del
    // escritorio crecería y el diseño se rompería en todas las pantallas.
    const fuera = CSS.replace(bloque("pointer: coarse"), "");
    expect(fuera).not.toMatch(/min-height:44px/);
  });
});

describe("el movimiento se puede apagar", () => {
  it("respeta prefers-reduced-motion", () => {
    // La app tenía seis animaciones y ninguna miraba esta preferencia.
    const reducido = bloque("prefers-reduced-motion: reduce");
    expect(reducido).toMatch(/animation-duration:0\.01ms!important/);
    expect(reducido).toMatch(/scroll-behavior:auto/);
  });

  it("el scroll suave está activo por defecto", () => {
    expect(CSS).toMatch(/html\{scroll-behavior:smooth\}/);
  });
});
