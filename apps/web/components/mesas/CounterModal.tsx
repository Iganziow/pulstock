"use client";

import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { WaiterSelect } from "@/components/WaiterSelect";
import { MesaBtn as Btn } from "./MesaBtn";
import { MesaModal } from "./MesaModal";

interface CounterModalProps {
  counterName: string;
  onChangeName: (v: string) => void;
  waiterId?: number | null;
  onChangeWaiter?: (id: number | null) => void;
  storeId?: number | null;
  counterLoading: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function CounterModal({
  counterName,
  onChangeName,
  waiterId = null,
  onChangeWaiter,
  storeId = null,
  counterLoading,
  onClose,
  onConfirm,
}: CounterModalProps) {
  return (
    <MesaModal title="Nuevo pedido para llevar" onClose={onClose} width={380}>
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 6 }}>
          Nombre del cliente <span style={{ color: C.mute, fontWeight: 400 }}>(opcional)</span>
        </label>
        <input value={counterName} onChange={e => onChangeName(e.target.value)} placeholder="Ej: Juan, María..."
          autoFocus
          onKeyDown={e => { if (e.key === "Enter") onConfirm(); }}
          style={{ width: "100%", padding: "10px 12px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 14, fontFamily: "inherit", outline: "none" }} />
        <div style={{ fontSize: 11, color: C.mute, marginTop: 4 }}>
          Se mostrará en la comanda para identificar al cliente.
        </div>
      </div>
      {onChangeWaiter && (
        <div style={{ marginBottom: 14 }}>
          <WaiterSelect
            value={waiterId}
            onChange={onChangeWaiter}
            storeId={storeId}
            label="Garzón"
            placeholder="Sin asignar"
          />
        </div>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <Btn variant="secondary" onClick={onClose}>Cancelar</Btn>
        <Btn variant="primary" full disabled={counterLoading} onClick={onConfirm}>
          {counterLoading ? <Spinner size={13} /> : null}
          Crear pedido
        </Btn>
      </div>
    </MesaModal>
  );
}
