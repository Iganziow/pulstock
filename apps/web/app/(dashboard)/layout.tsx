"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { apiFetch, clearTokens } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile, useIsTablet } from "@/hooks/useIsMobile";
import { ErrorBoundary } from "@/components/ErrorBoundary";

// ─── Design tokens ────────────────────────────────────────────────────────────


const MOBILE_BP = 768;
const SIDEBAR_W = 240;
const SIDEBAR_COLLAPSED_W = 68;
const TOPBAR_H = 52;

// ─── CSS ──────────────────────────────────────────────────────────────────────

const LAYOUT_CSS = `
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&family=JetBrains+Mono:wght@400;500&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'DM Sans','Helvetica Neue',system-ui,sans-serif;overscroll-behavior:none}
@keyframes slideIn{from{transform:translateX(-100%)}to{transform:translateX(0)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.mobile-nav::-webkit-scrollbar{display:none}
.mobile-nav{-ms-overflow-style:none;scrollbar-width:none}
.safe-bottom{padding-bottom:max(12px,env(safe-area-inset-bottom))}
.safe-top{padding-top:max(0px,env(safe-area-inset-top))}
.sb-link{text-decoration:none;}
.sb-link .sb-item{transition:all 0.15s cubic-bezier(0.4,0,0.2,1);}
.sb-link .sb-item:hover{background:#F4F4F5;color:#18181B;}
.sb-link .sb-item.active{background:#EEF2FF;color:#4F46E5;}
.sb-link .sb-item.active:hover{background:#E0E7FF;}
.sb-tooltip{position:absolute;left:calc(100% + 8px);top:50%;transform:translateY(-50%);background:#18181B;color:#fff;font-size:12px;font-weight:600;padding:4px 10px;border-radius:6px;white-space:nowrap;pointer-events:none;opacity:0;transition:opacity 0.12s ease;z-index:200;}
.sb-item:hover .sb-tooltip{opacity:1;}
.topbar-btn{background:none;border:1px solid transparent;cursor:pointer;border-radius:8px;display:flex;align-items:center;gap:8px;padding:6px 10px;transition:all 0.12s ease;font-family:inherit;color:${C.mid};}
.topbar-btn:hover{background:${C.bg};border-color:${C.border};}
`;

function useLayoutStyles() {
  useEffect(() => {
    const id = "layout-pwa-v2";
    if (document.getElementById(id)) return;
    const el = document.createElement("style");
    el.id = id;
    el.textContent = LAYOUT_CSS;
    document.head.appendChild(el);
  }, []);
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const icons: Record<string, React.ReactNode> = {
    dashboard: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>,
    catalog: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>,
    pos: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>,
    sales: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>,
    purchases: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>,
    stock: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>,
    kardex: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>,
    reports: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>,
    forecast: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>,
    caja: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/><line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/></svg>,
    mesas: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v6"/><path d="M19 12v6"/><path d="M5 18h14"/></svg>,
    recetas: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="9" y1="12" x2="15" y2="12"/></svg>,
    settings: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
    users: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>,
    logout: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>,
    menu: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>,
    close: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>,
    store: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
    chevronLeft: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/></svg>,
    chevronDown: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="6 9 12 15 18 9"/></svg>,
    check: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><polyline points="20 6 9 17 4 12"/></svg>,
    search: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>,
  };
  return <>{icons[name] || null}</>;
}

// ─── Types ────────────────────────────────────────────────────────────────────

type Perms = Record<string, boolean>;
type NavItem = { href: string; label: string; icon: string; section?: string; perm?: string };
type Store = { id: number; name: string; code?: string; is_active: boolean };

