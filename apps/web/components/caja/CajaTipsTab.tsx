"use client";

/**
 * CajaTipsTab — visor histórico de propinas embebido en /dashboard/caja.
 *
 * Mario lo pidió: "más que gráficos que a veces no dicen nada, mejor tabla
 * estilo Fudo con filtros". Reemplazado el gráfico de barras + breakdowns
 * agregados por la tabla detallada (componente TipsTable, también usado en
 * /dashboard/propinas).
 *
 * Diferencia con la página completa: acá usamos `compact=true` para que
 * encaje mejor dentro del tab (padding chico, fontes un punto menores).
 */

import { TipsTable } from "@/components/propinas/TipsTable";

export function CajaTipsTab() {
  return <TipsTable showFilters defaultDaysRange={1} compact />;
}
