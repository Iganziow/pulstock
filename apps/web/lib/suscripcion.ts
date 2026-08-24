/**
 * Cuánto le queda a una suscripción, en lenguaje de operador.
 *
 * La lista de tenants mostraba plan y estado, pero no cuándo vence cada uno.
 * Para saber a quién hay que cobrarle esta semana había que abrir negocio por
 * negocio — con un cliente da igual, con veinte es la diferencia entre operar
 * la plataforma y perseguirla.
 *
 * "Activa" tampoco alcanza: una suscripción activa que vence mañana y una que
 * vence en 28 días se ven idénticas, y son dos situaciones distintas.
 */

export type UrgenciaVencimiento = "vencido" | "urgente" | "proximo" | "ok";

export type Vencimiento = {
  /** Días hasta el vencimiento. Negativo si ya pasó. */
  dias: number;
  urgencia: UrgenciaVencimiento;
  /** Texto listo para mostrar: "en 5 días", "vence hoy", "hace 3 días". */
  texto: string;
};

/** Días de calendario entre hoy y la fecha, ignorando la hora. */
function diasHasta(iso: string, hoy = new Date()): number {
  const fin = new Date(iso);
  const a = Date.UTC(fin.getFullYear(), fin.getMonth(), fin.getDate());
  const b = Date.UTC(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  return Math.round((a - b) / 86_400_000);
}

/**
 * Traduce una fecha de fin de período a algo accionable.
 * Devuelve null si no hay fecha — un tenant sin suscripción no vence.
 */
export function vencimiento(iso: string | null | undefined, hoy = new Date()): Vencimiento | null {
  if (!iso) return null;
  const fin = new Date(iso);
  if (isNaN(fin.getTime())) return null;

  const dias = diasHasta(iso, hoy);

  // Los cortes salen de la ventana de cobro real: bajo 3 días ya no alcanza a
  // resolverse solo (el cliente tiene que actualizar tarjeta o transferir), y
  // sobre 7 no hay nada que hacer todavía.
  const urgencia: UrgenciaVencimiento =
    dias < 0 ? "vencido" : dias <= 3 ? "urgente" : dias <= 7 ? "proximo" : "ok";

  let texto: string;
  if (dias < -1) texto = `hace ${Math.abs(dias)} días`;
  else if (dias === -1) texto = "ayer";
  else if (dias === 0) texto = "vence hoy";
  else if (dias === 1) texto = "mañana";
  else texto = `en ${dias} días`;

  return { dias, urgencia, texto };
}

/** Cuántos vencen dentro de `dentroDe` días (incluye los ya vencidos). */
export function cuentaPorVencer(
  fechas: (string | null | undefined)[],
  dentroDe = 7,
  hoy = new Date(),
): number {
  return fechas.filter((f) => {
    const v = vencimiento(f, hoy);
    return v !== null && v.dias <= dentroDe;
  }).length;
}
