export const fmt = (v: string | number) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL");
};

export const fmtDec = (v: string | number, d = 1) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "0" : n.toFixed(d);
};

export const fmtMoney = (v: string | number) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL");
};

// ─── Formato consciente de la unidad del producto ────────────────────────
//
// Para "Leche entera" cargada en ml, mostrar "31.860 unidades" o "1780.8
// uds/día" es ininteligible. El equipo de la cafetería piensa en litros.
// Esta familia de helpers convierte automáticamente:
//   ML  → L   cuando el valor es ≥ 1000
//   G   → kg  cuando el valor es ≥ 1000
//   resto → mantiene la unidad original
//
// Devuelve un objeto con `text` (número formateado), `suffix` (etiqueta como
// " L" o " uds") y `tooltip` opcional (el valor original, p. ej. "31.860 ml")
// para que el cliente pueda hacer hover y ver la conversión.

export type UnitInfo = {
  unit_code?: string | null;
  unit_family?: string | null;
};

export type FormattedQty = { text: string; suffix: string; tooltip?: string };

const VOLUME_ML_CODES = new Set(["ML", "MILILITRO", "MILILITROS", "MILI"]);
const MASS_G_CODES = new Set(["G", "GR", "GRAMO", "GRAMOS"]);
const UNIT_CODES = new Set(["UN", "UND", "UNI", "UNIDAD", "UNIDADES", "UD", "UDS", ""]);

function normCode(code?: string | null): string {
  return (code || "").trim().toUpperCase();
}

// Decimales razonables según el rango del valor — más decimales para
// números chicos, ninguno para números grandes (no necesitamos "1.245,3 L").
function smartDecimals(v: number, max = 2): number {
  const abs = Math.abs(v);
  if (abs >= 100) return 0;
  if (abs >= 10) return 1;
  return max;
}

/**
 * Formatea una cantidad respetando la unidad de medida del producto.
 *
 * @param value   número crudo (en la unidad nativa del producto: ml, g, ud)
 * @param unit    info de unidad del producto (de detail.product)
 * @param opts.perDay si true, agrega "/día" al sufijo (ej: "1,8 L/día")
 * @param opts.unitWord si "uds" agrega "uds" en vez de "unidades" (más corto)
 */
export function formatQty(
  value: number | string,
  unit?: UnitInfo | null,
  opts?: { perDay?: boolean; unitWord?: "unidades" | "uds" | "" },
): FormattedQty {
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (!Number.isFinite(n)) return { text: "0", suffix: "" };

  const code = normCode(unit?.unit_code);
  const perDay = opts?.perDay ? "/día" : "";

  // ml → L cuando vale la pena
  if (VOLUME_ML_CODES.has(code) && Math.abs(n) >= 1000) {
    const v = n / 1000;
    const d = smartDecimals(v);
    return {
      text: v.toLocaleString("es-CL", { minimumFractionDigits: 0, maximumFractionDigits: d }),
      suffix: ` L${perDay}`,
      tooltip: `${Math.round(n).toLocaleString("es-CL")} ml${perDay}`,
    };
  }

  // g → kg cuando vale la pena
  if (MASS_G_CODES.has(code) && Math.abs(n) >= 1000) {
    const v = n / 1000;
    const d = smartDecimals(v);
    return {
      text: v.toLocaleString("es-CL", { minimumFractionDigits: 0, maximumFractionDigits: d }),
      suffix: ` kg${perDay}`,
      tooltip: `${Math.round(n).toLocaleString("es-CL")} g${perDay}`,
    };
  }

  // Caso general: redondea a entero y pone el sufijo correspondiente
  const rounded = Math.round(n);
  if (UNIT_CODES.has(code)) {
    const word = opts?.unitWord === "" ? "" : opts?.unitWord || "unidades";
    const suf = word ? ` ${word === "unidades" && perDay ? "uds" : word}${perDay}` : perDay;
    return { text: rounded.toLocaleString("es-CL"), suffix: suf };
  }

  // Unidad desconocida (ml chico, g chico, KG, L explícito, etc.) — usa el
  // código tal cual en minúsculas
  return {
    text: rounded.toLocaleString("es-CL"),
    suffix: ` ${code.toLowerCase()}${perDay}`,
  };
}

// Conveniencia: devuelve solo el string completo "1,8 L/día"
export function fmtQty(value: number | string, unit?: UnitInfo | null, opts?: { perDay?: boolean; unitWord?: "unidades" | "uds" | "" }): string {
  const r = formatQty(value, unit, opts);
  return `${r.text}${r.suffix}`;
}

// Conveniencia para el promedio diario (es un decimal real, p. ej. 1.78)
// — siempre usa decimales aunque el número sea pequeño.
export function fmtQtyDaily(value: number | string, unit?: UnitInfo | null): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (!Number.isFinite(n)) return "0";
  const code = normCode(unit?.unit_code);

  if (VOLUME_ML_CODES.has(code) && Math.abs(n) >= 1000) {
    const v = n / 1000;
    return `${v.toLocaleString("es-CL", { maximumFractionDigits: 2 })} L/día`;
  }
  if (MASS_G_CODES.has(code) && Math.abs(n) >= 1000) {
    const v = n / 1000;
    return `${v.toLocaleString("es-CL", { maximumFractionDigits: 2 })} kg/día`;
  }
  // Para unidades, decimal de 1 si es chiquito (rotación lenta)
  if (UNIT_CODES.has(code)) {
    const d = n < 10 ? 1 : 0;
    return `${n.toLocaleString("es-CL", { maximumFractionDigits: d })} uds/día`;
  }
  return `${n.toLocaleString("es-CL", { maximumFractionDigits: 1 })} ${code.toLowerCase()}/día`;
}
