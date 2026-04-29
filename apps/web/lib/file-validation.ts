/**
 * File upload validation helpers (client-side defense).
 *
 * El backend SIEMPRE re-valida (size, MIME, contenido). Esto es UX:
 * dar feedback inmediato al dueño en vez de esperar a que el server
 * rechace después de un upload de 50 MB que demoró minutos.
 *
 * IMPORTANTE: estos chequeos NO son security boundary. Un atacante puede
 * editar el DOM o saltarse el JS. Para seguridad real, mirar el equivalente
 * en backend (apps/api/catalog/views.py:_check_size, etc.).
 */

export const MAX_IMPORT_SIZE_BYTES = 5 * 1024 * 1024;  // 5 MB — match con backend
export const MAX_IMPORT_SIZE_LABEL = "5 MB";

export const MAX_SUPERADMIN_IMPORT_SIZE_BYTES = 20 * 1024 * 1024;  // 20 MB
export const MAX_SUPERADMIN_IMPORT_SIZE_LABEL = "20 MB";

/** Extensiones permitidas por tipo de import. Se validan en LOWERCASE. */
export const ACCEPTED_CSV_EXTS = [".csv"];
export const ACCEPTED_CSV_OR_XLSX_EXTS = [".csv", ".xls", ".xlsx"];

/** Validation result. error=null si todo OK. */
export type FileValidation = {
  ok: boolean;
  error: string | null;
};

/**
 * Valida un archivo antes de subirlo.
 *
 * Chequea:
 * - Existe (no null)
 * - Tamaño <= maxBytes
 * - Extensión está en allowedExts
 *
 * Devuelve { ok, error }. Mostrar `error` al usuario si !ok.
 */
export function validateImportFile(
  file: File | null,
  opts?: {
    maxBytes?: number;
    maxLabel?: string;
    allowedExts?: string[];
  }
): FileValidation {
  const maxBytes = opts?.maxBytes ?? MAX_IMPORT_SIZE_BYTES;
  const maxLabel = opts?.maxLabel ?? MAX_IMPORT_SIZE_LABEL;
  const allowedExts = opts?.allowedExts ?? ACCEPTED_CSV_OR_XLSX_EXTS;

  if (!file) return { ok: false, error: "Seleccioná un archivo." };

  if (file.size === 0) {
    return { ok: false, error: "El archivo está vacío." };
  }

  if (file.size > maxBytes) {
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    return {
      ok: false,
      error: `Archivo demasiado grande (${mb} MB). Máximo permitido: ${maxLabel}.`,
    };
  }

  const name = file.name.toLowerCase();
  const ok_ext = allowedExts.some((ext) => name.endsWith(ext));
  if (!ok_ext) {
    return {
      ok: false,
      error: `Formato no soportado. Aceptados: ${allowedExts.join(", ")}.`,
    };
  }

  return { ok: true, error: null };
}
