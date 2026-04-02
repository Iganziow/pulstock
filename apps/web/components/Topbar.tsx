"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import { apiFetch, clearTokens } from "@/lib/api";
import { C } from "@/lib/theme";

// ─── Design tokens ────────────────────────────────────────────────────────────


// ─── Route → breadcrumb mapping ───────────────────────────────────────────────

const ROUTE_LABELS: Record<string, string> = {
  "/dashboard":                 "Dashboard",
  "/dashboard/catalog":         "Catálogo",
  "/dashboard/pos":             "Punto de Venta",
  "/dashboard/sales":           "Ventas",
  "/dashboard/purchases":       "Compras",
  "/dashboard/purchases/new":   "Nueva Compra",
  "/dashboard/reports":         "Reportes",
  "/dashboard/inventory/stock": "Stock",
  "/dashboard/inventory/kardex":"Kardex",
  "/dashboard/prices":          "Lista de Precios",
  "/dashboard/promotions":      "Ofertas y Promociones",
  "/dashboard/settings":        "Configuración",
};

function getBreadcrumb(pathname: string): string {
  if (ROUTE_LABELS[pathname]) return ROUTE_LABELS[pathname];
  // Match dynamic routes like /dashboard/sales/123
  for (const [route, label] of Object.entries(ROUTE_LABELS)) {
    if (pathname.startsWith(route + "/")) return label;
  }
  return "Dashboard";
}

// ─── Types ────────────────────────────────────────────────────────────────────

type UserData = {
  id: number;
  email: string;
  username?: string;
  tenant_id: number;
  active_store_id: number;
  default_warehouse_id: number | null;
};

type Store = {
  id: number;
  name: string;
  code?: string;
  is_active: boolean;
};

// ─── Component ────────────────────────────────────────────────────────────────

type Notification = { type: string; icon: string; title: string; description: string; link: string; severity: string };

