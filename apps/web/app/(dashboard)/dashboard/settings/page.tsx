"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { PrinterConfig, PrinterType } from "@/lib/printer";
import type { Me } from "@/lib/me";


function useIsMobile() {
  const [m, setM] = useState(false);
  useEffect(() => {
    const fn = () => setM(window.innerWidth < 768);
    fn(); window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, []);
  return m;
}

const iS: React.CSSProperties = {
  width: "100%", padding: "9px 12px", border: `1.5px solid ${C.border}`,
  borderRadius: 8, fontSize: 13, fontFamily: "'DM Sans',system-ui,sans-serif",
  background: C.surface, outline: "none", boxSizing: "border-box" as const,
  color: "#18181B", transition: "border-color .15s",
};
const FL: React.CSSProperties = { display: "flex", flexDirection: "column" as const, gap: 4 };

function Label({ children, req }: { children: React.ReactNode; req?: boolean }) {
  return <label style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: ".06em" }}>{children}{req && <span style={{ color: C.red }}> *</span>}</label>;
}
function Hint({ children }: { children: React.ReactNode }) {
  return <span style={{ fontSize: 11, color: C.mute, marginTop: 1 }}>{children}</span>;
}
function Spinner() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: "spin .7s linear infinite", verticalAlign: "middle" }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></svg>;
}
function Btn({ onClick, disabled, children, color = C.accent, variant = "solid", style: s }: {
  onClick?: () => void; disabled?: boolean; children: React.ReactNode;
  color?: string; variant?: "solid" | "outline" | "ghost"; style?: React.CSSProperties;
}) {
  return (
    <button onClick={onClick} disabled={disabled} className="cfg-btn" style={{
      padding: "9px 18px", fontSize: 13, fontWeight: 700,
      cursor: disabled ? "default" : "pointer", fontFamily: C.font,
      border: variant === "solid" ? "none" : `1.5px solid ${color}`,
      borderRadius: 8,
      background: variant === "solid" ? color : variant === "ghost" ? "transparent" : "transparent",
      color: variant === "solid" ? "#fff" : color,
      opacity: disabled ? .5 : 1, ...s,
    }}>{children}</button>
  );
}
function SectionHeader({ icon, title, desc }: { icon: string; title: string; desc?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 20 }}>
      <div style={{ fontSize: 22, flexShrink: 0 }}>{icon}</div>
      <div>
        <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-.02em" }}>{title}</div>
        {desc && <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>{desc}</div>}
      </div>
    </div>
  );
}
function Divider() {
  return <div style={{ borderTop: `1px solid ${C.border}`, margin: "16px 0" }} />;
}
function Card({ children, style: s, padding }: { children: React.ReactNode; style?: React.CSSProperties; padding?: number }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: padding ?? 22, boxShadow: C.sh, ...s }}>
      {children}
    </div>
  );
}

const ROLES = [
  { value: "owner", label: "Dueño/Gerente", desc: "Acceso total al sistema", color: C.accent, bg: C.accentBg, bd: C.accentBd },
  { value: "manager", label: "Administrador", desc: "Todo excepto configuración", color: C.amber, bg: C.amberBg, bd: C.amberBd },
  { value: "cashier", label: "Caja/Garzón", desc: "Punto de venta y catálogo", color: C.green, bg: C.greenBg, bd: C.greenBd },
  { value: "inventory", label: "Inventario", desc: "Stock, compras y catálogo", color: "#EA580C", bg: "#FFF7ED", bd: "#FDBA74" },
];

type Tenant = {
  id: number; name: string; slug: string; legal_name: string; rut: string; giro: string;
  address: string; city: string; comuna: string; phone: string; email: string;
  website: string; logo_url: string; primary_color: string;
  receipt_header: string; receipt_footer: string; receipt_show_logo: boolean; receipt_show_rut: boolean;
  currency: string; timezone: string; tax_rate: string; created_at: string;
};
type Warehouse = { id: number; name: string; is_active: boolean; warehouse_type?: string };
type Store = { id: number; name: string; code: string; is_active: boolean; warehouses: Warehouse[] };
type User = {
  id: number; username: string; email: string; first_name: string; last_name: string;
  role: string; role_label: string; is_active: boolean; active_store_id: number | null;
  date_joined: string; last_login: string | null;
};
type Tab = "cuenta" | "empresa" | "boleta" | "tiendas" | "usuarios" | "alertas" | "impresoras" | "plan";

