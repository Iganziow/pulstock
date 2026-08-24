/**
 * Cuándo vence cada suscripción, visto desde la lista de tenants.
 *
 * La lista mostraba plan y estado, pero no el vencimiento. Para saber a quién
 * cobrarle esta semana había que abrir negocio por negocio — con un cliente da
 * igual, con veinte no se hace.
 *
 * El detalle que decide si sirve: "Activa" es la misma etiqueta para uno que
 * vence mañana y para uno que vence en 28 días, y son dos situaciones muy
 * distintas.
 */
import { describe, it, expect } from "vitest";
import { vencimiento, cuentaPorVencer } from "@/lib/suscripcion";

const HOY = new Date("2026-08-24T15:00:00-04:00");
const enDias = (n: number) => {
  const d = new Date(HOY);
  d.setDate(d.getDate() + n);
  return d.toISOString();
};

describe("cuánto le queda", () => {
  it("cuenta días de calendario, no de 24 horas", () => {
    // Vence mañana a las 02:00: faltan 11 horas, pero es "mañana", no "hoy".
    // Redondear por horas haría que la lista dijera cosas distintas según a
    // qué hora del día la mires.
    expect(vencimiento("2026-08-25T02:00:00-04:00", HOY)!.dias).toBe(1);
  });

  it("habla en días, no en fechas ISO", () => {
    expect(vencimiento(enDias(5), HOY)!.texto).toBe("en 5 días");
    expect(vencimiento(enDias(1), HOY)!.texto).toBe("mañana");
    expect(vencimiento(enDias(0), HOY)!.texto).toBe("vence hoy");
  });

  it("dice hace cuánto venció, no un número negativo", () => {
    expect(vencimiento(enDias(-1), HOY)!.texto).toBe("ayer");
    expect(vencimiento(enDias(-5), HOY)!.texto).toBe("hace 5 días");
  });

  it("sin fecha no inventa nada", () => {
    // Un tenant sin suscripción no vence: mostrar "hace 20.000 días" sería
    // ruido rojo permanente en la lista.
    expect(vencimiento(null)).toBeNull();
    expect(vencimiento("")).toBeNull();
    expect(vencimiento("cuando sea")).toBeNull();
  });
});

describe("la urgencia es la que decide el color", () => {
  it("separa lo vencido de lo que está por vencer", () => {
    expect(vencimiento(enDias(-1), HOY)!.urgencia).toBe("vencido");
    expect(vencimiento(enDias(2), HOY)!.urgencia).toBe("urgente");
    expect(vencimiento(enDias(6), HOY)!.urgencia).toBe("proximo");
    expect(vencimiento(enDias(20), HOY)!.urgencia).toBe("ok");
  });

  it("hoy es urgente, no está ok", () => {
    // El borde que importa: si vence hoy y sale en gris, no se llama a nadie.
    expect(vencimiento(enDias(0), HOY)!.urgencia).toBe("urgente");
  });

  it("el corte de la semana cae donde se dice", () => {
    expect(vencimiento(enDias(7), HOY)!.urgencia).toBe("proximo");
    expect(vencimiento(enDias(8), HOY)!.urgencia).toBe("ok");
  });
});

describe("el contador de la cabecera", () => {
  it("suma los que vencen esta semana e incluye los ya vencidos", () => {
    // Un vencido sigue siendo trabajo pendiente: dejarlo fuera del contador
    // haría que el problema desaparezca de la vista justo cuando se agrava.
    const fechas = [enDias(-3), enDias(0), enDias(5), enDias(30), null];
    expect(cuentaPorVencer(fechas, 7, HOY)).toBe(3);
  });

  it("da cero cuando no hay nada que perseguir", () => {
    expect(cuentaPorVencer([enDias(30), enDias(45), null], 7, HOY)).toBe(0);
  });
});
