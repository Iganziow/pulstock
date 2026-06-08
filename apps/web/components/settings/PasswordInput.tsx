"use client";
import { useState } from "react";
import { C } from "@/lib/theme";
import { iS } from "./SettingsUI";

/**
 * Input de contraseña con botón ojo (ver/ocultar) integrado.
 * Componente único para no repetir el toggle en cada formulario
 * (Mi cuenta, Crear/Editar usuario, etc.).
 */
export function PasswordInput({
  value, onChange, placeholder, autoComplete, testId,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
  testId?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <input
        type={show ? "text" : "password"}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        data-testid={testId}
        style={{ ...iS, paddingRight: 40 }}
      />
      <button
        type="button"
        onClick={() => setShow(s => !s)}
        data-testid={testId ? `${testId}-toggle` : undefined}
        aria-label={show ? "Ocultar contraseña" : "Ver contraseña"}
        title={show ? "Ocultar" : "Ver"}
        style={{
          position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "none", border: "none", color: C.mute, cursor: "pointer", padding: 4,
        }}
      >
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
          <circle cx="12" cy="12" r="3" />
          {show && <line x1="3" y1="3" x2="21" y2="21" />}
        </svg>
      </button>
    </div>
  );
}
