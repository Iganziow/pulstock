"use client";
import { C } from "@/lib/theme";
import { Card, SectionHeader, Btn, Spinner, Label, iS, FL, type Tenant } from "./SettingsUI";

interface ReceiptTabProps {
  f: (key: keyof Tenant) => any;
  set: (key: keyof Tenant, value: any) => void;
  onSave: () => Promise<void>;
  saving: boolean;
}

export default function ReceiptTab({ f, set, onSave, saving }: ReceiptTabProps) {
  return (
    <Card>
      <SectionHeader icon="🧾" title="Configuración de boleta" desc="Qué información aparece en tus boletas y recibos" />
      <div style={{ display: "grid", gap: 14 }}>
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13 }}>
            <input type="checkbox" checked={f("receipt_show_logo") !== false} onChange={e => set("receipt_show_logo", e.target.checked)} />
            Mostrar logo
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13 }}>
            <input type="checkbox" checked={f("receipt_show_rut") !== false} onChange={e => set("receipt_show_rut", e.target.checked)} />
            Mostrar RUT
          </label>
        </div>
        <div style={FL}><Label>Texto encabezado</Label><textarea value={f("receipt_header")} onChange={e => set("receipt_header", e.target.value)} rows={2} style={{ ...iS, resize: "vertical" }} placeholder="Ej: Horario L-V 9:00-18:00" /></div>
        <div style={FL}><Label>Texto pie de boleta</Label><textarea value={f("receipt_footer")} onChange={e => set("receipt_footer", e.target.value)} rows={2} style={{ ...iS, resize: "vertical" }} placeholder="Ej: Cambios dentro de 30 días" /></div>
        <div>
          <Label>Vista previa</Label>
          <div style={{ marginTop: 8, border: `1px dashed ${C.border}`, borderRadius: 8, padding: "14px 16px", background: "#FAFAFA" }}>
            <div style={{ fontFamily: C.mono, fontSize: 11, lineHeight: 1.7, maxWidth: 260 }}>
              {f("receipt_show_logo") !== false && f("logo_url") && <div style={{ color: C.mute }}>[ LOGO ]</div>}
              <div style={{ fontWeight: 700 }}>{f("name") || "Mi Negocio"}</div>
              {f("legal_name") && <div>{f("legal_name")}</div>}
              {f("receipt_show_rut") !== false && f("rut") && <div>RUT: {f("rut")}</div>}
              {f("receipt_header") && <div style={{ fontStyle: "italic", marginTop: 2, color: C.mid }}>{f("receipt_header")}</div>}
              <div style={{ borderTop: `1px dashed ${C.border}`, margin: "6px 0" }} />
              <div>1x Producto ejemplo ..... $1.990</div>
              <div style={{ fontWeight: 700, marginTop: 3 }}>TOTAL: $1.990</div>
              {f("receipt_footer") && (
                <><div style={{ borderTop: `1px dashed ${C.border}`, margin: "6px 0" }} />
                <div style={{ fontStyle: "italic", fontSize: 10, color: C.mid }}>{f("receipt_footer")}</div></>
              )}
            </div>
          </div>
        </div>
      </div>
      <div style={{ marginTop: 18, display: "flex", justifyContent: "flex-end" }}>
        <Btn onClick={onSave} disabled={saving}>{saving ? <><Spinner /> Guardando</> : "Guardar cambios"}</Btn>
      </div>
    </Card>
  );
}