export default function Topbar() {
  const pathname = usePathname();
  const [user, setUser] = useState<UserData | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [activeStoreId, setActiveStoreId] = useState<number | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [notifCount, setNotifCount] = useState(0);
  const storeRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  // Fetch user + stores
  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        const [me, storeList] = await Promise.all([
          apiFetch("/core/me/"),
          apiFetch("/stores/").catch(() => []),
        ]);
        if (mounted) {
          setUser(me);
          setActiveStoreId(me.active_store_id);
          if (Array.isArray(storeList)) {
            setStores(storeList.filter((s: Store) => s.is_active));
          } else if (storeList?.results) {
            setStores(storeList.results.filter((s: Store) => s.is_active));
          }
        }
      } catch { /* silent */ }
    }

    load();
    return () => { mounted = false; };
  }, []);

  // Load notifications
  useEffect(() => {
    let mounted = true;
    async function fetchNotifs() {
      try {
        const res = await apiFetch("/core/notifications/");
        if (mounted) {
          setNotifications(res?.notifications || []);
          setNotifCount(res?.count || 0);
        }
      } catch { /* silent */ }
    }
    fetchNotifs();
    const id = setInterval(fetchNotifs, 300_000); // every 5 min
    return () => { mounted = false; clearInterval(id); };
  }, []);

  // Close dropdowns on outside click
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (storeRef.current && !storeRef.current.contains(e.target as Node)) setDropdownOpen(false);
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserMenuOpen(false);
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function switchStore(storeId: number) {
    try {
      await apiFetch("/stores/set-active/", {
        method: "POST",
        body: JSON.stringify({ store_id: storeId }),
      });
      setActiveStoreId(storeId);
      setDropdownOpen(false);
      // Reload to refresh all data with new store context
      window.location.reload();
    } catch { /* silent */ }
  }

  const activeStore = stores.find(s => s.id === activeStoreId);
  const breadcrumb = getBreadcrumb(pathname);
  const displayName = user?.username || user?.email || "Usuario";
  const initials = displayName.slice(0, 2).toUpperCase();

  return (
    <header style={{
      height: 56,
      background: C.surface,
      borderBottom: `1px solid ${C.border}`,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "0 24px",
      fontFamily: C.font,
      flexShrink: 0,
    }}>

      {/* Left: Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 13, color: C.mute, fontWeight: 500 }}>
          {breadcrumb !== "Dashboard" && (
            <>
              <span style={{ cursor: "default" }}>Dashboard</span>
              <span style={{ margin: "0 6px", color: C.border }}>/</span>
            </>
          )}
          <span style={{ color: C.text, fontWeight: 600 }}>{breadcrumb}</span>
        </span>
      </div>

      {/* Right: Store selector + User */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>

        {/* Store selector */}
        {stores.length > 0 && (
          <div ref={storeRef} style={{ position: "relative" }}>
            <button
              onClick={() => { setDropdownOpen(!dropdownOpen); setUserMenuOpen(false); }}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "6px 12px", borderRadius: 8,
                border: `1px solid ${C.border}`, background: C.bg,
                cursor: "pointer", fontFamily: C.font, fontSize: 12,
                fontWeight: 600, color: C.mid,
                transition: "all 0.12s ease",
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = C.borderMd; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = C.border; }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.accent} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
              </svg>
              <span>{activeStore?.name || "Tienda"}</span>
              {stores.length > 1 && (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              )}
            </button>

            {/* Dropdown */}
            {dropdownOpen && stores.length > 1 && (
              <div style={{
                position: "absolute", top: "calc(100% + 6px)", right: 0,
                background: C.surface, border: `1px solid ${C.border}`,
                borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                padding: 6, minWidth: 200, zIndex: 100,
              }}>
                {stores.map(store => (
                  <button
                    key={store.id}
                    onClick={() => switchStore(store.id)}
                    style={{
                      display: "flex", alignItems: "center", gap: 10,
                      width: "100%", padding: "8px 12px", borderRadius: 6,
                      border: "none", cursor: "pointer", fontFamily: C.font,
                      fontSize: 13, fontWeight: store.id === activeStoreId ? 600 : 400,
                      color: store.id === activeStoreId ? C.accent : C.text,
                      background: store.id === activeStoreId ? C.accentBg : "transparent",
                      transition: "background 0.1s ease",
                      textAlign: "left",
                    }}
                    onMouseEnter={(e) => {
                      if (store.id !== activeStoreId)
                        (e.currentTarget as HTMLElement).style.background = C.bg;
                    }}
                    onMouseLeave={(e) => {
                      if (store.id !== activeStoreId)
                        (e.currentTarget as HTMLElement).style.background = "transparent";
                    }}
                  >
                    {store.id === activeStoreId && (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.accent} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                    )}
                    <span>{store.name}</span>
                    {store.code && <span style={{ fontSize: 11, color: C.mute, marginLeft: "auto" }}>{store.code}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Notification bell */}
        <div ref={notifRef} style={{ position: "relative" }}>
          <button
            onClick={() => { setNotifOpen(!notifOpen); setDropdownOpen(false); setUserMenuOpen(false); }}
            style={{
              position: "relative", display: "flex", alignItems: "center", justifyContent: "center",
              width: 36, height: 36, borderRadius: 8, border: "none",
              background: notifOpen ? C.bg : "transparent", cursor: "pointer",
              transition: "background .12s",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = C.bg; }}
            onMouseLeave={e => { if (!notifOpen) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={notifCount > 0 ? C.accent : C.mute} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
            {notifCount > 0 && (
              <span style={{
                position: "absolute", top: 2, right: 2,
                width: 16, height: 16, borderRadius: "50%",
                background: C.red, color: "#fff", fontSize: 9, fontWeight: 700,
                display: "flex", alignItems: "center", justifyContent: "center",
                lineHeight: 1, border: "2px solid " + C.surface,
              }}>
                {notifCount > 9 ? "9+" : notifCount}
              </span>
            )}
          </button>

          {notifOpen && (
            <div style={{
              position: "absolute", top: "calc(100% + 6px)", right: 0,
              background: C.surface, border: `1px solid ${C.border}`,
              borderRadius: 12, boxShadow: "0 12px 32px rgba(0,0,0,0.14)",
              width: 360, maxHeight: 420, overflow: "hidden", zIndex: 100,
            }}>
              <div style={{
                padding: "12px 16px", borderBottom: `1px solid ${C.border}`,
                display: "flex", justifyContent: "space-between", alignItems: "center",
              }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>Notificaciones</span>
                <span style={{ fontSize: 11, color: C.mute }}>{notifCount} alerta(s)</span>
              </div>
              <div style={{ maxHeight: 360, overflowY: "auto" }}>
                {notifications.length === 0 ? (
                  <div style={{ padding: 32, textAlign: "center", color: C.mute, fontSize: 13 }}>
                    Sin alertas por ahora
                  </div>
                ) : (
                  notifications.map((n, i) => (
                    <a key={i} href={n.link}
                      onClick={() => setNotifOpen(false)}
                      style={{
                        display: "flex", gap: 10, padding: "12px 16px",
                        borderBottom: `1px solid ${C.border}`, textDecoration: "none", color: "inherit",
                        background: n.severity === "critical" ? "#FEF2F2" : "transparent",
                        transition: "background .1s",
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = C.bg; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = n.severity === "critical" ? "#FEF2F2" : "transparent"; }}
                    >
                      <span style={{ fontSize: 20, flexShrink: 0, lineHeight: 1.2 }}>{n.icon}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{
                          fontSize: 13, fontWeight: 600,
                          color: n.severity === "critical" ? C.red : C.text,
                        }}>{n.title}</div>
                        <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{n.description}</div>
                      </div>
                      <span style={{ fontSize: 12, color: C.accent, flexShrink: 0, alignSelf: "center" }}>→</span>
                    </a>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* User avatar + menu */}
        <div ref={userRef} style={{ position: "relative" }}>
          <button
            onClick={() => { setUserMenuOpen(!userMenuOpen); setDropdownOpen(false); }}
            style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: 4, borderRadius: 8,
              border: "none", background: "transparent",
              cursor: "pointer", transition: "all 0.12s ease",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = C.bg; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
          >
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: C.accentBg, border: `1px solid ${C.accentBd}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, fontWeight: 700, color: C.accent,
            }}>
              {initials}
            </div>
          </button>

          {userMenuOpen && (
            <div style={{
              position: "absolute", top: "calc(100% + 6px)", right: 0,
              background: C.surface, border: `1px solid ${C.border}`,
              borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
              padding: 6, minWidth: 200, zIndex: 100,
            }}>
              {/* User info */}
              <div style={{ padding: "10px 12px 8px", borderBottom: `1px solid ${C.border}`, marginBottom: 4 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{displayName}</div>
                {user?.email && <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{user.email}</div>}
              </div>

              {/* Settings */}
              <button
                onClick={() => { setUserMenuOpen(false); window.location.href = "/dashboard/settings"; }}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  width: "100%", padding: "8px 12px", borderRadius: 6,
                  border: "none", cursor: "pointer", fontFamily: C.font,
                  fontSize: 13, fontWeight: 500, color: C.text,
                  background: "transparent", textAlign: "left",
                  transition: "background 0.1s ease",
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = C.bg; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.mid} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                </svg>
                Configuración
              </button>

              {/* Logout */}
              <button
                onClick={() => { clearTokens(); window.location.href = "/login"; }}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  width: "100%", padding: "8px 12px", borderRadius: 6,
                  border: "none", cursor: "pointer", fontFamily: C.font,
                  fontSize: 13, fontWeight: 500, color: C.red,
                  background: "transparent", textAlign: "left",
                  transition: "background 0.1s ease",
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#FEF2F2"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.red} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
                </svg>
                Cerrar sesión
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}   