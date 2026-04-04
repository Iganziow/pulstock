"use client";

import { C } from "@/lib/theme";
import { Btn } from "@/components/ui";

interface DeleteConfirmDialogProps {
  onCancel: () => void;
  onConfirm: () => void;
}

export function DeleteConfirmDialog({ onCancel, onConfirm }: DeleteConfirmDialogProps) {
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.4)", display: "flex",
      alignItems: "center", justifyContent: "center",
    }} onClick={onCancel}>
      <div style={{
        background: C.surface, borderRadius: C.rMd, padding: 28,
        width: 400, maxWidth: "90vw", boxShadow: C.shLg,
      }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ fontSize: 16, fontWeight: 700, color: C.text, margin: "0 0 8px" }}>
          Desactivar oferta
        </h3>
        <p style={{ fontSize: 13, color: C.mid, margin: "0 0 20px" }}>
          ¿Estas seguro de que deseas desactivar esta oferta? Los productos volveran a su precio normal.
        </p>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Btn variant="secondary" onClick={onCancel}>Cancelar</Btn>
          <Btn variant="danger" onClick={onConfirm}>Desactivar</Btn>
        </div>
      </div>
    </div>
  );
}
