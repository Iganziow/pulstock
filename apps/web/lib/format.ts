/** Format a number as Chilean Pesos (no symbol, dot-separated thousands). */
export function formatCLP(value: string | number) {
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("es-CL");
}

/**
 * Extract a human-readable error message from an ApiError or generic error.
 *
 * DRF puede devolver el error en varios shapes — antes hacíamos
 * JSON.stringify(e.data) y el usuario veía cosas como
 *   {"detail":"Algunos productos no existen o no están activos."}
 * en pantalla. Ahora extraemos el mensaje real:
 *
 *   "mensaje"                          → "mensaje"
 *   {detail: "X"}                      → "X"
 *   {field: ["err1", "err2"]}          → "field: err1; field: err2"
 *   {non_field_errors: ["X"]}          → "X"
 *   {field: {nested: ["X"]}}           → "field.nested: X"
 *   ["X", "Y"]                         → "X; Y"
 */
export function extractErr(e: any, fallback: string): string {
  const data = e?.data;
  if (data !== undefined && data !== null) {
    const msg = formatErrorPayload(data);
    if (msg) return msg;
  }
  return e?.message ?? fallback;
}

function formatErrorPayload(data: any): string {
  if (typeof data === "string") return data;
  if (Array.isArray(data)) {
    return data
      .map((item) => formatErrorPayload(item))
      .filter(Boolean)
      .join("; ");
  }
  if (typeof data === "object") {
    // Si tiene `detail`, ese es el mensaje principal de DRF.
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return formatErrorPayload(data.detail);

    // non_field_errors es el catch-all de DRF para errores generales.
    if (data.non_field_errors) return formatErrorPayload(data.non_field_errors);

    // Otros campos: prefijar con el nombre del campo para que el usuario
    // sepa qué arreglar (ej: "discount_value: debe ser > 0").
    const parts: string[] = [];
    for (const [key, val] of Object.entries(data)) {
      const inner = formatErrorPayload(val);
      if (!inner) continue;
      // Para errores generales sin nombre de campo significativo,
      // mostrar solo el mensaje. Si key es algo como "name" o
      // "discount_type", anteponerlo es informativo.
      if (key === "detail" || key === "non_field_errors") {
        parts.push(inner);
      } else {
        parts.push(`${key}: ${inner}`);
      }
    }
    return parts.join("; ");
  }
  return String(data);
}