export default function SettingsPage() {
  const mob = useIsMobile();
  const [tab, setTab] = useState<Tab>(() => {
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search);
      const t = p.get("tab");
      if (t && ["cuenta","empresa","boleta","tiendas","usuarios","alertas","impresoras","plan"].includes(t)) return t as Tab;
    }
    return "cuenta";
  });
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [form, setForm] = useState<Partial<Tenant>>({});

  // Cuenta
  const [accFirst, setAccFirst] = useState("");
  const [accLast, setAccLast] = useState("");
  const [accEmail, setAccEmail] = useState("");
  const [accPwNew, setAccPwNew] = useState("");
  const [accPwConf, setAccPwConf] = useState("");

  // Tiendas: nueva tienda
  const [newStoreName, setNewStoreName] = useState("");
  const [newStoreCode, setNewStoreCode] = useState("");
  const [newWHName, setNewWHName] = useState("Bodega Principal");
  const [showAddStore, setShowAddStore] = useState(false);

  // Tiendas: editar nombre de tienda existente
  const [editingStoreId, setEditingStoreId] = useState<number | null>(null);
  const [editingStoreName, setEditingStoreName] = useState("");
  const [editingStoreCode, setEditingStoreCode] = useState("");

  // Tiendas: añadir bodega
  const [addWHForStore, setAddWHForStore] = useState<number | null>(null);
  const [newWHNameForStore, setNewWHNameForStore] = useState("");
  const [newWHType, setNewWHType] = useState("storage");

  // Tiendas: editar nombre de bodega
  const [editingWHId, setEditingWHId] = useState<number | null>(null);
  const [editingWHName, setEditingWHName] = useState("");

  // Usuarios
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [nuUser, setNuUser] = useState(""); const [nuPass, setNuPass] = useState("");
  const [nuFirst, setNuFirst] = useState(""); const [nuLast, setNuLast] = useState("");
  const [nuEmail, setNuEmail] = useState(""); const [nuRole, setNuRole] = useState("cashier");
  const [editUser, setEditUser] = useState<User | null>(null);
  const [euRole, setEuRole] = useState(""); const [euFirst, setEuFirst] = useState(""); const [euLast, setEuLast] = useState("");
  const [euEmail, setEuEmail] = useState(""); const [euPw, setEuPw] = useState(""); const [euCurrentPw, setEuCurrentPw] = useState("");

  // Alertas: toggles state
  const [alertStates, setAlertStates] = useState<Record<string, boolean>>({
    stock_bajo: true, forecast_urgente: true, sugerencia_compra: true,
    merma_alta: false, sin_rotacion: false, resumen_diario: false,
  });

  const flash = (type: "ok" | "err", text: string) => {
    setMsg({ type, text });
    setTimeout(() => setMsg(null), 4500);
  };

  const reloadStores = async () => {
    const s = await apiFetch("/core/stores/");
    setStores(s || []);
  };

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [t, s, m, alerts] = await Promise.all([
          apiFetch("/core/settings/"),
          apiFetch("/core/stores/"),
          apiFetch("/core/me/"),
          apiFetch("/core/alerts/").catch(() => null),
        ]);
        setTenant(t); setForm(t); setStores(s || []); setMe(m);
        if (alerts) setAlertStates(alerts);
        setAccFirst(m?.first_name || ""); setAccLast(m?.last_name || ""); setAccEmail(m?.email || "");
        if (m?.permissions?.users) {
          const u = await apiFetch("/core/users/").catch(() => []);
          setUsers(u || []);
        }
      } catch (e: any) { flash("err", e?.message || "Error cargando configuración"); }
      finally { setLoading(false); }
    })();
  }, []);

  const f = (key: keyof Tenant) => (form as any)[key] ?? "";
  const set = (key: keyof Tenant, value: any) => setForm(prev => ({ ...prev, [key]: value }));

  const saveTenant = async () => {
    setSaving(true);
    try {
      const changed: any = {};
      for (const key of Object.keys(form) as (keyof Tenant)[]) {
        if (tenant && (form as any)[key] !== (tenant as any)[key]) changed[key] = (form as any)[key];
      }
      if (Object.keys(changed).length > 0) {
        await apiFetch("/core/settings/", { method: "PATCH", body: JSON.stringify(changed) });
        setTenant({ ...tenant!, ...changed });
      }
      flash("ok", "Cambios guardados");
    } catch (e: any) { flash("err", e?.message || "Error guardando"); }
    finally { setSaving(false); }
  };

  const saveAccount = async () => {
    if (accPwNew && accPwNew.length < 8) { flash("err", "La contraseña debe tener al menos 8 caracteres"); return; }
    if (accPwNew && accPwNew !== accPwConf) { flash("err", "Las contraseñas no coinciden"); return; }
    setSaving(true);
    try {
      const body: any = { first_name: accFirst, last_name: accLast, email: accEmail };
      if (accPwNew) body.password = accPwNew;
      await apiFetch(`/core/users/${me?.id}/`, { method: "PATCH", body: JSON.stringify(body) });
      flash("ok", accPwNew ? "Datos y contraseña actualizados" : "Datos actualizados");
      setAccPwNew(""); setAccPwConf("");
    } catch (e: any) { flash("err", e?.message || "Error guardando"); }
    finally { setSaving(false); }
  };

  const createStore = async () => {
    if (!newStoreName.trim()) return;
    setSaving(true);
    try {
      await apiFetch("/core/stores/", {
        method: "POST",
        body: JSON.stringify({ name: newStoreName.trim(), code: newStoreCode.trim(), warehouse_name: newWHName.trim() || "Bodega Principal" }),
      });
      await reloadStores();
      setNewStoreName(""); setNewStoreCode(""); setNewWHName("Bodega Principal");
      setShowAddStore(false);
      flash("ok", "Tienda creada");
    } catch (e: any) { flash("err", e?.message || "Error creando tienda"); }
    finally { setSaving(false); }
  };

  const saveStoreEdit = async (storeId: number) => {
    if (!editingStoreName.trim()) return;
    setSaving(true);
    try {
      await apiFetch(`/core/stores/${storeId}/`, {
        method: "PATCH",
        body: JSON.stringify({ name: editingStoreName.trim(), code: editingStoreCode.trim() }),
      });
      await reloadStores();
      setEditingStoreId(null);
      flash("ok", "Tienda actualizada");
    } catch (e: any) { flash("err", e?.message || "Error actualizando tienda"); }
    finally { setSaving(false); }
  };

  const toggleStore = async (store: Store) => {
    try {
      await apiFetch(`/core/stores/${store.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !store.is_active }),
      });
      await reloadStores();
      flash("ok", store.is_active ? "Tienda desactivada" : "Tienda reactivada");
    } catch (e: any) { flash("err", e?.message || "Error"); }
  };

  const addWarehouse = async (storeId: number) => {
    if (!newWHNameForStore.trim()) return;
    setSaving(true);
    try {
      await apiFetch("/core/warehouses/", {
        method: "POST",
        body: JSON.stringify({ store: storeId, name: newWHNameForStore.trim(), warehouse_type: newWHType }),
      });
      await reloadStores();
      setAddWHForStore(null); setNewWHNameForStore("");
      flash("ok", "Bodega agregada");
    } catch (e: any) { flash("err", e?.message || "Error creando bodega"); }
    finally { setSaving(false); }
  };

  const saveWarehouseEdit = async (whId: number) => {
    if (!editingWHName.trim()) return;
    setSaving(true);
    try {
      await apiFetch(`/core/warehouses/${whId}/`, {
        method: "PATCH",
        body: JSON.stringify({ name: editingWHName.trim() }),
      });
      await reloadStores();
      setEditingWHId(null);
      flash("ok", "Bodega actualizada");
    } catch (e: any) { flash("err", e?.message || "Error"); }
    finally { setSaving(false); }
  };

  const toggleWarehouse = async (wh: Warehouse) => {
    try {
      await apiFetch(`/core/warehouses/${wh.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !wh.is_active }),
      });
      await reloadStores();
      flash("ok", wh.is_active ? "Bodega desactivada" : "Bodega reactivada");
    } catch (e: any) { flash("err", e?.message || "Error"); }
  };

  const createUser = async () => {
    setSaving(true);
    try {
      await apiFetch("/core/users/", { method: "POST", body: JSON.stringify({ username: nuUser, password: nuPass, first_name: nuFirst, last_name: nuLast, email: nuEmail, role: nuRole }) });
      const u = await apiFetch("/core/users/");
      setUsers(u || []); setShowCreateUser(false);
      setNuUser(""); setNuPass(""); setNuFirst(""); setNuLast(""); setNuEmail(""); setNuRole("cashier");
      flash("ok", "Usuario creado");
    } catch (e: any) { flash("err", e?.message || "Error creando usuario"); }
    finally { setSaving(false); }
  };

  const saveEditUser = async () => {
    if (!editUser) return;
    setSaving(true);
    try {
      const body: any = { role: euRole, first_name: euFirst, last_name: euLast, email: euEmail };
      if (euPw) { body.password = euPw; if (editUser.id !== me?.id) body.current_password = euCurrentPw; }
      await apiFetch(`/core/users/${editUser.id}/`, { method: "PATCH", body: JSON.stringify(body) });
      const u = await apiFetch("/core/users/");
      setUsers(u || []); setEditUser(null); setEuPw(""); setEuCurrentPw("");
      flash("ok", "Usuario actualizado");
    } catch (e: any) { flash("err", e?.message || "Error actualizando"); }
    finally { setSaving(false); }
  };

  const toggleUserActive = async (u: User) => {
    try {
      await apiFetch(`/core/users/${u.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !u.is_active }) });
      const updated = await apiFetch("/core/users/");
      setUsers(updated || []);
      flash("ok", u.is_active ? "Usuario desactivado" : "Usuario reactivado");
    } catch (e: any) { flash("err", e?.message || "Error"); }
  };

  const startEditUser = (u: User) => {
    setEditUser(u); setEuRole(u.role); setEuFirst(u.first_name);
    setEuLast(u.last_name); setEuEmail(u.email); setEuPw("");
  };

  const isOwner = me?.permissions?.users;

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: "cuenta",   label: "Mi cuenta",  icon: "👤" },
    { key: "empresa",  label: "Empresa",     icon: "🏢" },
    { key: "boleta",   label: "Boleta",      icon: "🧾" },
    { key: "tiendas",  label: "Tiendas",     icon: "🏪" },
    ...(isOwner ? [{ key: "usuarios" as Tab, label: "Usuarios", icon: "👥" }] : []),
    { key: "alertas",  label: "Alertas",     icon: "🔔" },
    { key: "impresoras", label: "Impresoras", icon: "🖨️" },
    { key: "plan",     label: "Plan",        icon: "⭐" },
  ];

  if (loading) {
    return (
      <div style={{ fontFamily: C.font, padding: 48, textAlign: "center", color: C.mute }}>
        <Spinner /> <span style={{ marginLeft: 8 }}>Cargando...</span>
      </div>
    );
  }


  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "14px 10px" : "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
      <style>{`
        @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
        input:focus, textarea:focus, select:focus { border-color: ${C.accent} !important; box-shadow: 0 0 0 3px rgba(79,70,229,.08) !important; }
        .tabs-bar::-webkit-scrollbar { display:none }
        .tabs-bar { -ms-overflow-style:none; scrollbar-width:none }
        .cfg-btn { transition: filter .15s, transform .12s; }
        .cfg-btn:hover:not(:disabled) { filter: brightness(.93); transform: translateY(-1px); }
        .cfg-btn:active:not(:disabled) { transform: scale(0.98); }
        .tab-btn { transition: color .15s, border-color .15s; }
        .tab-btn:hover { color: ${C.accent} !important; }
        .wh-tag { display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 99px; font-size: 11px; font-weight: 600; }
        .store-row:hover { background: #FAFAFA; }
        .toggle-switch { position:relative; display:inline-block; width:40px; height:22px; flex-shrink:0; }
        .toggle-switch input { opacity:0; width:0; height:0; position:absolute; }
        .toggle-track { position:absolute; cursor:pointer; inset:0; border-radius:11px; transition:background .2s; }
        .toggle-knob { position:absolute; width:16px; height:16px; background:#fff; border-radius:50%; top:3px; transition:left .2s; box-shadow:0 1px 3px rgba(0,0,0,.15); }
      `}</style>

      {/* Header */}
      <div>
        <h1 style={{ margin: 0, fontSize: mob ? 19 : 23, fontWeight: 800, letterSpacing: "-.04em" }}>
          Configuración
        </h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>
          Datos de tu negocio, cuenta, usuarios y preferencias
        </p>
      </div>

      {/* Tabs */}
      <div className="tabs-bar" style={{ display: "flex", gap: 0, borderBottom: `2px solid ${C.border}`, overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
        {tabs.map(t => (
          <button key={t.key} className="tab-btn" onClick={() => setTab(t.key)} style={{
            padding: mob ? "8px 10px" : "10px 16px", fontSize: 13, fontWeight: tab === t.key ? 700 : 500,
            color: tab === t.key ? C.accent : C.mute, background: "none", border: "none", cursor: "pointer",
            borderBottom: tab === t.key ? `2px solid ${C.accent}` : "2px solid transparent",
            marginBottom: -2, fontFamily: C.font, whiteSpace: "nowrap",
            display: "flex", alignItems: "center", gap: 6,
          }}>
            <span style={{ fontSize: 15 }}>{t.icon}</span>
            {!mob ? t.label : t.label.split(" ").slice(-1)[0]}
          </button>
        ))}
      </div>

      {/* Flash */}
      {msg && (
        <div style={{
          padding: "10px 14px",
          background: msg.type === "ok" ? C.greenBg : C.redBg,
          border: `1px solid ${msg.type === "ok" ? C.greenBd : C.redBd}`,
          borderRadius: 8, fontSize: 13,
          color: msg.type === "ok" ? C.green : C.red,
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <span>{msg.type === "ok" ? "✓" : "⚠"} {msg.text}</span>
          <button onClick={() => setMsg(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", fontSize: 18, lineHeight: 1 }}>×</button>
        </div>
      )}

      {/* ── MI CUENTA ── */}
      {tab === "cuenta" && (
        <Card>
          <SectionHeader icon="👤" title="Mi cuenta" desc="Tu información personal y contraseña de acceso" />
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
            <Btn onClick={saveAccount} disabled={saving}>{saving ? <><Spinner /> Guardando</> : "Guardar cambios"}</Btn>
          </div>
        </Card>
      )}

      {/* ── EMPRESA ── */}
      {tab === "empresa" && (
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
            <Btn onClick={saveTenant} disabled={saving}>{saving ? <><Spinner /> Guardando</> : "Guardar cambios"}</Btn>
          </div>
        </Card>
      )}

      {/* ── BOLETA ── */}
      {tab === "boleta" && (
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
            <Btn onClick={saveTenant} disabled={saving}>{saving ? <><Spinner /> Guardando</> : "Guardar cambios"}</Btn>
          </div>
        </Card>
      )}

      {/* ── TIENDAS ── */}
      {tab === "tiendas" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-.02em" }}>Tiendas y bodegas</div>
              <div style={{ fontSize: 13, color: C.mute, marginTop: 2 }}>
                {stores.length} tienda{stores.length !== 1 ? "s" : ""} · {stores.reduce((acc, s) => acc + s.warehouses.length, 0)} bodega{stores.reduce((acc, s) => acc + s.warehouses.length, 0) !== 1 ? "s" : ""} en total
              </div>
            </div>
            <Btn onClick={() => { setShowAddStore(!showAddStore); setEditingStoreId(null); }} style={{ padding: "8px 14px", fontSize: 12 }}>
              {showAddStore ? "Cancelar" : "+ Nueva tienda"}
            </Btn>
          </div>

          {/* Formulario nueva tienda */}
          {showAddStore && (
            <Card style={{ borderColor: C.accentBd, borderStyle: "dashed" }}>
              <SectionHeader icon="🏪" title="Nueva tienda" desc="Se crea con una bodega principal incluida" />
              <div style={{ display: "grid", gap: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 10 }}>
                  <div style={FL}><Label req>Nombre de la tienda</Label><input value={newStoreName} onChange={e => setNewStoreName(e.target.value)} placeholder="Ej: Local Centro" style={iS} autoFocus /></div>
                  <div style={FL}><Label>Código</Label><input value={newStoreCode} onChange={e => setNewStoreCode(e.target.value)} placeholder="LOCAL-2" style={{ ...iS, width: 110, fontFamily: C.mono }} /></div>
                </div>
                <div style={FL}>
                  <Label>Nombre bodega inicial</Label>
                  <input value={newWHName} onChange={e => setNewWHName(e.target.value)} placeholder="Bodega Principal" style={iS} />
                  <Hint>Puedes agregar más bodegas después</Hint>
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                  <Btn onClick={() => setShowAddStore(false)} variant="outline" color={C.mute} style={{ padding: "9px 16px", fontSize: 13 }}>Cancelar</Btn>
                  <Btn onClick={createStore} disabled={saving || !newStoreName.trim()} color={C.green}>
                    {saving ? <><Spinner /> Creando...</> : "Crear tienda"}
                  </Btn>
                </div>
              </div>
            </Card>
          )}

          {/* Lista de tiendas */}
          {stores.map(s => {
            const isEditingThisStore = editingStoreId === s.id;
            return (
              <Card key={s.id} style={{ padding: "0", overflow: "hidden" }}>
                {/* Store header */}
                <div style={{
                  padding: "14px 18px",
                  borderBottom: s.warehouses.length > 0 ? `1px solid ${C.border}` : "none",
                  display: "flex", justifyContent: "space-between", alignItems: "flex-start",
                  gap: 12, flexWrap: "wrap",
                  background: s.is_active ? C.surface : "#FAFAFA",
                }}>
                  {!isEditingThisStore ? (
                    <>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                          <span style={{ fontWeight: 700, fontSize: 14, color: s.is_active ? C.text : C.mute }}>
                            🏪 {s.name}
                          </span>
                          {s.code && (
                            <code style={{ fontFamily: C.mono, fontSize: 11, color: C.mute, background: "#F4F4F5", padding: "1px 6px", borderRadius: 4 }}>
                              {s.code}
                            </code>
                          )}
                          <span className="wh-tag" style={{
                            background: s.is_active ? C.greenBg : "#F4F4F5",
                            border: `1px solid ${s.is_active ? C.greenBd : "#D4D4D8"}`,
                            color: s.is_active ? C.green : C.mute,
                          }}>
                            {s.is_active ? "Activa" : "Inactiva"}
                          </span>
                        </div>
                        <div style={{ fontSize: 12, color: C.mute, marginTop: 3 }}>
                          {s.warehouses.length} bodega{s.warehouses.length !== 1 ? "s" : ""}
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <button
                          onClick={() => { setEditingStoreId(s.id); setEditingStoreName(s.name); setEditingStoreCode(s.code || ""); setShowAddStore(false); }}
                          style={{ fontSize: 12, fontWeight: 700, color: C.accent, background: "none", border: `1px solid ${C.accentBd}`, borderRadius: 7, padding: "5px 10px", cursor: "pointer", fontFamily: C.font }}
                        >
                          Editar
                        </button>
                        <button
                          onClick={() => toggleStore(s)}
                          style={{ fontSize: 12, fontWeight: 700, color: s.is_active ? C.red : C.green, background: "none", border: `1px solid ${s.is_active ? C.redBd : C.greenBd}`, borderRadius: 7, padding: "5px 10px", cursor: "pointer", fontFamily: C.font }}
                        >
                          {s.is_active ? "Desactivar" : "Activar"}
                        </button>
                      </div>
                    </>
                  ) : (
                    <div style={{ flex: 1, display: "grid", gap: 10 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: C.accent, marginBottom: -4 }}>Editando tienda</div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 10 }}>
                        <div style={FL}>
                          <Label req>Nombre</Label>
                          <input value={editingStoreName} onChange={e => setEditingStoreName(e.target.value)} style={iS} autoFocus
                            onKeyDown={e => { if (e.key === "Enter") saveStoreEdit(s.id); if (e.key === "Escape") setEditingStoreId(null); }} />
                        </div>
                        <div style={FL}>
                          <Label>Código</Label>
                          <input value={editingStoreCode} onChange={e => setEditingStoreCode(e.target.value)} style={{ ...iS, width: 110, fontFamily: C.mono }}
                            onKeyDown={e => { if (e.key === "Enter") saveStoreEdit(s.id); }} />
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <Btn onClick={() => setEditingStoreId(null)} variant="outline" color={C.mute} style={{ padding: "7px 14px", fontSize: 12 }}>Cancelar</Btn>
                        <Btn onClick={() => saveStoreEdit(s.id)} disabled={saving || !editingStoreName.trim()} color={C.green} style={{ padding: "7px 14px", fontSize: 12 }}>
                          {saving ? <Spinner /> : "Guardar"}
                        </Btn>
                      </div>
                    </div>
                  )}
                </div>

                {/* Warehouses list */}
                {s.warehouses.length > 0 && (
                  <div style={{ padding: "10px 18px 14px" }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 8 }}>
                      Bodegas
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {s.warehouses.map(w => (
                        <div key={w.id} style={{
                          display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
                          borderRadius: 8, border: `1px solid ${C.border}`,
                          background: w.is_active ? "#FAFAFA" : "#F4F4F5",
                          flexWrap: "wrap",
                        }}>
                          {editingWHId === w.id ? (
                            <>
                              <input
                                value={editingWHName}
                                onChange={e => setEditingWHName(e.target.value)}
                                style={{ ...iS, flex: 1, minWidth: 120, padding: "6px 10px", fontSize: 12 }}
                                autoFocus
                                onKeyDown={e => { if (e.key === "Enter") saveWarehouseEdit(w.id); if (e.key === "Escape") setEditingWHId(null); }}
                              />
                              <Btn onClick={() => saveWarehouseEdit(w.id)} disabled={saving || !editingWHName.trim()} color={C.green} style={{ padding: "6px 12px", fontSize: 12 }}>
                                {saving ? <Spinner /> : "✓"}
                              </Btn>
                              <Btn onClick={() => setEditingWHId(null)} variant="ghost" color={C.mute} style={{ padding: "6px 10px", fontSize: 12 }}>✕</Btn>
                            </>
                          ) : (
                            <>
                              <span style={{ fontSize: 13, color: w.is_active ? C.text : C.mute, flex: 1 }}>
                                📦 {w.name}
                                {!w.is_active && <span style={{ fontSize: 11, color: C.mute, marginLeft: 6 }}>(inactiva)</span>}
                                <span style={{fontSize:9,fontWeight:700,padding:"1px 5px",borderRadius:4,background:w.warehouse_type==="sales_floor"?C.greenBg:C.bg,color:w.warehouse_type==="sales_floor"?C.green:C.mute,border:"1px solid "+(w.warehouse_type==="sales_floor"?C.greenBd:C.border),marginLeft:6}}>{w.warehouse_type==="sales_floor"?"Sala":"Bodega"}</span>
                              </span>
                              <button
                                onClick={() => { setEditingWHId(w.id); setEditingWHName(w.name); }}
                                style={{ fontSize: 11, fontWeight: 700, color: C.mid, background: "none", border: "none", cursor: "pointer", padding: "2px 6px" }}
                              >Editar</button>
                              <button
                                onClick={() => toggleWarehouse(w)}
                                style={{ fontSize: 11, fontWeight: 700, color: w.is_active ? C.red : C.green, background: "none", border: "none", cursor: "pointer", padding: "2px 6px" }}
                              >
                                {w.is_active ? "Desactivar" : "Activar"}
                              </button>
                            </>
                          )}
                        </div>
                      ))}
                    </div>

                    {/* Add warehouse button */}
                    {addWHForStore === s.id ? (
                      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                        <input
                          value={newWHNameForStore}
                          onChange={e => setNewWHNameForStore(e.target.value)}
                          placeholder="Nombre de la bodega"
                          style={{ ...iS, flex: 1, minWidth: 160, fontSize: 12, padding: "8px 10px" }}
                          autoFocus
                          onKeyDown={e => { if (e.key === "Enter") addWarehouse(s.id); }}
                        />
                        <select value={newWHType} onChange={e => setNewWHType(e.target.value)} style={{height:32, padding:"0 8px", border:"1px solid "+C.border, borderRadius:8, fontSize:12, background:C.bg}}>
                          <option value="storage">Bodega</option>
                          <option value="sales_floor">Sala de venta</option>
                        </select>
                        <Btn onClick={() => addWarehouse(s.id)} disabled={saving || !newWHNameForStore.trim()} color={C.green} style={{ padding: "8px 14px", fontSize: 12 }}>
                          {saving ? <Spinner /> : "Crear"}
                        </Btn>
                        <Btn onClick={() => setAddWHForStore(null)} variant="outline" color={C.mute} style={{ padding: "8px 12px", fontSize: 12 }}>
                          Cancelar
                        </Btn>
                      </div>
                    ) : (
                      <button
                        onClick={() => { setAddWHForStore(s.id); setNewWHNameForStore(""); }}
                        style={{
                          marginTop: 8, fontSize: 12, fontWeight: 600, color: C.accent,
                          background: "none", border: `1px dashed ${C.accentBd}`,
                          borderRadius: 8, padding: "6px 12px", cursor: "pointer", fontFamily: C.font,
                          width: "100%",
                        }}
                      >
                        + Agregar bodega
                      </button>
                    )}
                  </div>
                )}

                {/* If no warehouses */}
                {s.warehouses.length === 0 && (
                  <div style={{ padding: "10px 18px 14px" }}>
                    <button
                      onClick={() => { setAddWHForStore(s.id); setNewWHNameForStore(""); }}
                      style={{
                        fontSize: 12, fontWeight: 600, color: C.accent,
                        background: "none", border: `1px dashed ${C.accentBd}`,
                        borderRadius: 8, padding: "6px 12px", cursor: "pointer", fontFamily: C.font,
                        width: "100%",
                      }}
                    >+ Agregar primera bodega</button>
                    {addWHForStore === s.id && (
                      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                        <input value={newWHNameForStore} onChange={e => setNewWHNameForStore(e.target.value)} placeholder="Nombre de la bodega" style={{ ...iS, flex: 1, minWidth: 160, fontSize: 12, padding: "8px 10px" }} autoFocus onKeyDown={e => { if (e.key === "Enter") addWarehouse(s.id); }} />
                        <select value={newWHType} onChange={e => setNewWHType(e.target.value)} style={{height:32, padding:"0 8px", border:"1px solid "+C.border, borderRadius:8, fontSize:12, background:C.bg}}>
                          <option value="storage">Bodega</option>
                          <option value="sales_floor">Sala de venta</option>
                        </select>
                        <Btn onClick={() => addWarehouse(s.id)} disabled={saving || !newWHNameForStore.trim()} color={C.green} style={{ padding: "8px 14px", fontSize: 12 }}>{saving ? <Spinner /> : "Crear"}</Btn>
                        <Btn onClick={() => setAddWHForStore(null)} variant="outline" color={C.mute} style={{ padding: "8px 12px", fontSize: 12 }}>Cancelar</Btn>
                      </div>
                    )}
                  </div>
                )}
              </Card>
            );
          })}

          {stores.length === 0 && !showAddStore && (
            <div style={{ textAlign: "center", padding: "40px 20px", color: C.mute, border: `1.5px dashed ${C.border}`, borderRadius: 10 }}>
              <div style={{ fontSize: 36, marginBottom: 10 }}>🏪</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: C.mid, marginBottom: 4 }}>No hay tiendas todavía</div>
              <div style={{ fontSize: 13, marginBottom: 14 }}>Crea tu primera tienda para empezar a operar</div>
              <Btn onClick={() => setShowAddStore(true)}>+ Crear primera tienda</Btn>
            </div>
          )}
        </div>
      )}

      {/* ── USUARIOS ── */}
      {tab === "usuarios" && isOwner && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-.02em" }}>Usuarios</div>
              <div style={{ fontSize: 13, color: C.mute, marginTop: 2 }}>{users.length} usuario{users.length !== 1 ? "s" : ""} en tu negocio</div>
            </div>
            <Btn onClick={() => setShowCreateUser(!showCreateUser)} style={{ padding: "8px 14px", fontSize: 12 }}>
              {showCreateUser ? "Cancelar" : "+ Nuevo usuario"}
            </Btn>
          </div>

          {showCreateUser && (
            <Card style={{ borderColor: C.accentBd }}>
              <SectionHeader icon="👤" title="Crear usuario" desc="El usuario podrá acceder al sistema con estas credenciales" />
              <div style={{ display: "grid", gap: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <div style={FL}><Label req>Usuario</Label><input value={nuUser} onChange={e => setNuUser(e.target.value)} style={{ ...iS, fontFamily: C.mono }} placeholder="jperez" /></div>
                  <div style={FL}><Label req>Contraseña</Label><input type="password" value={nuPass} onChange={e => setNuPass(e.target.value)} style={iS} placeholder="Mín. 8 caracteres" /></div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <div style={FL}><Label>Nombre</Label><input value={nuFirst} onChange={e => setNuFirst(e.target.value)} style={iS} /></div>
                  <div style={FL}><Label>Apellido</Label><input value={nuLast} onChange={e => setNuLast(e.target.value)} style={iS} /></div>
                </div>
                <div style={FL}><Label>Email</Label><input type="email" value={nuEmail} onChange={e => setNuEmail(e.target.value)} style={iS} /></div>
                <div style={FL}>
                  <Label req>Rol</Label>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {ROLES.map(r => (
                      <button key={r.value} onClick={() => setNuRole(r.value)} style={{
                        padding: "10px 14px", border: `1.5px solid ${nuRole === r.value ? r.color : C.border}`,
                        borderRadius: 8, background: nuRole === r.value ? r.bg : C.surface,
                        cursor: "pointer", fontFamily: C.font, flex: 1, textAlign: "left", minWidth: 120,
                      }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: nuRole === r.value ? r.color : C.text }}>{r.label}</div>
                        <div style={{ fontSize: 11, color: C.mute, marginTop: 1 }}>{r.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                  <Btn onClick={() => setShowCreateUser(false)} variant="outline" color={C.mute} style={{ padding: "9px 16px", fontSize: 13 }}>Cancelar</Btn>
                  <Btn onClick={createUser} disabled={saving || !nuUser || !nuPass} color={C.green}>
                    {saving ? <><Spinner /> Creando...</> : "Crear usuario"}
                  </Btn>
                </div>
              </div>
            </Card>
          )}

          {users.map(u => {
            const rc = ROLES.find(r => r.value === u.role);
            const isEditing = editUser?.id === u.id;
            return (
              <Card key={u.id} style={{ padding: "12px 18px", borderColor: isEditing ? C.accentBd : C.border }}>
                {!isEditing ? (
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", gap: 7 }}>
                        {u.first_name || u.username} {u.last_name}
                        {!u.is_active && (
                          <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 99, background: C.redBg, color: C.red, border: `1px solid ${C.redBd}` }}>
                            Inactivo
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>
                        {u.email || u.username}
                        {u.last_login
                          ? ` · Último acceso: ${new Date(u.last_login).toLocaleDateString("es-CL", { day: "numeric", month: "short", year: "numeric" })}`
                          : " · Nunca accedió"}
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="wh-tag" style={{ background: rc?.bg || "#F4F4F5", border: `1px solid ${rc?.bd || "#E4E4E7"}`, color: rc?.color || C.mute }}>
                        {rc?.label || u.role}
                      </span>
                      <button onClick={() => { setEditUser(u); setEuRole(u.role); setEuFirst(u.first_name); setEuLast(u.last_name); setEuEmail(u.email); setEuPw(""); setEuCurrentPw(""); }} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, color: C.accent, fontWeight: 700 }}>
                        Editar
                      </button>
                      {u.id !== me?.id && (
                        <button onClick={() => toggleUserActive(u)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, color: u.is_active ? C.red : C.green, fontWeight: 700 }}>
                          {u.is_active ? "Desactivar" : "Reactivar"}
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "grid", gap: 12 }}>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>Editando: <code style={{ fontFamily: C.mono }}>{u.username}</code></div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                      <div style={FL}><Label>Nombre</Label><input value={euFirst} onChange={e => setEuFirst(e.target.value)} style={iS} /></div>
                      <div style={FL}><Label>Apellido</Label><input value={euLast} onChange={e => setEuLast(e.target.value)} style={iS} /></div>
                    </div>
                    <div style={FL}><Label>Email</Label><input type="email" value={euEmail} onChange={e => setEuEmail(e.target.value)} style={iS} /></div>
                    <div style={FL}><Label>Nueva contraseña</Label><input type="password" value={euPw} onChange={e => setEuPw(e.target.value)} style={iS} placeholder="Dejar vacío para no cambiar" /></div>
                    {euPw && u.id !== me?.id && (
                      <div style={FL}><Label req>Tu contraseña actual (para confirmar)</Label><input type="password" value={euCurrentPw} onChange={e => setEuCurrentPw(e.target.value)} style={iS} placeholder="Tu contraseña de administrador" autoComplete="current-password" /></div>
                    )}
                    <div style={FL}>
                      <Label>Rol</Label>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {ROLES.map(r => (
                          <button key={r.value} onClick={() => setEuRole(r.value)} style={{
                            padding: "8px 14px", border: `1.5px solid ${euRole === r.value ? r.color : C.border}`,
                            borderRadius: 8, background: euRole === r.value ? r.bg : C.surface,
                            cursor: "pointer", fontFamily: C.font, fontSize: 13, fontWeight: 600,
                            color: euRole === r.value ? r.color : C.mid,
                          }}>{r.label}</button>
                        ))}
                      </div>
                    </div>
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                      <Btn onClick={() => { setEditUser(null); setEuCurrentPw(""); }} variant="outline" color={C.mute} style={{ padding: "8px 16px", fontSize: 13 }}>Cancelar</Btn>
                      <Btn onClick={saveEditUser} disabled={saving}>{saving ? <><Spinner /> Guardando</> : "Guardar"}</Btn>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* ── ALERTAS ── */}
      {tab === "alertas" && (
        <Card>
          <SectionHeader icon="🔔" title="Alertas y notificaciones" desc="Cuáles alertas quieres recibir en tu dashboard" />
          <div style={{ display: "flex", flexDirection: "column" }}>
            {[
              { key: "stock_bajo", label: "Stock bajo mínimo", desc: "Alerta cuando un producto baja del stock mínimo configurado" },
              { key: "forecast_urgente", label: "Predicción: producto por agotarse", desc: "Alerta cuando el sistema predice que un producto se agota en menos de 3 días" },
              { key: "sugerencia_compra", label: "Sugerencia de compra lista", desc: "Notificación cuando el sistema genera un pedido sugerido para aprobar" },
              { key: "merma_alta", label: "Merma inusual detectada", desc: "Alerta cuando las pérdidas de un producto superan lo histórico" },
              { key: "sin_rotacion", label: "Productos sin rotación", desc: "Aviso semanal de productos con stock pero sin ventas en 30+ días" },
              { key: "resumen_diario", label: "Resumen diario de ventas", desc: "Email con ventas, margen y productos más vendidos del día" },
            ].map((n, i, arr) => {
              const on = alertStates[n.key] ?? false;
              return (
                <div key={n.key} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "13px 0",
                  borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
                  gap: 12,
                }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{n.label}</div>
                    <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>{n.desc}</div>
                  </div>
                  <label className="toggle-switch" style={{ cursor: "pointer" }}>
                    <input type="checkbox" checked={on} onChange={async () => {
                      const newVal = !on;
                      setAlertStates(prev => ({ ...prev, [n.key]: newVal }));
                      try {
                        await apiFetch("/core/alerts/", { method: "PATCH", body: JSON.stringify({ [n.key]: newVal }) });
                      } catch { setAlertStates(prev => ({ ...prev, [n.key]: on })); }
                    }} />
                    <div className="toggle-track" style={{ background: on ? C.accent : "#D4D4D8" }}>
                      <div className="toggle-knob" style={{ left: on ? 21 : 3 }} />
                    </div>
                  </label>
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: 16, padding: "10px 13px", background: C.accentBg, border: `1px solid ${C.accentBd}`, borderRadius: 8, fontSize: 12, color: C.accent, display: "flex", gap: 8 }}>
            <span>💡</span>
            <span>Tus preferencias se guardan automáticamente.</span>
          </div>
        </Card>
      )}

      {/* ── PLAN ── */}
      {tab === "impresoras" && <PrintersTab mob={mob} flash={flash} />}

      {tab === "plan" && <PlanTab mob={mob} flash={flash} tenantCreatedAt={tenant?.created_at} />}
    </div>
  );
}


// ─── Printers Tab Component ──────────────────────────────────────────────────

function PrintersTab({ mob, flash }: {
  mob: boolean;
  flash: (type: "ok" | "err", text: string) => void;
}) {
  const [printers, setPrinters] = useState<PrinterConfig[]>([]);
  const [defaultId, setDefaultId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [addType, setAddType] = useState<PrinterType | null>(null);
  const [addName, setAddName] = useState("");
  const [addWidth, setAddWidth] = useState<58 | 80>(80);
  const [addAddress, setAddAddress] = useState("");
  const [pairing, setPairing] = useState(false);

  const reload = () => {
    try {
      const { getSavedPrinters, getDefaultPrinter } = require("@/lib/printer");
      setPrinters(getSavedPrinters());
      setDefaultId(getDefaultPrinter()?.id || null);
    } catch { setPrinters([]); }
  };

  useEffect(() => { reload(); }, []);

  const handleRemove = (id: string) => {
    if (!confirm("¿Eliminar esta impresora?")) return;
    const { removePrinter } = require("@/lib/printer");
    removePrinter(id);
    reload();
    flash("ok", "Impresora eliminada");
  };

  const handleSetDefault = (id: string) => {
    const { setDefaultPrinter } = require("@/lib/printer");
    setDefaultPrinter(id);
    setDefaultId(id);
    flash("ok", "Impresora predeterminada actualizada");
  };

  const handleTest = async (p: PrinterConfig) => {
    try {
      if (p.type === "system") {
        const { printSystemReceipt } = require("@/lib/printer");
        const html = `
          <div class="title">PRUEBA</div>
          <div class="sep-double"></div>
          <div class="row"><span>Impresora:</span><span>${p.name}</span></div>
          <div class="row"><span>Tipo:</span><span>${p.type.toUpperCase()}</span></div>
          <div class="row"><span>Ancho:</span><span>${p.paperWidth}mm</span></div>
          <div class="sep-double"></div>
          <div class="center">Impresión OK!</div>
        `;
        printSystemReceipt(html, p);
        flash("ok", "Prueba enviada al diálogo de impresión");
      } else {
        const { EscPos } = require("@/lib/escpos");
        const { printBytes } = require("@/lib/printer");
        const cols = p.paperWidth === 58 ? 32 : 48;
        const esc = new EscPos();
        esc.init()
          .align("center").bold(true).fontSize(2, 2)
          .text("PRUEBA").nl()
          .fontSize(1, 1).bold(false)
          .separator("=", cols)
          .textLine("Impresora:", p.name, cols)
          .textLine("Tipo:", p.type.toUpperCase(), cols)
          .textLine("Ancho:", `${p.paperWidth}mm`, cols)
          .separator("=", cols)
          .align("center")
          .text("Impresion OK!").nl()
          .feed(3).cut();
        await printBytes(esc.build(), p);
        flash("ok", "Prueba enviada correctamente");
      }
    } catch (e: any) {
      flash("err", e?.message || "Error al imprimir prueba");
    }
  };

  const handleAddUSB = async () => {
    setPairing(true);
    try {
      const { pairUSBPrinter, savePrinter, generateId } = require("@/lib/printer");
      await pairUSBPrinter();
      const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora USB", type: "usb", paperWidth: addWidth };
      savePrinter(cfg);
      reload();
      setShowAdd(false); setAddType(null); setAddName(""); setAddAddress("");
      flash("ok", "Impresora USB agregada");
    } catch (e: any) {
      flash("err", e?.message || "No se pudo conectar la impresora USB");
    } finally { setPairing(false); }
  };

  const handleAddBluetooth = async () => {
    setPairing(true);
    try {
      const { pairBluetoothPrinter, savePrinter, generateId } = require("@/lib/printer");
      await pairBluetoothPrinter();
      const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora Bluetooth", type: "bluetooth", paperWidth: addWidth };
      savePrinter(cfg);
      reload();
      setShowAdd(false); setAddType(null); setAddName(""); setAddAddress("");
      flash("ok", "Impresora Bluetooth agregada");
    } catch (e: any) {
      flash("err", e?.message || "No se pudo conectar la impresora Bluetooth");
    } finally { setPairing(false); }
  };

  const handleAddNetwork = () => {
    if (!addAddress.trim()) { flash("err", "Ingresa la dirección IP"); return; }
    const { savePrinter, generateId } = require("@/lib/printer");
    const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora Red", type: "network", paperWidth: addWidth, address: addAddress.trim() };
    savePrinter(cfg);
    reload();
    setShowAdd(false); setAddType(null); setAddName(""); setAddAddress("");
    flash("ok", "Impresora de red agregada");
  };

  const handleAddSystem = () => {
    const { savePrinter, generateId } = require("@/lib/printer");
    const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora del sistema", type: "system", paperWidth: addWidth };
    savePrinter(cfg);
    reload();
    setShowAdd(false); setAddType(null); setAddName(""); setAddAddress("");
    flash("ok", "Impresora del sistema agregada");
  };

  const TYPE_BADGES: Record<PrinterType, { label: string; color: string; bg: string; bd: string }> = {
    usb: { label: "USB", color: C.accent, bg: C.accentBg, bd: C.accentBd },
    bluetooth: { label: "Bluetooth", color: "#2563EB", bg: "#EFF6FF", bd: "#BFDBFE" },
    network: { label: "Red/WiFi", color: C.green, bg: C.greenBg, bd: C.greenBd },
    system: { label: "Sistema", color: "#7C3AED", bg: "#F5F3FF", bd: "#DDD6FE" },
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Card>
        <SectionHeader icon="🖨️" title="Impresoras térmicas" desc="Configura tus impresoras para imprimir boletas y pre-cuentas directamente" />

        {printers.length === 0 && !showAdd && (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>🖨️</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: C.mid, marginBottom: 4 }}>No hay impresoras configuradas</div>
            <div style={{ fontSize: 12, color: C.mute, marginBottom: 16 }}>Agrega una impresora térmica para imprimir boletas y pre-cuentas</div>
          </div>
        )}

        {printers.map(p => {
          const badge = TYPE_BADGES[p.type];
          const isDefault = p.id === defaultId;
          return (
            <div key={p.id} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
              border: `1.5px solid ${isDefault ? C.accentBd : C.border}`,
              borderRadius: 10, marginBottom: 8,
              background: isDefault ? C.accentBg : "transparent",
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{p.name}</span>
                  <span style={{
                    padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 700,
                    color: badge.color, background: badge.bg, border: `1px solid ${badge.bd}`,
                  }}>{badge.label}</span>
                  {isDefault && (
                    <span style={{
                      padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 700,
                      color: C.amber, background: C.amberBg, border: `1px solid ${C.amberBd}`,
                    }}>Predeterminada</span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: C.mute }}>
                  {p.paperWidth}mm{p.address ? ` · ${p.address}` : ""}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                {!isDefault && (
                  <button onClick={() => handleSetDefault(p.id)} className="cfg-btn" style={{
                    padding: "5px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                    border: `1px solid ${C.border}`, borderRadius: 6, background: C.surface, color: C.mid,
                  }}>Predeterminada</button>
                )}
                <button onClick={() => handleTest(p)} className="cfg-btn" style={{
                  padding: "5px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                  border: `1px solid ${C.accentBd}`, borderRadius: 6, background: C.accentBg, color: C.accent,
                }}>Test</button>
                <button onClick={() => handleRemove(p.id)} className="cfg-btn" style={{
                  padding: "5px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                  border: `1px solid ${C.redBd}`, borderRadius: 6, background: C.redBg, color: C.red,
                }}>Eliminar</button>
              </div>
            </div>
          );
        })}

        <Divider />

        {!showAdd ? (
          <Btn onClick={() => { setShowAdd(true); setAddType(null); setAddName(""); setAddAddress(""); }} color={C.accent}>
            + Agregar impresora
          </Btn>
        ) : (
          <div style={{ border: `1.5px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Agregar impresora</div>

            {!addType ? (
              <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 1fr", gap: 8 }}>
                {([
                  { type: "system" as PrinterType, icon: "🖥️", label: "Sistema (Windows)", desc: "Usa impresoras instaladas en tu PC" },
                  { type: "usb" as PrinterType, icon: "🔌", label: "USB directa", desc: "Conexión directa ESC/POS por cable" },
                  { type: "bluetooth" as PrinterType, icon: "📶", label: "Bluetooth", desc: "Impresora inalámbrica BT" },
                  { type: "network" as PrinterType, icon: "🌐", label: "Red / WiFi", desc: "Conexión por IP de red" },
                ]).map(opt => (
                  <button key={opt.type} onClick={() => setAddType(opt.type)} className="cfg-btn" style={{
                    padding: 16, border: `1.5px solid ${C.border}`, borderRadius: 10,
                    background: C.surface, cursor: "pointer", textAlign: "center",
                  }}>
                    <div style={{ fontSize: 28, marginBottom: 6 }}>{opt.icon}</div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{opt.label}</div>
                    <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{opt.desc}</div>
                  </button>
                ))}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {addType === "system" && (
                  <div style={{ background: "#F5F3FF", border: "1px solid #DDD6FE", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#5B21B6", lineHeight: 1.5 }}>
                    <strong>¿Cómo funciona?</strong> Al imprimir, se abrirá el diálogo de Windows donde podrás elegir entre tus impresoras instaladas (ej: POST 801, Microsoft Print to PDF, etc.). Usa el nombre de tu impresora real para identificarla fácilmente.
                  </div>
                )}
                <div style={FL}>
                  <Label>Nombre</Label>
                  <input style={iS} value={addName} onChange={e => setAddName(e.target.value)}
                    placeholder={addType === "system" ? "Ej: POST 801" : addType === "usb" ? "Ej: Caja principal" : addType === "bluetooth" ? "Ej: Impresora bar" : "Ej: Cocina"} />
                  {addType === "system" && <Hint>Ponle el mismo nombre de tu impresora en Windows para identificarla</Hint>}
                </div>
                <div style={FL}>
                  <Label>Ancho de papel</Label>
                  <div style={{ display: "flex", gap: 8 }}>
                    {([58, 80] as const).map(w => (
                      <button key={w} onClick={() => setAddWidth(w)} className="cfg-btn" style={{
                        padding: "7px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer",
                        border: `1.5px solid ${addWidth === w ? C.accent : C.border}`,
                        borderRadius: 8, background: addWidth === w ? C.accentBg : "transparent",
                        color: addWidth === w ? C.accent : C.mid,
                      }}>{w}mm</button>
                    ))}
                  </div>
                </div>
                {addType === "network" && (
                  <div style={FL}>
                    <Label req>Dirección IP</Label>
                    <input style={iS} value={addAddress} onChange={e => setAddAddress(e.target.value)}
                      placeholder="192.168.1.100:9100" />
                    <Hint>IP y puerto de la impresora en tu red local</Hint>
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                  <Btn onClick={() => {
                    if (addType === "system") handleAddSystem();
                    else if (addType === "usb") handleAddUSB();
                    else if (addType === "bluetooth") handleAddBluetooth();
                    else handleAddNetwork();
                  }} disabled={pairing}>
                    {pairing ? "Conectando..." : (addType === "network" || addType === "system") ? "Agregar" : "Conectar y agregar"}
                  </Btn>
                  <Btn onClick={() => { setShowAdd(false); setAddType(null); }} variant="outline" color={C.mid}>
                    Cancelar
                  </Btn>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}


// ─── Plan & Subscription Tab ─────────────────────────────────────────────────

type SubPlan = {
  key: string; name: string; price_clp: number; trial_days: number;
  max_products: number; max_stores: number; max_users: number;
  has_forecast: boolean; has_abc: boolean; has_reports: boolean; has_transfers: boolean;
};
type SubInvoice = {
  id: number; status: string; amount_clp: number;
  period_start: string; period_end: string;
  paid_at: string | null; payment_url: string | null; created_at: string;
};
type SubData = {
  status: string; status_label: string; is_access_allowed: boolean;
  plan: SubPlan; trial_ends_at: string | null; current_period_end: string | null;
  days_remaining: number | null; payment_retry_count: number;
  next_retry_at: string | null; recent_invoices: SubInvoice[];
  has_card: boolean; card_brand: string; card_last4: string;
};

const CLP = (n: number) =>
  new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", minimumFractionDigits: 0 }).format(n);
const fmtD = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("es-CL", { day: "numeric", month: "long", year: "numeric" }) : "—";

const ST_CFG: Record<string, { label: string; color: string; bg: string; bd: string }> = {
  trialing:  { label: "Período de prueba", color: "#2563EB", bg: "#EFF6FF", bd: "#BFDBFE" },
  active:    { label: "Activa",            color: "#16A34A", bg: "#ECFDF5", bd: "#A7F3D0" },
  past_due:  { label: "Pago pendiente",    color: "#D97706", bg: "#FFFBEB", bd: "#FDE68A" },
  suspended: { label: "Suspendida",        color: "#DC2626", bg: "#FEF2F2", bd: "#FECACA" },
  cancelled: { label: "Cancelada",         color: "#71717A", bg: "#F4F4F5", bd: "#E4E4E7" },
};
const INV_ST: Record<string, { label: string; color: string }> = {
  pending: { label: "Pendiente", color: "#D97706" },
  paid:    { label: "Pagada",    color: "#16A34A" },
  failed:  { label: "Fallida",   color: "#DC2626" },
  voided:  { label: "Anulada",   color: "#71717A" },
};

function PlanTab({ mob, flash, tenantCreatedAt }: { mob: boolean; flash: (t: "ok" | "err", m: string) => void; tenantCreatedAt?: string }) {
  const [sub, setSub] = useState<SubData | null>(null);
  const [plans, setPlans] = useState<SubPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [payUrl, setPayUrl] = useState<string | null>(null);
  const [showCancel, setShowCancel] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [s, p] = await Promise.all([
        apiFetch("/billing/subscription/"),
        apiFetch("/billing/plans/"),
      ]);
      setSub(s); setPlans(p);
    } catch { flash("err", "No se pudo cargar la suscripción."); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  // Confirmar pago si hay token en la URL (retorno de Flow)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (!token) return;
    (async () => {
      setBusy(true);
      try {
        const res = await apiFetch("/billing/subscription/confirm-payment/", {
          method: "POST", body: JSON.stringify({ token }),
        });
        if (res.ok || res.status === "already_paid") {
          flash("ok", res.detail || "Pago confirmado exitosamente.");
          setPayUrl(null);
          await load();
        } else {
          flash("err", res.detail || "El pago fue rechazado.");
        }
      } catch (e: any) {
        flash("err", e?.data?.detail || "Error verificando el pago.");
      } finally {
        setBusy(false);
        const url = new URL(window.location.href);
        url.searchParams.delete("token");
        url.searchParams.delete("tab");
        window.history.replaceState({}, "", url.toString());
      }
    })();
  }, []);

  const handlePay = async () => {
    setBusy(true);
    try {
      const data = await apiFetch("/billing/subscription/pay/", { method: "POST", body: JSON.stringify({}) });
      if (data.payment_url) {
        window.location.href = data.payment_url;
      }
    } catch { flash("err", "No se pudo generar el link de pago."); }
    finally { setBusy(false); }
  };

  const handleUpgrade = async (key: string) => {
    if (!sub || key === sub.plan.key) return;
    setBusy(true);
    try {
      const data = await apiFetch("/billing/subscription/upgrade/", {
        method: "POST", body: JSON.stringify({ plan: key }),
      });
      setSub(data);
      if (data.payment_url) {
        window.location.href = data.payment_url;
      } else {
        flash("ok", "Plan actualizado.");
      }
    } catch (e: any) {
      flash("err", e?.data?.detail || "Error al cambiar de plan.");
    } finally { setBusy(false); }
  };

  const handleCancel = async () => {
    setBusy(true);
    try {
      await apiFetch("/billing/subscription/cancel/", { method: "POST", body: JSON.stringify({}) });
      setShowCancel(false);
      flash("ok", "Suscripción cancelada. Tu acceso continúa hasta el fin del período.");
      await load();
    } catch (e: any) {
      flash("err", e?.data?.detail || "Error al cancelar.");
    } finally { setBusy(false); }
  };

  const handleReactivate = async () => {
    setBusy(true);
    try {
      const data = await apiFetch("/billing/subscription/reactivate/", { method: "POST", body: JSON.stringify({}) });
      if (data.payment_url) {
        window.location.href = data.payment_url;
      } else {
        flash("ok", "Suscripción reactivada.");
        await load();
      }
    } catch (e: any) {
      if (e?.data?.payment_url) window.location.href = e.data.payment_url;
      else flash("err", e?.message || "Error al reactivar.");
    } finally { setBusy(false); }
  };

  // ── Tarjeta de crédito ──
  const handleRegisterCard = async () => {
    setBusy(true);
    try {
      const data = await apiFetch("/billing/subscription/card/", { method: "POST", body: JSON.stringify({}) });
      if (data.register_url) window.location.href = data.register_url;
    } catch (e: any) {
      flash("err", e?.data?.detail || "Error al iniciar registro de tarjeta.");
    } finally { setBusy(false); }
  };

  const handleRemoveCard = async () => {
    setBusy(true);
    try {
      await apiFetch("/billing/subscription/card/remove/", { method: "POST", body: JSON.stringify({}) });
      flash("ok", "Tarjeta eliminada.");
      await load();
    } catch (e: any) {
      flash("err", e?.data?.detail || "Error al eliminar tarjeta.");
    } finally { setBusy(false); }
  };

  // Detectar retorno de registro de tarjeta
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const card = params.get("card");
    if (card === "ok") {
      flash("ok", "Tarjeta registrada exitosamente. Los próximos cobros se harán automáticamente.");
      load();
    } else if (card === "fail") {
      flash("err", "No se pudo registrar la tarjeta. Intenta nuevamente.");
    }
    if (card) {
      const url = new URL(window.location.href);
      url.searchParams.delete("card");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: 40, color: C.mute }}>
      <div style={{ width: 18, height: 18, border: `2px solid ${C.border}`, borderTopColor: C.accent, borderRadius: "50%", animation: "spin .7s linear infinite" }} />
      Cargando suscripción...
    </div>
  );
  if (!sub) return <Card><div style={{ color: C.mute, fontSize: 13 }}>Sin datos de suscripción.</div></Card>;

  const sc = ST_CFG[sub.status] || ST_CFG.cancelled;
  const isFree = sub.plan.price_clp === 0;
  const isTrial = sub.status === "trialing";
  const isPD = sub.status === "past_due";
  const isSusp = sub.status === "suspended";
  const isCanc = sub.status === "cancelled";

  const pb: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: "pointer", border: "none", fontFamily: "inherit", minHeight: 40 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

      {/* Alerta pago pendiente */}
      {isPD && (
        <Card style={{ borderColor: "#FDE68A", background: "#FFFBEB" }} padding={14}>
          <div style={{ display: "flex", alignItems: mob ? "stretch" : "center", gap: 12, flexDirection: mob ? "column" : "row" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, color: "#92400E", fontSize: 13 }}>⚠ Pago pendiente</div>
              <div style={{ fontSize: 12, color: "#78350F", marginTop: 2 }}>
                Intento {sub.payment_retry_count} de 3.
                {sub.next_retry_at && ` Próximo reintento: ${fmtD(sub.next_retry_at)}.`}
              </div>
            </div>
            <button onClick={handlePay} disabled={busy} style={{ ...pb, background: C.accent, color: "#fff" }}>
              💳 Pagar ahora
            </button>
          </div>
        </Card>
      )}

      {/* Alerta suspendida */}
      {isSusp && (
        <Card style={{ borderColor: "#FECACA", background: "#FEF2F2" }} padding={14}>
          <div style={{ display: "flex", alignItems: mob ? "stretch" : "center", gap: 12, flexDirection: mob ? "column" : "row" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, color: "#991B1B", fontSize: 13 }}>🔒 Cuenta suspendida</div>
              <div style={{ fontSize: 12, color: "#7F1D1D", marginTop: 2 }}>Tu acceso está bloqueado por falta de pago.</div>
            </div>
            <button onClick={handleReactivate} disabled={busy} style={{ ...pb, background: "#DC2626", color: "#fff" }}>
              Reactivar cuenta
            </button>
          </div>
        </Card>
      )}

      {/* Estado actual */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span style={{
                padding: "3px 10px", borderRadius: 99, fontSize: 11, fontWeight: 700,
                background: sc.bg, color: sc.color, border: `1px solid ${sc.bd}`
              }}>{sc.label}</span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-.03em" }}>
              {sub.plan.name}
              {!isFree && <span style={{ fontSize: 14, fontWeight: 500, color: C.mute, marginLeft: 8 }}>{CLP(sub.plan.price_clp)}/mes</span>}
            </div>
          </div>
          <div style={{ textAlign: mob ? "left" : "right" }}>
            {isTrial && sub.trial_ends_at && (
              <>
                <div style={{ fontSize: 11, color: C.mute }}>Trial vence</div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{fmtD(sub.trial_ends_at)}</div>
                <div style={{ fontSize: 12, color: sub.days_remaining! <= 3 ? C.red : C.mid }}>{sub.days_remaining} días</div>
              </>
            )}
            {!isTrial && sub.current_period_end && !isFree && (
              <>
                <div style={{ fontSize: 11, color: C.mute }}>Próximo cobro</div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{fmtD(sub.current_period_end)}</div>
                <div style={{ fontSize: 12, color: sub.days_remaining! <= 3 ? C.red : C.mid }}>{sub.days_remaining} días</div>
              </>
            )}
          </div>
        </div>

        {/* Límites */}
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(3, 1fr)", gap: 8, marginBottom: 16 }}>
          {[
            { l: "Productos", v: sub.plan.max_products === -1 ? "∞ ilimitados" : `hasta ${sub.plan.max_products}` },
            { l: "Locales",   v: sub.plan.max_stores === -1 ? "∞ ilimitados" : `hasta ${sub.plan.max_stores}` },
            { l: "Usuarios",  v: sub.plan.max_users === -1 ? "∞ ilimitados" : `hasta ${sub.plan.max_users}` },
            { l: "Forecast IA", v: sub.plan.has_forecast ? "✓ incluido" : "✗" },
            { l: "Análisis ABC", v: sub.plan.has_abc ? "✓ incluido" : "✗" },
            { l: "Transferencias", v: sub.plan.has_transfers ? "✓ incluido" : "✗" },
          ].map(i => (
            <div key={i.l} style={{ padding: "8px 12px", background: C.bg, borderRadius: 8, border: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 10, color: C.mute, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em" }}>{i.l}</div>
              <div style={{ fontSize: 13, fontWeight: 700, marginTop: 2, color: i.v.startsWith("✗") ? C.mute : i.v.startsWith("✓") ? C.green : C.text }}>{i.v}</div>
            </div>
          ))}
        </div>

        {/* Acciones */}
        {!isSusp && !isCanc && !isFree && (
          <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {isPD && <button onClick={handlePay} disabled={busy} style={{ ...pb, background: C.accent, color: "#fff" }}>💳 Pagar ahora</button>}
            <button onClick={() => setShowCancel(true)} disabled={busy}
              style={{ ...pb, background: "transparent", color: C.red, border: `1px solid #FECACA` }}>
              Cancelar suscripción
            </button>
          </div>
        )}
        {isCanc && (
          <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 14 }}>
            <button onClick={handleReactivate} disabled={busy} style={{ ...pb, background: C.accent, color: "#fff" }}>Reactivar suscripción</button>
          </div>
        )}
      </Card>

      {/* Método de pago */}
      {!isFree && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 10 }}>Método de pago</div>
          {sub.has_card ? (
            <div style={{ display: "flex", alignItems: mob ? "stretch" : "center", gap: 12, flexDirection: mob ? "column" : "row" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
                <div style={{ width: 44, height: 30, borderRadius: 6, background: C.bg, border: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 800, color: C.mid }}>
                  {sub.card_brand === "Visa" ? "VISA" : sub.card_brand === "Mastercard" ? "MC" : sub.card_brand?.slice(0, 4) || "CARD"}
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{sub.card_brand} •••• {sub.card_last4}</div>
                  <div style={{ fontSize: 11, color: C.green }}>Cobro automático activo</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={handleRegisterCard} disabled={busy}
                  style={{ ...pb, background: "transparent", color: C.mid, border: `1px solid ${C.border}`, fontSize: 12, padding: "6px 12px", minHeight: 34 }}>
                  Cambiar
                </button>
                <button onClick={handleRemoveCard} disabled={busy}
                  style={{ ...pb, background: "transparent", color: C.red, border: `1px solid #FECACA`, fontSize: 12, padding: "6px 12px", minHeight: 34 }}>
                  Eliminar
                </button>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: mob ? "stretch" : "center", gap: 12, flexDirection: mob ? "column" : "row" }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: C.mid }}>Sin tarjeta registrada. Los cobros se realizan manualmente.</div>
                <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>Registra tu tarjeta para activar el cobro automático mensual.</div>
              </div>
              <button onClick={handleRegisterCard} disabled={busy}
                style={{ ...pb, background: C.accent, color: "#fff", flexShrink: 0 }}>
                💳 Registrar tarjeta
              </button>
            </div>
          )}
        </Card>
      )}

      {/* Cuenta creada */}
      <Card style={{ borderColor: C.greenBd }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>✓</span>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: C.green }}>Cuenta activa</div>
            <div style={{ fontSize: 12, color: C.mute }}>Creada el {tenantCreatedAt ? new Date(tenantCreatedAt).toLocaleDateString("es-CL", { day: "numeric", month: "long", year: "numeric" }) : "—"}</div>
          </div>
        </div>
      </Card>

      {/* Cambiar plan */}
      <div style={{ fontSize: 14, fontWeight: 800 }}>Cambiar plan</div>
      <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
        {plans.map(p => {
          const cur = p.key === sub.plan.key;
          const up = p.price_clp > sub.plan.price_clp;
          return (
            <Card key={p.key} style={cur ? { borderColor: C.accent, boxShadow: `0 0 0 3px ${C.accentBg}` } : {}} padding={18}>
              {cur && <div style={{ textAlign: "center", background: C.accent, color: "#fff", padding: "3px 0", borderRadius: 99, fontSize: 10, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 8 }}>Plan actual</div>}
              <div style={{ fontSize: 13, fontWeight: 700, color: C.mid }}>{p.name}</div>
              <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-.04em", marginTop: 4 }}>
                {p.price_clp === 0 ? "Gratis" : <>{CLP(p.price_clp)}<span style={{ fontSize: 12, color: C.mute, fontWeight: 500 }}>/mes</span></>}
              </div>
              <ul style={{ listStyle: "none", margin: "10px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> {p.max_products === -1 ? "Productos ilimitados" : `Hasta ${p.max_products} productos`}</li>
                <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> {p.max_stores === -1 ? "Locales ilimitados" : `Hasta ${p.max_stores} local${p.max_stores > 1 ? "es" : ""}`}</li>
                <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> {p.max_users === -1 ? "Usuarios ilimitados" : `Hasta ${p.max_users} usuarios`}</li>
                {p.has_forecast && <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> Forecast IA</li>}
                {p.has_abc && <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> Análisis ABC</li>}
                {p.has_transfers && <li style={{ fontSize: 12, color: C.mid }}><span style={{ color: C.green, fontWeight: 900 }}>✓</span> Transferencias</li>}
              </ul>
              {!cur && (
                <button onClick={() => handleUpgrade(p.key)} disabled={busy}
                  style={{ ...pb, width: "100%", justifyContent: "center", marginTop: 12, ...(up ? { background: C.accent, color: "#fff" } : { background: "transparent", color: C.mid, border: `1.5px solid ${C.border}` }) }}>
                  {up ? `Subir a ${p.name}` : `Cambiar a ${p.name}`}
                </button>
              )}
            </Card>
          );
        })}
      </div>

      {/* Historial de pagos */}
      {sub.recent_invoices.length > 0 && (
        <>
          <div style={{ fontSize: 14, fontWeight: 800 }}>Historial de pagos</div>
          <Card padding={0}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: mob ? 500 : undefined }}>
                <thead>
                  <tr style={{ background: C.bg }}>
                    {["Período", "Monto", "Estado", "Fecha pago", ""].map(h => (
                      <th key={h} style={{ padding: "8px 12px", fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em", textAlign: "left" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sub.recent_invoices.map(inv => {
                    const is = INV_ST[inv.status] || { label: inv.status, color: C.mid };
                    return (
                      <tr key={inv.id} style={{ borderBottom: `1px solid ${C.bg}` }}>
                        <td style={{ padding: "10px 12px", fontSize: 12, fontFamily: "monospace" }}>{inv.period_start} → {inv.period_end}</td>
                        <td style={{ padding: "10px 12px", fontSize: 13, fontWeight: 700 }}>{CLP(inv.amount_clp)}</td>
                        <td style={{ padding: "10px 12px" }}>
                          <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 700, color: is.color, background: is.color + "18", border: `1px solid ${is.color}40` }}>{is.label}</span>
                        </td>
                        <td style={{ padding: "10px 12px", fontSize: 13 }}>{inv.paid_at ? fmtD(inv.paid_at) : "—"}</td>
                        <td style={{ padding: "10px 12px" }}>
                          {inv.payment_url && inv.status !== "paid" && (
                            <a href={inv.payment_url} style={{ fontSize: 12, color: C.accent, fontWeight: 600, textDecoration: "none" }}>Pagar →</a>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      {/* Modal cancelar */}
      {showCancel && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 999 }}>
          <div style={{ background: "#fff", borderRadius: 14, padding: 28, maxWidth: 420, width: "90%", boxShadow: "0 20px 60px rgba(0,0,0,.15)" }}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>⚠</div>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 8 }}>¿Cancelar suscripción?</div>
            <p style={{ fontSize: 13, color: C.mid, lineHeight: 1.6, marginBottom: 20 }}>
              Tu suscripción quedará activa hasta el <strong>{fmtD(sub.current_period_end)}</strong>.
              Después pasarás al plan Gratuito. Tus datos se conservan.
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setShowCancel(false)} style={{ ...pb, background: "transparent", color: C.mid, border: `1.5px solid ${C.border}` }}>No cancelar</button>
              <button onClick={handleCancel} disabled={busy} style={{ ...pb, background: "#DC2626", color: "#fff" }}>Sí, cancelar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}