// ─── Nav config ───────────────────────────────────────────────────────────────

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard",                 label: "Dashboard",      icon: "dashboard" },
  { href: "/dashboard/catalog",         label: "Catálogo",       icon: "catalog",   section: "Productos", perm: "catalog" },
  { href: "/dashboard/catalog/recetas", label: "Recetas",        icon: "recetas",   perm: "catalog" },
  { href: "/dashboard/pos",             label: "Punto de Venta", icon: "pos",       section: "Ventas",    perm: "pos" },
  { href: "/dashboard/sales",           label: "Ventas",         icon: "sales",     perm: "sales" },
  { href: "/dashboard/caja",            label: "Caja",           icon: "caja",      perm: "caja" },
  { href: "/dashboard/mesas",           label: "Mesas",          icon: "mesas",     perm: "pos" },
  { href: "/dashboard/purchases",       label: "Compras",        icon: "purchases", section: "Inventario", perm: "purchases" },
  { href: "/dashboard/inventory/stock", label: "Stock",          icon: "stock",     perm: "inventory" },
  { href: "/dashboard/inventory/kardex",label: "Kardex",         icon: "kardex",    perm: "inventory" },
  { href: "/dashboard/inventory/salidas",label: "Salidas",      icon: "stock",     perm: "inventory" },
  { href: "/dashboard/reports",         label: "Reportes",       icon: "reports",   section: "Análisis",  perm: "reports" },
  { href: "/dashboard/forecast",        label: "Predicción",     icon: "forecast",  section: "Inteligencia", perm: "forecast" },
  { href: "/dashboard/settings",        label: "Configuración",  icon: "settings",  section: "Sistema",   perm: "settings" },
];

const BOTTOM_NAV = [
  { href: "/dashboard",                 label: "Inicio",  icon: "dashboard" },
  { href: "/dashboard/pos",             label: "POS",     icon: "pos",   perm: "pos" },
  { href: "/dashboard/inventory/stock", label: "Stock",   icon: "stock", perm: "inventory" },
  { href: "/dashboard/sales",           label: "Ventas",  icon: "sales", perm: "sales" },
];

// ─── Route → breadcrumb ──────────────────────────────────────────────────────

const ROUTE_LABELS: Record<string, string> = {
  "/dashboard":                  "Dashboard",
  "/dashboard/catalog":          "Catálogo",
  "/dashboard/catalog/recetas":  "Recetas",
  "/dashboard/pos":              "Punto de Venta",
  "/dashboard/sales":            "Ventas",
  "/dashboard/purchases":        "Compras",
  "/dashboard/purchases/new":    "Nueva Compra",
  "/dashboard/reports":          "Reportes",
  "/dashboard/inventory/stock":  "Stock",
  "/dashboard/inventory/kardex": "Kardex",
  "/dashboard/inventory/salidas": "Salidas",
  "/dashboard/caja":             "Caja",
  "/dashboard/mesas":            "Mesas",
  "/dashboard/mesas/config":     "Config. Mesas",
  "/dashboard/forecast":         "Predicción",
  "/dashboard/settings":         "Configuración",
};

function getBreadcrumbs(pathname: string): { label: string; href?: string }[] {
  const crumbs: { label: string; href?: string }[] = [];
  // Try exact match first
  if (ROUTE_LABELS[pathname]) {
    if (pathname !== "/dashboard") {
      crumbs.push({ label: "Dashboard", href: "/dashboard" });
    }
    crumbs.push({ label: ROUTE_LABELS[pathname] });
    return crumbs;
  }
  // Try parent routes
  const parts = pathname.split("/").filter(Boolean);
  let path = "";
  for (const part of parts) {
    path += "/" + part;
    if (ROUTE_LABELS[path]) {
      crumbs.push({ label: ROUTE_LABELS[path], href: path });
    }
  }
  if (crumbs.length > 0) {
    // Remove href from last item (current page)
    crumbs[crumbs.length - 1] = { label: crumbs[crumbs.length - 1].label };
  } else {
    crumbs.push({ label: "Dashboard" });
  }
  return crumbs;
}

// ─── Hooks ────────────────────────────────────────────────────────────────────

