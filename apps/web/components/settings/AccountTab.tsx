"use client";
import { useState } from "react";
import { C } from "@/lib/theme";
import type { Me } from "@/lib/me";
import { Card, SectionHeader, Divider, Btn, Spinner, Label, Hint, iS, FL, ROLES } from "./SettingsUI";

interface AccountTabProps {
  me: Me;
  onSave: (data: { first_name: string; last_name: string; email: string; password?: string }) => Promise<void>;
  saving: boolean;
  mob: boolean;
}

export default function AccountTab({ me, onSave, saving, mob }: AccountTabProps) {
  const [accFirst, setAccFirst] = useState(me.first_name || "");
  const [accLast, setAccLast] = useState(me.last_name || "");
  const [accEmail, setAccEmail] = useState(me.email || "");
  const [accPwNew, setAccPwNew] = useState("");
  const [accPwConf, setAccPwConf] = useState("");
  const [localSaving, setLocalSaving] = useState(false);
  const [err, setErr] = useState("");

  const handleSave = async () => {
    setErr("");
    if (accPwNew && accPwNew.length < 8) { setErr("La contraseña debe tener al menos 8 caracteres"); return; }
    if (accPwNew && accPwNew !== accPwConf) { setErr("Las contraseñas no coinciden"); return; }
    setLocalSaving(true);
    try {
      const body: any = { first_name: accFirst, last_name: accLast, email: accEmail };
      if (accPwNew) body.password = accPwNew;
      await onSave(body);
      setAccPwNew(""); setAccPwConf("");
    } finally { setLocalSaving(false); }
  };

  const isBusy = saving || localSaving;

  return (
    <Card>
      <SectionHeader icon="👤" title="Mi cuenta" desc="Tu información personal y contraseña de acceso" />
      {err && <div style={{ color: C.red, fontSize: 12, marginBottom: 8 }}>{err}</div>}
      <div style={{ display: "grid", gap: 14 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={FL}><Label>Nombre</Label><input value={accFirst} onChange={e => setAccFirst(e.target.value)} style={iS} /></div>
          <div style={FL}><Label>Apellido</Label><input value={accLast} onChange={e => setAccLast(e.target.value)} style={iS} /></div>
        </div>
        <div style={FL}>
          <Label>Email</Label>
          <input type="email" value={accEmail} onChange={e => setAccEmail(e.target.value)} style={iS} />
        </div>
        <div style={{
          display: "flex", gap: 10, padding: "10px 12px",
          background: "#F9F9F9", borderRadius: 8, border: `1px solid ${C.border}`,
          fontSize: 13, flexWrap: "wrap",
        }}>
          <span style={{ color: C.mute }}>Usuario:</span>
          <code style={{ fontFamily: C.mono, color: C.text, fontWeight: 600 }}>{me?.username}</code>
          <span style={{ color: C.border }}>·</span>
          <span style={{ color: C.mute }}>Rol:</span>
          {(() => {
            const r = ROLES.find(r => r.value === me?.role);
            return <span style={{ fontWeight: 700, color: r?.color || C.mute }}>{r?.label || me?.role}</span>;
          })()}
        </div>
        <Divider />
        <div style={{ fontSize: 13, fontWeight: 700, color: C.mid, marginBottom: -4 }}>Cambiar contraseña</div>
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 1fr", gap: 10 }}>
          <div style={FL}>
            <Label>Nueva contraseña</Label>
            <input type="password" value={accPwNew} onChange={e => setAccPwNew(e.target.value)} style={iS} placeholder="Mínimo 8 caracteres" />
          </div>
          <div style={FL}>
            <Label>Confirmar contraseña</Label>
            <input type="password" value={accPwConf} onChange={e => setAccPwConf(e.target.value)} style={iS} placeholder="Repetir contraseña" />
          </div>
        </div>
        <Hint>Deja en blanco si no quieres cambiarla</Hint>
      </div>
      <div style={{ marginTop: 18, display: "flex", justifyContent: "flex-end" }}>
        <Btn onClick={handleSave} disabled={isBusy}>{isBusy ? <><Spinner /> Guardando</> : "Guardar cambios"}</Btn>
      </div>
    </Card>
  );
}
