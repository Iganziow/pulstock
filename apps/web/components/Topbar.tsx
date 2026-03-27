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

export default function Topbar() {
  const pathname = usePathname();
  const [user, setUser] = useState<UserData | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [activeStoreId, setActiveStoreId] = useState<number | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const storeRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);

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

  // Close dropdowns on outside click
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (storeRef.current && !storeRef.current.contains(e.target as Node)) setDropdownOpen(false);
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserMenuOpen(false);
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