const ROLE_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  owner:     { bg: "#EEF2FF", fg: "#4F46E5", label: "Dueño/Gerente" },
  manager:   { bg: "#FFFBEB", fg: "#D97706", label: "Administrador" },
  cashier:   { bg: "#F0FDF4", fg: "#16A34A", label: "Caja/Garzón" },
  inventory: { bg: "#FFF7ED", fg: "#EA580C", label: "Inventario" },
};

// ─── Component ────────────────────────────────────────────────────────────────

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  useLayoutStyles();
  const pathname = usePathname();
  const isMobile = useIsMobile();
  const isTablet = useIsTablet();
  const [drawerOpen, setDrawerOpen] = useState(false);
  // En tablet horizontal (iPad acostado, 1024px) auto-colapsamos la sidebar
  // por defecto — sino el contenido queda muy comprimido (240px sidebar +
  // tabla larga = scroll horizontal molesto).
  const [collapsed, setCollapsed] = useState(false);
  const [lowStock, setLowStock] = useState(0);
  const [perms, setPerms] = useState<Perms | null>(null);
  const [userRole, setUserRole] = useState("");
  const [userName, setUserName] = useState("");
  const [userEmail, setUserEmail] = useState("");
  const [stores, setStores] = useState<Store[]>([]);
  const [activeStoreId, setActiveStoreId] = useState<number | null>(null);
  const [storeDropOpen, setStoreDropOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const storeRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setDrawerOpen(false); }, [pathname]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setDrawerOpen(false); setStoreDropOpen(false); setUserMenuOpen(false); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Close dropdowns on outside click
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (storeRef.current && !storeRef.current.contains(e.target as Node)) setStoreDropOpen(false);
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserMenuOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Load user info + permissions + stores
  useEffect(() => {
    let m = true;
    async function load() {
      try {
        const [me, storeList] = await Promise.all([
          apiFetch("/core/me/"),
          apiFetch("/stores/").catch(() => []),
        ]);
        if (!m) return;
        if (me?.permissions) setPerms(me.permissions);
        setUserRole((me?.role || "").toLowerCase());
        setUserName(me?.first_name || me?.username || "");
        setUserEmail(me?.email || "");
        setActiveStoreId(me?.active_store_id || null);
        const list = Array.isArray(storeList) ? storeList : storeList?.results || [];
        setStores(list.filter((s: Store) => s.is_active));
      } catch (e) { console.error("Layout: error cargando datos de usuario/tiendas:", e); }
    }
    load();
    return () => { m = false; };
  }, []);

  // Low stock badge
  useEffect(() => {
    let m = true;
    const fetch = async () => {
      try {
        const r = await apiFetch("/dashboard/summary/");
        if (m && r?.kpis?.low_stock?.count != null) setLowStock(r.kpis.low_stock.count);
      } catch (e) { console.error("Layout: error cargando resumen de stock bajo:", e); }
    };
    fetch();
    // Daniel 30/04/26 — Fase 1: subido de 5min a 10min. Esto es solo
    // para el badge de stock bajo del layout (sidebar/topbar).
    const id = setInterval(fetch, 600_000);
    return () => { m = false; clearInterval(id); };
  }, []);

  // Read collapsed preference. En tablet horizontal: si el user no expresó
  // preferencia explícita ("0" o "1"), forzamos colapsado por default.
  useEffect(() => {
    try {
      const v = localStorage.getItem("sb_collapsed");
      if (v === "1") setCollapsed(true);
      else if (v === null && isTablet) setCollapsed(true);  // tablet default
    } catch (e) { console.error("Layout: error leyendo preferencia sidebar colapsado:", e); }
  }, [isTablet]);

  const toggleCollapsed = useCallback(() => {
    setCollapsed(v => {
      const next = !v;
      try { localStorage.setItem("sb_collapsed", next ? "1" : "0"); } catch (e) { console.error("Layout: error guardando preferencia sidebar colapsado:", e); }
      return next;
    });
  }, []);

  const isActive = useCallback((href: string) => {
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname === href || pathname.startsWith(href + "/");
  }, [pathname]);

  const canSee = useCallback((perm?: string) => {
    if (!perm) return true;
    if (!perms) return true;
    return !!perms[perm];
  }, [perms]);

  const handleLogout = useCallback(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"}/auth/logout/`, {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include",
    }).catch(() => {}).finally(() => { clearTokens(); window.location.href = "/login"; });
  }, []);

  const switchStore = useCallback(async (storeId: number) => {
    try {
      await apiFetch("/stores/set-active/", { method: "POST", body: JSON.stringify({ store_id: storeId }) });
      setActiveStoreId(storeId);
      setStoreDropOpen(false);
      window.location.reload();
    } catch (e) { console.error("Layout: error cambiando tienda activa:", e); }
  }, []);

  // Receipt page renders standalone (no sidebar/topbar)
  const isReceiptPage = pathname.startsWith("/dashboard/pos/receipt/");

  const visibleNav = useMemo(() => NAV_ITEMS.filter(i => canSee(i.perm)), [canSee]);
  const visibleBottom = useMemo(() => BOTTOM_NAV.filter(i => canSee(i.perm)), [canSee]);
  const rs = ROLE_STYLE[userRole] || ROLE_STYLE.cashier;
  const activeStore = stores.find(s => s.id === activeStoreId);
  const breadcrumbs = getBreadcrumbs(pathname);
  const sidebarW = collapsed ? SIDEBAR_COLLAPSED_W : SIDEBAR_W;

  // ── Sidebar items renderer ──────────────────────────────────────────────
  // IMPORTANTE: useMemo debe ir ANTES del early-return de receipt para
  // mantener el mismo orden de hooks entre renders (React #310).
  const navItems = useMemo(() => {
    let lastSection = "";
    return visibleNav.map((item) => {
      const active = isActive(item.href);
      const showSection = !collapsed && item.section && item.section !== lastSection;
      if (item.section) lastSection = item.section;
      const badge = item.icon === "stock" && lowStock > 0 ? lowStock : undefined;

      return (
        <div key={item.href}>
          {showSection && (
            <div style={{ fontSize: 10, fontWeight: 600, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em", padding: "16px 10px 4px" }}>
              {item.section}
            </div>
          )}
          <Link href={item.href} className="sb-link">
            <div
              className={`sb-item${active ? " active" : ""}`}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: collapsed ? "9px 0" : "9px 12px",
                borderRadius: 8,
                background: active ? C.accentBg : "transparent",
                color: active ? C.accent : C.mid,
                fontWeight: active ? 600 : 500, fontSize: 13,
                justifyContent: collapsed ? "center" : "flex-start",
                border: active ? `1px solid ${C.accentBd}` : "1px solid transparent",
                position: "relative",
              }}
            >
              <span style={{ display: "flex", flexShrink: 0 }}><Icon name={item.icon} /></span>
              {!collapsed && <span>{item.label}</span>}
              {collapsed && <span className="sb-tooltip">{item.label}</span>}
              {badge != null && (
                <span style={{
                  marginLeft: collapsed ? 0 : "auto",
                  position: collapsed ? "absolute" : "relative",
                  top: collapsed ? 2 : "auto", right: collapsed ? 2 : "auto",
                  background: C.red, color: "#fff", fontSize: 10, fontWeight: 700,
                  padding: "1px 6px", borderRadius: 99, minWidth: 18, textAlign: "center", lineHeight: "16px",
                }}>
                  {badge > 99 ? "99+" : badge}
                </span>
              )}
            </div>
          </Link>
        </div>
      );
    });
  }, [visibleNav, collapsed, lowStock, isActive]);

  // Early return DESPUÉS de todos los hooks (no antes).
  if (isReceiptPage) return <>{children}</>;

  // ── Sidebar content ──────────────────────────────────────────────────
  // Mario reportó: "no puedo scrolear hacia abajo si no tengo mouse y no
  // puedo llegar a las funciones de abajo".
  //
  // Causa: había DOBLE overflow — el <aside> padre tenía overflowY:auto y
  // el <nav> interno también con flex:1. Eso confunde el comportamiento
  // del scroll en touchpads y algunos browsers (Opera GX, Brave, etc.)
  // porque dos contextos de scroll compiten por el mismo gesture.
  //
  // Fix: scroll SOLO a nivel <aside>. El contenido (brand, user, nav,
  // bottom) fluye natural arriba abajo. Si el sidebar es más alto que
  // viewport, scrollea como una página completa. Si es más bajo, todo
  // visible. Touchpad/wheel/swipe funcionan en cualquier parte.
  const sidebarContent = (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100%", fontFamily: C.font }}>
      {/* Brand */}
      <div style={{ padding: collapsed ? "16px 12px" : "16px 20px", display: "flex", alignItems: "center", gap: 12, borderBottom: `1px solid ${C.border}`, minHeight: TOPBAR_H }}>
        <div style={{ width: 34, height: 34, borderRadius: 10, background: "linear-gradient(135deg, #4F46E5, #7C3AED)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 2px 8px rgba(79,70,229,0.25)" }}>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>
          </svg>
        </div>
        {!collapsed && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 15, fontWeight: 800, color: C.text, lineHeight: 1.1 }}>Pulstock</div>
            <div style={{ fontSize: 10, color: C.mute, fontWeight: 500, marginTop: 1 }}>Sistema de gestión</div>
          </div>
        )}
        {isMobile && (
          <button onClick={() => setDrawerOpen(false)} style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: C.mute, display: "flex", padding: 4 }}>
            <Icon name="close" />
          </button>
        )}
      </div>

      {/* User info */}
      {userName && !collapsed && (
        <div style={{ padding: "10px 20px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 30, height: 30, borderRadius: "50%", background: rs.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, color: rs.fg, flexShrink: 0 }}>
            {userName.charAt(0).toUpperCase()}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{userName}</div>
            <span style={{ display: "inline-block", marginTop: 1, padding: "0px 6px", borderRadius: 99, fontSize: 9, fontWeight: 700, background: rs.bg, color: rs.fg, lineHeight: "16px" }}>{rs.label}</span>
          </div>
        </div>
      )}
      {userName && collapsed && (
        <div style={{ padding: "10px 0", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "center" }}>
          <div style={{ width: 32, height: 32, borderRadius: "50%", background: rs.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: rs.fg }}>
            {userName.charAt(0).toUpperCase()}
          </div>
        </div>
      )}

      {/* Nav. SIN overflow propio — deja que el <aside> padre maneje el
          scroll. flex:1 con marginBottom-auto empuja el bottom al final
          del contenido cuando el sidebar es corto, pero permite que el
          bottom siga en flujo cuando el contenido excede el viewport. */}
      <nav className="mobile-nav" style={{ padding: "8px 8px", display: "flex", flexDirection: "column", gap: 1, flexShrink: 0 }}>
        {navItems}
      </nav>

      {/* Bottom: collapse + logout. marginTop:auto lo empuja al fondo
          cuando hay espacio sobrante; cuando no hay espacio, queda
          al final del flujo natural y se accede con scroll. */}
      <div style={{ padding: "8px 8px 12px", borderTop: `1px solid ${C.border}`, display: "flex", flexDirection: "column", gap: 2, marginTop: "auto", flexShrink: 0 }}>
        {/* Collapse toggle (desktop only) */}
        {!isMobile && (
          <button onClick={toggleCollapsed} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: collapsed ? "9px 0" : "9px 12px",
            borderRadius: 8, border: "none", background: "transparent", color: C.mute,
            fontSize: 12, fontWeight: 500, cursor: "pointer", justifyContent: collapsed ? "center" : "flex-start",
            fontFamily: C.font, width: "100%", transition: "all 0.12s ease",
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
              style={{ transform: collapsed ? "rotate(180deg)" : "none", transition: "transform 0.2s ease", flexShrink: 0 }}>
              <polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/>
            </svg>
            {!collapsed && <span>Colapsar</span>}
          </button>
        )}
        {/* Logout */}
        <button onClick={handleLogout} style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: collapsed ? "9px 0" : "9px 12px",
          borderRadius: 8, border: "none", background: "transparent", color: C.mute,
          fontSize: 12, fontWeight: 500, cursor: "pointer", justifyContent: collapsed ? "center" : "flex-start",
          fontFamily: C.font, width: "100%", transition: "all 0.12s ease",
        }}>
          <span style={{ display: "flex", flexShrink: 0 }}><Icon name="logout" /></span>
          {!collapsed && <span>Cerrar sesión</span>}
        </button>
      </div>
    </div>
  );

  // ── Topbar ─────────────────────────────────────────────────────────────
  const topbar = (
    <header style={{
      height: TOPBAR_H, background: C.surface,
      borderBottom: `1px solid ${C.border}`,
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0 20px", fontFamily: C.font, flexShrink: 0,
    }}>
      {/* Left: Breadcrumbs — minWidth:0 + ellipsis para que en tablet
          horizontal no choque contra los dropdowns de la derecha. */}
      <div style={{
        display: "flex", alignItems: "center", gap: 6,
        minWidth: 0, flex: 1, overflow: "hidden",
        whiteSpace: "nowrap", textOverflow: "ellipsis",
      }}>
        {breadcrumbs.map((crumb, i) => (
          <span key={i} style={{
            display: "flex", alignItems: "center", gap: 6, flexShrink: 0,
          }}>
            {i > 0 && <span style={{ color: C.border, fontSize: 12 }}>/</span>}
            {crumb.href ? (
              <Link href={crumb.href} style={{ fontSize: 13, color: C.mute, textDecoration: "none", fontWeight: 500 }}>
                {crumb.label}
              </Link>
            ) : (
              <span style={{ fontSize: 13, color: C.text, fontWeight: 600 }}>{crumb.label}</span>
            )}
          </span>
        ))}
      </div>

      {/* Right: Store + User */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {/* Store selector */}
        {stores.length > 0 && (
          <div ref={storeRef} style={{ position: "relative" }}>
            <button
              className="topbar-btn"
              onClick={() => { setStoreDropOpen(!storeDropOpen); setUserMenuOpen(false); }}
              style={{
                fontSize: 12, fontWeight: 600,
                background: storeDropOpen ? C.bg : undefined,
                borderColor: storeDropOpen ? C.border : undefined,
              }}
            >
              <Icon name="store" size={16} />
              <span>{activeStore?.name || "Tienda"}</span>
              {stores.length > 1 && <Icon name="chevronDown" />}
            </button>

            {storeDropOpen && stores.length > 1 && (
              <div style={{
                position: "absolute", top: "calc(100% + 6px)", right: 0,
                background: C.surface, border: `1px solid ${C.border}`,
                borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                padding: 6, minWidth: 200, maxWidth: "calc(100vw - 32px)",
                maxHeight: "60vh", overflowY: "auto", zIndex: 300,
              }}>
                {stores.map(store => (
                  <button key={store.id} onClick={() => switchStore(store.id)}
                    style={{
                      display: "flex", alignItems: "center", gap: 10,
                      width: "100%", padding: "8px 12px", borderRadius: 6,
                      border: "none", cursor: "pointer", fontFamily: C.font,
                      fontSize: 13, fontWeight: store.id === activeStoreId ? 600 : 400,
                      color: store.id === activeStoreId ? C.accent : C.text,
                      background: store.id === activeStoreId ? C.accentBg : "transparent",
                      textAlign: "left", transition: "background 0.1s ease",
                    }}>
                    {store.id === activeStoreId && <Icon name="check" />}
                    <span>{store.name}</span>
                    {store.code && <span style={{ fontSize: 11, color: C.mute, marginLeft: "auto" }}>{store.code}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* User menu */}
        <div ref={userRef} style={{ position: "relative" }}>
          <button
            className="topbar-btn"
            onClick={() => { setUserMenuOpen(!userMenuOpen); setStoreDropOpen(false); }}
            style={{ padding: 4 }}
          >
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: rs.bg, border: `1px solid ${rs.fg}22`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, fontWeight: 700, color: rs.fg,
            }}>
              {(userName || "U").charAt(0).toUpperCase()}
            </div>
          </button>

          {userMenuOpen && (
            <div style={{
              position: "absolute", top: "calc(100% + 6px)", right: 0,
              background: C.surface, border: `1px solid ${C.border}`,
              borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
              padding: 6, minWidth: 220, maxWidth: "calc(100vw - 32px)",
              maxHeight: "70vh", overflowY: "auto", zIndex: 300,
            }}>
              <div style={{ padding: "10px 12px 8px", borderBottom: `1px solid ${C.border}`, marginBottom: 4 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{userName}</div>
                {userEmail && <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{userEmail}</div>}
                <span style={{ display: "inline-block", marginTop: 4, padding: "1px 8px", borderRadius: 99, fontSize: 10, fontWeight: 700, background: rs.bg, color: rs.fg }}>{rs.label}</span>
              </div>
              <Link href="/dashboard/settings" style={{ textDecoration: "none" }} onClick={() => setUserMenuOpen(false)}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: 6, fontSize: 13, fontWeight: 500, color: C.mid, cursor: "pointer", transition: "background 0.1s" }}>
                  <Icon name="settings" size={16} /> Configuración
                </div>
              </Link>
              <button onClick={handleLogout} style={{
                display: "flex", alignItems: "center", gap: 10,
                width: "100%", padding: "8px 12px", borderRadius: 6,
                border: "none", cursor: "pointer", fontFamily: C.font,
                fontSize: 13, fontWeight: 500, color: C.red,
                background: "transparent", textAlign: "left",
              }}>
                <Icon name="logout" size={16} /> Cerrar sesión
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );

  // ── MOBILE ─────────────────────────────────────────────────────────────
  if (isMobile) {
    return (
      <div style={{ fontFamily: C.font, minHeight: "100vh", display: "flex", flexDirection: "column", background: C.bg }}>
        <header className="safe-top" style={{
          height: TOPBAR_H, background: C.surface, borderBottom: `1px solid ${C.border}`,
          display: "flex", alignItems: "center", padding: "0 12px", gap: 10,
          position: "sticky", top: 0, zIndex: 50,
        }}>
          <button onClick={() => setDrawerOpen(true)} style={{ background: "none", border: "none", cursor: "pointer", color: C.text, display: "flex", padding: 6 }}>
            <Icon name="menu" />
          </button>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: "linear-gradient(135deg, #4F46E5, #7C3AED)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
          </div>
          <span style={{ fontSize: 15, fontWeight: 700, color: C.text }}>Pulstock</span>
          {/* Mobile store selector */}
          {stores.length > 0 && activeStore && (
            <div style={{ marginLeft: "auto" }}>
              <div ref={storeRef} style={{ position: "relative" }}>
                <button onClick={() => setStoreDropOpen(!storeDropOpen)} style={{
                  display: "flex", alignItems: "center", gap: 4,
                  padding: "4px 8px", borderRadius: 6, border: `1px solid ${C.border}`,
                  background: C.bg, cursor: "pointer", fontFamily: C.font, fontSize: 11,
                  fontWeight: 600, color: C.mid,
                }}>
                  <Icon name="store" size={14} />
                  <span>{activeStore.name}</span>
                </button>
                {storeDropOpen && stores.length > 1 && (
                  <div style={{
                    position: "absolute", top: "calc(100% + 6px)", right: 0,
                    background: C.surface, border: `1px solid ${C.border}`,
                    borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                    padding: 6, minWidth: 180, maxWidth: "calc(100vw - 16px)",
                    maxHeight: "60vh", overflowY: "auto", zIndex: 300,
                  }}>
                    {stores.map(store => (
                      <button key={store.id} onClick={() => switchStore(store.id)} style={{
                        display: "flex", alignItems: "center", gap: 8,
                        width: "100%", padding: "8px 10px", borderRadius: 6,
                        border: "none", cursor: "pointer", fontFamily: C.font,
                        fontSize: 13, fontWeight: store.id === activeStoreId ? 600 : 400,
                        color: store.id === activeStoreId ? C.accent : C.text,
                        background: store.id === activeStoreId ? C.accentBg : "transparent",
                        textAlign: "left",
                      }}>
                        {store.id === activeStoreId && <Icon name="check" />}
                        {store.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </header>
        {drawerOpen && (<>
          <div onClick={() => setDrawerOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 90, animation: "fadeIn 0.15s ease" }} />
          <aside style={{ position: "fixed", top: 0, left: 0, bottom: 0, width: 280, background: C.surface, zIndex: 100, animation: "slideIn 0.2s cubic-bezier(0.22,1,0.36,1)", boxShadow: "4px 0 24px rgba(0,0,0,0.15)", overflowY: "auto" }}>
            {sidebarContent}
          </aside>
        </>)}
        <main style={{
          flex: 1, overflow: "auto",
          // bottom nav = 64px + safe-area-inset-bottom (iOS notch / Android gestures).
          // Antes era fijo 72px → en algunos phones el contenido se solapaba con el nav.
          paddingBottom: "calc(64px + max(12px, env(safe-area-inset-bottom)))",
        }}><ErrorBoundary>{children}</ErrorBoundary></main>
        <nav className="safe-bottom" style={{ position: "fixed", bottom: 0, left: 0, right: 0, height: 64, background: C.surface, borderTop: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-around", zIndex: 50, paddingBottom: "max(4px, env(safe-area-inset-bottom))" }}>
          {visibleBottom.map(item => {
            const active = isActive(item.href);
            return (
              <Link key={item.href} href={item.href} style={{ textDecoration: "none", display: "flex", flexDirection: "column", alignItems: "center", gap: 2, padding: "6px 12px", color: active ? C.accent : C.mute, transition: "color 0.12s ease", position: "relative" }}>
                {active && <div style={{ position: "absolute", top: -1, width: 24, height: 3, borderRadius: 2, background: C.accent }} />}
                <Icon name={item.icon} /><span style={{ fontSize: 10, fontWeight: active ? 700 : 500 }}>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    );
  }

  // ── DESKTOP ────────────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: C.font, background: C.bg }}>
      {/* Sidebar — height:100vh + overflowY:auto. WebkitOverflowScrolling
          mejora el touch scroll en iOS/macOS Safari. overscrollBehavior
          contiene el scroll en este contenedor (no se filtra al body). */}
      <aside style={{
        width: sidebarW, background: C.surface,
        borderRight: `1px solid ${C.border}`, flexShrink: 0,
        position: "sticky", top: 0, height: "100vh", overflowY: "auto",
        transition: "width 0.2s cubic-bezier(0.4,0,0.2,1)",
        overflowX: "hidden",
        WebkitOverflowScrolling: "touch",
        overscrollBehavior: "contain",
      }}>
        {sidebarContent}
      </aside>

      {/* Main area */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", height: "100vh" }}>
        {/* Topbar */}
        {topbar}

        {/* Content */}
        <main style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
