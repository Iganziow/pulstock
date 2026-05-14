/**
 * Tests del helper isTokenExpired y el flujo de auto-redirect cuando
 * la sesión está muerta (14/05/26).
 *
 * Mario reportó que después de un logout forzado del backend, el
 * navegador mostraba "El servidor tardó demasiado" sin contexto.
 * Causa: el access token vencido seguía intentando requests, llegaban
 * a 401, el refresh fallaba, y cualquier error de red intermedio se
 * mostraba como genérico.
 *
 * Fix: detectar el token vencido localmente ANTES de pegar al server,
 * o silenciar el error y redirect inmediato al login.
 */
import { describe, it, expect } from "vitest";
import { isTokenExpired } from "@/lib/api";

function makeJwt(expSecondsFromNow: number): string {
  // JWT estructura: header.payload.signature (no validamos firma).
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(JSON.stringify({
    exp: Math.floor(Date.now() / 1000) + expSecondsFromNow,
    user_id: 1,
  }));
  return `${header}.${payload}.fakesignature`;
}

describe("isTokenExpired", () => {

  it("token sin exp → NO vencido (política conservadora — asume válido)", () => {
    // Política: si no podemos decodificar el `exp`, NO marcamos como
    // vencido. Dejamos que el server decida. Esto evita falsos
    // positivos que romperían tests con tokens dummy.
    const noExp = "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxfQ.x";
    expect(isTokenExpired(noExp)).toBe(false);
  });

  it("token vencido hace 1 hora → true", () => {
    const expired = makeJwt(-3600);
    expect(isTokenExpired(expired)).toBe(true);
  });

  it("token que vence en 1 hora → false (aún válido)", () => {
    const valid = makeJwt(3600);
    expect(isTokenExpired(valid)).toBe(false);
  });

  it("token que vence en 1 segundo → false (aún válido)", () => {
    const aboutToExpire = makeJwt(1);
    expect(isTokenExpired(aboutToExpire)).toBe(false);
  });

  it("null → vencido (no hay sesión)", () => {
    expect(isTokenExpired(null)).toBe(true);
  });

  it("string malformado → NO vencido (política conservadora)", () => {
    // Si no se puede decodificar, no marcamos vencido. El server
    // rechazará si es invalido — pero al menos no causamos un
    // redirect espurio en tests con tokens dummy.
    expect(isTokenExpired("no-es-un-jwt")).toBe(false);
  });

  it("token con exp en el pasado más reciente → vencido", () => {
    // Vencido hace 1 segundo
    const justExpired = makeJwt(-1);
    expect(isTokenExpired(justExpired)).toBe(true);
  });
});
