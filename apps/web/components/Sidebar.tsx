"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, clearTokens } from "@/lib/api";
import { C } from "@/lib/theme";
import { LogoIcon } from "@/components/ui/Logo";

// ─── Design tokens ────────────────────────────────────────────────────────────


// ─── SVG Icons (inline, no deps) ─────────────────────────────────────────────

const icons: Record<string, React.ReactNode> = {
  dashboard: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
    </svg>
  ),
  catalog: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      <polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>
    </svg>
  ),
  pos: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
    </svg>
  ),
  sales: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
    </svg>
  ),
  purchases: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
    </svg>
  ),
  reports: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
    </svg>
  ),
  stock: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
    </svg>
  ),
  kardex: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
    </svg>
  ),
  prices: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>
    </svg>
  ),
  offers: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>
    </svg>
  ),
  forecast: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.04-4.79A3 3 0 0 1 4.5 11a3 3 0 0 1 1.5-2.6A2.5 2.5 0 0 1 9.5 2z"/>
      <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.04-4.79A3 3 0 0 0 19.5 11a3 3 0 0 0-1.5-2.6A2.5 2.5 0 0 0 14.5 2z"/>
    </svg>
  ),
  logout: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  ),
};

// ─── Nav config ───────────────────────────────────────────────────────────────

