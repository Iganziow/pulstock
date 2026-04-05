"use client";
import { C } from "@/lib/theme";
import { Card, SectionHeader, Btn, Spinner, Label, Hint, iS, FL, type Tenant } from "./SettingsUI";

interface CompanyTabProps {
  form: Partial<Tenant>;
  f: (key: keyof Tenant) => any;
  set: (key: keyof Tenant, value: any) => void;
  onSave: () => Promise<void>;
  saving: boolean;
  mob: boolean;
}

export default function CompanyTab({ form, f, set, onSave, saving, mob }: CompanyTabProps) {
  return (
    <Card>
      <SectionHeader icon="🏢" title="Datos de empresa" desc="Información legal y de contacto de tu negocio" />
      <div style={{ display: "grid", gap: 14 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={FL}><Label req>Nombre comercial</Label><input value={f("name")} onChange={e => set("name", e.target.value)} style={iS} placeholder="Mi Negocio" /></div>
          <div style={FL}><Label>Razón social</Label><input value={f("legal_name")} onChange={e => set("legal_name", e.target.value)} style={iS} placeholder="Empresa SpA" /></div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={FL}><Label>RUT</Label><input value={f("rut")} onChange={e => set("rut", e.target.value)} style={{ ...iS, fontFamily: C.mono }} placeholder="76.123.456-7" /></div>
          <div style={FL}><Label>Giro</Label><input value={f("giro")} onChange={e => set("giro", e.target.value)} style={iS} placeholder="Venta al por menor" /></div>
        </div>
        <div style={FL}><Label>Dirección</Label><input value={f("address")} onChange={e => set("address", e.target.value)} style={iS} /></div>
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "1fr 1fr 1fr", gap: 12 }}>
          <div style={FL}><Label>Ciudad</Label><input value={f("city")} onChange={e => set("city", e.target.value)} style={iS} /></div>
          <div style={FL}><Label>Comuna</Label><input value={f("comuna")} onChange={e => set("comuna", e.target.value)} style={iS} /></div>
          <div style={FL}><Label>Teléfono</Label><input value={f("phone")} onChange={e => set("phone", e.target.value)} style={iS} /></div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={FL}><Label>Email contacto</Label><input value={f("email")} onChange={e => set("email", e.target.value)} style={iS} type="email" /></div>
          <div style={FL}><Label>IVA por defecto (%)</Label><input value={f("tax_rate")} onChange={e => set("tax_rate", e.target.value)} style={{ ...iS, fontFamily: C.mono }} type="number" /></div>
        </div>
        <div style={FL}><Label>URL del logo</Label><input value={f("logo_url")} onChange={e => set("logo_url", e.target.value)} style={iS} /><Hint>Se usa en boletas y el encabezado del sistema</Hint></div>
      </div>
      <div style={{ marginTop: 18, display: "flex", justifyContent: "flex-end" }}>
        <Btn onClick={onSave} disabled={saving} variant="primary">{saving ? <><Spinner /> Guardando</> : "Guardar cambios"}</Btn>
      </div>
    </Card>
  );
}
