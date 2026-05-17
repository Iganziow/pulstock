"use client";

import { useStaff } from "@/hooks/useStaff";
import { C } from "@/lib/theme";

interface WaiterSelectProps {
  value: number | null;
  onChange: (id: number | null) => void;
  storeId?: number | null;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  size?: "sm" | "md";
  label?: string;
  hint?: string;
}

/**
 * Dropdown para elegir un garzon/mozo (Fudo-style).
 * Lista a TODOS los usuarios activos del tenant (cualquier rol puede
 * atender una mesa: dueno, manager, cajero, etc.).
 *
 * Se usa en:
 *   - Modal abrir mesa (apps/web/.../mesas/page.tsx)
 *   - Modal pedido para llevar (CounterModal)
 *   - Filtros de ventas (/dashboard/sales)
 *   - Filtros de propinas (caja/CajaTipsTab)
 */
export function WaiterSelect({
  value,
  onChange,
  storeId,
  placeholder = "Sin asignar",
  required = false,
  disabled = false,
  size = "md",
  label,
  hint,
}: WaiterSelectProps) {
  const { staff, loading } = useStaff(storeId ?? null);

  const padding = size === "sm" ? "6px 10px" : "10px 12px";
  const fontSize = size === "sm" ? 12 : 14;

  return (
    <div>
      {label && (
        <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 6 }}>
          {label}
          {required && <span style={{ color: C.red, marginLeft: 4 }}>*</span>}
          {!required && <span style={{ color: C.mute, fontWeight: 400 }}> (opcional)</span>}
        </label>
      )}
      <select
        value={value ?? ""}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v ? Number(v) : null);
        }}
        disabled={disabled || loading}
        style={{
          width: "100%",
          padding,
          border: `1px solid ${C.border}`,
          borderRadius: C.r,
          fontSize,
          fontFamily: "inherit",
          outline: "none",
          background: C.surface,
          color: value == null ? C.mute : C.text,
          cursor: disabled || loading ? "not-allowed" : "pointer",
        }}
      >
        <option value="">{loading ? "Cargando…" : placeholder}</option>
        {staff.map((s) => (
          <option key={s.id} value={s.id} style={{ color: C.text }}>
            {s.display_name}
          </option>
        ))}
      </select>
      {hint && (
        <div style={{ fontSize: 11, color: C.mute, marginTop: 4 }}>{hint}</div>
      )}
    </div>
  );
}