type NavItem = {
  href: string;
  label: string;
  icon: keyof typeof icons;
  section?: string;
  badge?: number;
  requires?: string; // permission key from ROLE_PERMISSIONS
};

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard",                label: "Dashboard",  icon: "dashboard" },
  { href: "/dashboard/catalog",        label: "Catálogo",   icon: "catalog",   section: "Productos", requires: "catalog" },
  { href: "/dashboard/catalog/recetas", label: "Recetas",   icon: "catalog",   requires: "catalog" },
  { href: "/dashboard/prices",         label: "Precios",    icon: "prices",    requires: "catalog_write" },
  { href: "/dashboard/pos",            label: "Punto de Venta", icon: "pos",   section: "Ventas",    requires: "pos" },
  { href: "/dashboard/sales",          label: "Ventas",     icon: "sales",     requires: "sales" },
  { href: "/dashboard/caja",           label: "Caja",       icon: "sales",     requires: "caja" },
  { href: "/dashboard/mesas",          label: "Mesas",      icon: "pos",       requires: "pos" },
  { href: "/dashboard/promotions",     label: "Ofertas",    icon: "offers",    requires: "catalog_write" },
  { href: "/dashboard/purchases",      label: "Compras",    icon: "purchases", section: "Inventario", requires: "purchases" },
  { href: "/dashboard/inventory/stock", label: "Stock",     icon: "stock",     requires: "inventory" },
  { href: "/dashboard/inventory/kardex", label: "Kardex",   icon: "kardex",    requires: "inventory" },
  { href: "/dashboard/inventory/salidas", label: "Salidas",  icon: "stock",    requires: "inventory_write" },
  { href: "/dashboard/forecast",       label: "Predicción", icon: "forecast",  section: "Inteligencia", requires: "forecast" },
  { href: "/dashboard/reports",        label: "Reportes",   icon: "reports",   section: "Análisis", requires: "reports" },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function Sidebar() {
  const pathname = usePathname();
  const [lowStock, setLowStock] = useState(0);
  const [collapsed, setCollapsed] = useState(false);
  const [perms, setPerms] = useState<Record<string, boolean> | null>(null);
  const [me, setMe] = useState<{ email?: string; role_label?: string } | null>(null);

  // Load user permissions + low stock
  useEffect(() => {
    let mounted = true;

    async function fetchData() {
      try {
        const [meRes, dashRes] = await Promise.all([
          apiFetch("/core/me/").catch(() => null),
          apiFetch("/dashboard/summary/").catch(() => null),
        ]);
        if (!mounted) return;
        if (meRes?.permissions) setPerms(meRes.permissions);
        if (meRes) setMe({ email: meRes.email, role_label: meRes.role_label });
        if (dashRes?.kpis?.low_stock?.count != null) setLowStock(dashRes.kpis.low_stock.count);
      } catch { /* silent */ }
    }

    fetchData();
    const id = setInterval(fetchData, 300_000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  function isActive(href: string): boolean {
    if (pathname === href) return true;
    if (href === "/dashboard") return false;
    if (!pathname.startsWith(href)) return false;
    // Don't match if a more specific menu item matches
    return !NAV_ITEMS.some(
      m => m.href !== href && m.href.length > href.length && pathname.startsWith(m.href)
    );
  }

  function handleLogout() {
    clearTokens();
    window.location.href = "/login";
  }

  // Filter by role permissions + inject badges
  const items = NAV_ITEMS
    .filter(item => !item.requires || !perms || perms[item.requires] !== false)
    .map(item => ({
      ...item,
      badge: item.icon === "stock" ? lowStock : undefined,
    }));

  // Group by section
  let lastSection = "";

  return (
    <aside style={{
      width: collapsed ? 68 : 240,
      minHeight: "100vh",
      background: C.surface,
      borderRight: `1px solid ${C.border}`,
      display: "flex",
      flexDirection: "column",
      transition: "width 0.2s ease",
      fontFamily: C.font,
      flexShrink: 0,
      overflow: "hidden",
    }}>

      {/* Brand */}
      <div style={{
        padding: collapsed ? "20px 12px 16px" : "20px 20px 16px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        borderBottom: `1px solid ${C.border}`,
      }}>
        <LogoIcon size={36} />
        {!collapsed && (
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, color: C.text, lineHeight: 1.1 }}>Pulstock</div>
            <div style={{ fontSize: 10, color: C.mute, fontWeight: 500, marginTop: 1 }}>Sistema de gestión</div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: "12px 10px", display: "flex", flexDirection: "column", gap: 2, overflowY: "auto" }}>
        {items.map((item) => {
          const active = isActive(item.href);
          const showSection = !collapsed && item.section && item.section !== lastSection;
          if (item.section) lastSection = item.section;

          return (
            <div key={item.href}>
              {showSection && (
                <div style={{
                  fontSize: 10, fontWeight: 600, color: C.mute,
                  textTransform: "uppercase", letterSpacing: "0.06em",
                  padding: "14px 10px 4px",
                }}>
                  {item.section}
                </div>
              )}
              <Link href={item.href} style={{ textDecoration: "none" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: collapsed ? "10px 0" : "9px 12px",
                    borderRadius: 8,
                    background: active ? C.accentBg : "transparent",
                    color: active ? C.accent : C.mid,
                    fontWeight: active ? 600 : 500,
                    fontSize: 13,
                    transition: "all 0.12s ease",
                    cursor: "pointer",
                    justifyContent: collapsed ? "center" : "flex-start",
                    border: active ? `1px solid ${C.accentBd}` : "1px solid transparent",
                    position: "relative",
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      (e.currentTarget as HTMLElement).style.background = C.bg;
                      (e.currentTarget as HTMLElement).style.color = C.text;
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      (e.currentTarget as HTMLElement).style.background = "transparent";
                      (e.currentTarget as HTMLElement).style.color = C.mid;
                    }
                  }}
                >
                  <span style={{ display: "flex", flexShrink: 0 }}>{icons[item.icon]}</span>
                  {!collapsed && <span>{item.label}</span>}

                  {/* Badge */}
                  {item.badge != null && item.badge > 0 && (
                    <span style={{
                      marginLeft: collapsed ? 0 : "auto",
                      position: collapsed ? "absolute" : "relative",
                      top: collapsed ? 4 : "auto",
                      right: collapsed ? 4 : "auto",
                      background: C.red,
                      color: "#fff",
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "1px 6px",
                      borderRadius: 99,
                      minWidth: 18,
                      textAlign: "center",
                      lineHeight: "16px",
                    }}>
                      {item.badge > 99 ? "99+" : item.badge}
                    </span>
                  )}
                </div>
              </Link>
            </div>
          );
        })}
      </nav>

      {/* User info */}
      {!collapsed && me && (
        <div style={{ padding: "10px 16px", borderTop: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, background: C.accentBg,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, fontWeight: 700, color: C.accent, flexShrink: 0,
          }}>
            {(me.email || "U")[0].toUpperCase()}
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{me.email}</div>
            <div style={{ fontSize: 10, color: C.mute }}>{me.role_label}</div>
          </div>
        </div>
      )}

      {/* Bottom: Collapse + Logout */}
      <div style={{
        padding: "12px 10px 16px",
        borderTop: `1px solid ${C.border}`,
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}>
        {/* Collapse toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: collapsed ? "9px 0" : "9px 12px",
            borderRadius: 8, border: "none",
            background: "transparent", color: C.mute,
            fontSize: 13, fontWeight: 500, cursor: "pointer",
            transition: "all 0.12s ease",
            justifyContent: collapsed ? "center" : "flex-start",
            fontFamily: C.font, width: "100%",
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = C.bg; (e.currentTarget as HTMLElement).style.color = C.mid; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; (e.currentTarget as HTMLElement).style.color = C.mute; }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            style={{ transform: collapsed ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}>
            <polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/>
          </svg>
          {!collapsed && <span>Colapsar</span>}
        </button>

        {/* Settings */}
        <Link href="/dashboard/settings" style={{ textDecoration: "none" }}>
          <div
            style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: collapsed ? "9px 0" : "9px 12px",
              borderRadius: 8,
              background: isActive("/dashboard/settings") ? C.accentBg : "transparent",
              color: isActive("/dashboard/settings") ? C.accent : C.mute,
              fontWeight: isActive("/dashboard/settings") ? 600 : 500,
              fontSize: 13,
              transition: "all 0.12s ease",
              cursor: "pointer",
              justifyContent: collapsed ? "center" : "flex-start",
              border: isActive("/dashboard/settings") ? `1px solid ${C.accentBd}` : "1px solid transparent",
            }}
            onMouseEnter={(e) => {
              if (!isActive("/dashboard/settings")) {
                (e.currentTarget as HTMLElement).style.background = C.bg;
                (e.currentTarget as HTMLElement).style.color = C.text;
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive("/dashboard/settings")) {
                (e.currentTarget as HTMLElement).style.background = "transparent";
                (e.currentTarget as HTMLElement).style.color = C.mute;
              }
            }}
          >
            <span style={{ display: "flex", flexShrink: 0 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </span>
            {!collapsed && <span>Configuración</span>}
          </div>
        </Link>

        {/* Logout */}
        <button
          onClick={handleLogout}
          style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: collapsed ? "9px 0" : "9px 12px",
            borderRadius: 8, border: "none",
            background: "transparent", color: C.mute,
            fontSize: 13, fontWeight: 500, cursor: "pointer",
            transition: "all 0.12s ease",
            justifyContent: collapsed ? "center" : "flex-start",
            fontFamily: C.font, width: "100%",
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#FEF2F2"; (e.currentTarget as HTMLElement).style.color = C.red; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; (e.currentTarget as HTMLElement).style.color = C.mute; }}
        >
          <span style={{ display: "flex", flexShrink: 0 }}>{icons.logout}</span>
          {!collapsed && <span>Cerrar sesión</span>}
        </button>
      </div>
    </aside>
  );
}