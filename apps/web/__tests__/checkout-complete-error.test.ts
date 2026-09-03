/**
 * La pantalla de resultado del pago no puede caerse por la forma del error.
 *
 * Visto en producción el 02/09/26: /checkout/complete?token=x mostraba
 * "Error inesperado — La aplicación encontró un problema" (el error boundary
 * global) en vez de un mensaje. La API respondía
 *
 *     400 {"detail": ["“x” no es un UUID válido."]}
 *
 * y la página le hacía `.toLowerCase()` a esa LISTA. Quien llega ahí acaba
 * de entregar plata: una pantalla en blanco con "Reintentar" es lo peor que
 * se le puede mostrar.
 */
import { describe, it, expect } from "vitest";
import { friendlyError } from "@/components/checkout/friendlyError";
import { extractErr } from "@/lib/format";

// Copiado tal cual de la respuesta de producción.
const PAYLOAD_REAL = { detail: ["“x” no es un UUID válido."] };

describe("friendlyError no revienta con lo que devuelva DRF", () => {
  it("lista (el caso real de producción) → mensaje accionable, no excepción", () => {
    expect(() => friendlyError(PAYLOAD_REAL.detail, true)).not.toThrow();
    const r = friendlyError(PAYLOAD_REAL.detail, true);
    expect(r.title).toBe("El enlace de pago no es válido");
    expect(r.primaryAction).toBe("back");
    // Nunca le mostramos "UUID" a alguien que acaba de pagar.
    expect(r.message.toLowerCase()).not.toContain("uuid");
  });

  it("objeto por campo → tampoco revienta", () => {
    expect(() => friendlyError({ token: ["Este campo es requerido."] }, true)).not.toThrow();
    expect(friendlyError({ token: ["Este campo es requerido."] }, true).title)
      .toBe("Falta el código de la sesión");
  });

  it("undefined / null → fallback genérico con contacto", () => {
    for (const raw of [undefined, null, ""]) {
      const r = friendlyError(raw, true);
      expect(r.primaryAction).toBe("support");
      expect(r.message).toContain("pulstock.admin@gmail.com");
    }
  });

  it("texto → se comporta como antes", () => {
    expect(friendlyError("sesión no encontrada", true).title)
      .toBe("No encontramos esta sesión de pago");
    expect(friendlyError("error de conexión", true).primaryAction).toBe("retry");
  });

  it("sin token manda de vuelta a planes, sea cual sea el error", () => {
    expect(friendlyError(PAYLOAD_REAL.detail, false).primaryAction).toBe("back");
    expect(friendlyError("__no_token__", false).title)
      .toBe("Esta página no es accesible directamente");
  });
});

describe("la página normaliza el detail antes de guardarlo", () => {
  it("el payload real se vuelve texto plano", () => {
    const s = extractErr({ data: PAYLOAD_REAL }, "sesión no encontrada");
    expect(typeof s).toBe("string");
    expect(s).toContain("UUID");
  });

  it("sin detail cae al fallback", () => {
    expect(extractErr({ data: {} }, "sesión no encontrada")).toBe("sesión no encontrada");
  });
});
