"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { humanizeError } from "@/lib/errors";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import type { Me } from "@/lib/me";
import { Spinner, type Tenant, type Store, type User, type Tab } from "@/components/settings/SettingsUI";

import AccountTab from "@/components/settings/AccountTab";
import CompanyTab from "@/components/settings/CompanyTab";
import ReceiptTab from "@/components/settings/ReceiptTab";
import StoresTab from "@/components/settings/StoresTab";
import UsersTab from "@/components/settings/UsersTab";
import AlertsTab from "@/components/settings/AlertsTab";
import PrintersTab from "@/components/settings/PrintersTab";
import PlanTab from "@/components/settings/PlanTab";

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

  const reloadUsers = async () => {
    const u = await apiFetch("/core/users/").catch(() => []);
    setUsers(u || []);
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
        if (m?.permissions?.users) {
          const u = await apiFetch("/core/users/").catch(() => []);
          setUsers(u || []);
        }
      } catch (e: any) { flash("err", humanizeError(e, "Error cargando configuración")); }
      finally { setLoading(false); }
    })();
  }, []);

  /* ── Form helpers for tenant fields ── */
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
    } catch (e: any) { flash("err", humanizeError(e, "Error guardando")); }
    finally { setSaving(false); }
  };

  const saveAccount = async (body: { first_name: string; last_name: string; email: string; password?: string }) => {
    setSaving(true);
    try {
      await apiFetch(`/core/users/${me?.id}/`, { method: "PATCH", body: JSON.stringify(body) });
      flash("ok", body.password ? "Datos y contraseña actualizados" : "Datos actualizados");
    } catch (e: any) { flash("err", humanizeError(e, "Error guardando")); }
    finally { setSaving(false); }
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

      {/* Flash — toast animado con slide-in */}
      {msg && (
        <>
          <style>{`
            @keyframes pulstockFlashIn {
              from { opacity: 0; transform: translateY(-8px); }
              to   { opacity: 1; transform: translateY(0); }
            }
          `}</style>
          <div
            role="alert"
            style={{
              padding: "12px 16px",
              background: msg.type === "ok" ? C.greenBg : C.redBg,
              border: `1.5px solid ${msg.type === "ok" ? C.greenBd : C.redBd}`,
              borderRadius: 12,
              fontSize: 13,
              fontWeight: 500,
              color: msg.type === "ok" ? C.green : C.red,
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              lineHeight: 1.45,
              boxShadow: msg.type === "ok"
                ? "0 2px 8px rgba(22, 163, 74, 0.08)"
                : "0 2px 8px rgba(220, 38, 38, 0.12)",
              animation: "pulstockFlashIn 0.25s ease-out",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                flexShrink: 0,
                width: 20,
                height: 20,
                borderRadius: 99,
                background: msg.type === "ok" ? C.green : C.red,
                color: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: 700,
                marginTop: 1,
              }}
            >
              {msg.type === "ok" ? "✓" : "!"}
            </span>
            <span style={{ flex: 1, minWidth: 0, wordBreak: "break-word" }}>
              {msg.text}
            </span>
            <button
              onClick={() => setMsg(null)}
              aria-label="Cerrar"
              style={{
                flexShrink: 0,
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "inherit",
                fontSize: 20,
                lineHeight: 1,
                opacity: 0.6,
                padding: 0,
                width: 24,
                height: 24,
              }}
              onMouseEnter={(e) => ((e.target as HTMLElement).style.opacity = "1")}
              onMouseLeave={(e) => ((e.target as HTMLElement).style.opacity = "0.6")}
            >
              ×
            </button>
          </div>
        </>
      )}

      {/* Tab content */}
      {tab === "cuenta" && me && (
        <AccountTab me={me} onSave={saveAccount} saving={saving} mob={mob} />
      )}

      {tab === "empresa" && (
        <CompanyTab form={form} f={f} set={set} onSave={saveTenant} saving={saving} mob={mob} />
      )}

      {tab === "boleta" && (
        <ReceiptTab f={f} set={set} onSave={saveTenant} saving={saving} />
      )}

      {tab === "tiendas" && (
        <StoresTab stores={stores} onRefresh={reloadStores} flash={flash} />
      )}

      {tab === "usuarios" && isOwner && me && (
        <UsersTab users={users} me={me} stores={stores} onRefresh={reloadUsers} flash={flash} />
      )}

      {tab === "alertas" && (
        <AlertsTab initialStates={alertStates} />
      )}

      {tab === "impresoras" && <PrintersTab mob={mob} flash={flash} />}

      {tab === "plan" && <PlanTab mob={mob} flash={flash} tenantCreatedAt={tenant?.created_at} />}
    </div>
  );
}
