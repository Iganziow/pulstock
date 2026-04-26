"use client";
import { useEffect, useState, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getAccessToken, isSuperAdmin, clearTokens, apiFetch } from "@/lib/api";

const C = {
  bg: "#0F172A", sidebar: "#1E293B", card: "#1E293B", border: "#334155",
  text: "#F1F5F9", mute: "#94A3B8", accent: "#6366F1", accentHover: "#818CF8",
  green: "#22C55E", red: "#EF4444", yellow: "#F59E0B", white: "#FFFFFF",
};

const NAV = [
  { href: "/superadmin", label: "Dashboard", icon: "📊" },
  { href: "/superadmin/tenants", label: "Tenants", icon: "🏢" },
  { href: "/superadmin/users", label: "Usuarios", icon: "👤" },
  { href: "/superadmin/billing", label: "Facturación", icon: "💰" },
  { href: "/superadmin/forecast", label: "Forecast IA", icon: "🤖" },
];

export default function SuperadminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ok, setOk] = useState(false);

  const isLoginPage = pathname === "/superadmin/login";

  useEffect(() => {
    // Login page no requiere auth
    if (isLoginPage) { setOk(true); return; }

    if (!getAccessToken() || !isSuperAdmin()) {
      router.replace("/superadmin/login");
      return;
    }
    setOk(true);
  }, [isLoginPage]);

  if (!ok) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: C.bg, color: C.mute }}>
      Verificando acceso...
    </div>
  );

  // Login page: render sin sidebar
  if (isLoginPage) return <>{children}</>;

  const isActive = (href: string) => {
    if (href === "/superadmin") return pathname === "/superadmin";
    return pathname.startsWith(href);
  };

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: C.bg, color: C.text, fontFamily: "'Inter', sans-serif" }}>
      {/* Sidebar */}
      <aside style={{ width: 220, background: C.sidebar, borderRight: `1px solid ${C.border}`, padding: "20px 0", display: "flex", flexDirection: "column", position: "fixed", top: 0, left: 0, bottom: 0, zIndex: 10 }}>
        <div style={{ padding: "0 16px 20px", borderBottom: `1px solid ${C.border}` }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: C.accent }}>Pulstock</div>
          <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>Panel de Administración</div>
        </div>

        <nav style={{ flex: 1, padding: "12px 8px" }}>
          {NAV.map((n) => (
            <a
              key={n.href}
              href={n.href}
              onClick={(e) => { e.preventDefault(); router.push(n.href); }}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "10px 12px", borderRadius: 8, marginBottom: 2,
                fontSize: 13, fontWeight: isActive(n.href) ? 700 : 500,
                color: isActive(n.href) ? C.white : C.mute,
                background: isActive(n.href) ? C.accent + "22" : "transparent",
                textDecoration: "none", transition: "all .15s",
              }}
            >
              <span style={{ fontSize: 16 }}>{n.icon}</span>
              {n.label}
            </a>
          ))}
        </nav>

        <div style={{ padding: "12px 16px", borderTop: `1px solid ${C.border}` }}>
          <button
            onClick={() => { clearTokens(); router.replace("/superadmin/login"); }}
            style={{
              width: "100%", padding: "8px 0", borderRadius: 6,
              background: "transparent", color: C.red, border: `1px solid ${C.red}33`,
              fontSize: 12, fontWeight: 600, cursor: "pointer",
            }}
          >
            Cerrar sesión
          </button>
        </div>
      </aside>

      {/* Content */}
      <main style={{ flex: 1, marginLeft: 220, padding: "0", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
        <GlobalSearch />
        <div style={{ padding: "24px 32px", flex: 1 }}>
          {children}
        </div>
      </main>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// GLOBAL SEARCH — caja en el topbar para buscar tenants/users
// ─────────────────────────────────────────────────────────────
function GlobalSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{ tenants: any[]; users: any[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<any>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Cerrar al click afuera
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Debounce de la búsqueda
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (q.trim().length < 2) { setResults(null); return; }
    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const r = await apiFetch(`/superadmin/search/?q=${encodeURIComponent(q.trim())}`);
        setResults(r);
        setOpen(true);
      } catch { setResults(null); }
      finally { setLoading(false); }
    }, 250);
    return () => clearTimeout(debounceRef.current);
  }, [q]);

  const C2 = {
    bg: "#0F172A", card: "#1E293B", border: "#334155",
    text: "#F1F5F9", mute: "#94A3B8", accent: "#6366F1",
  };

  return (
    <div ref={wrapperRef} style={{
      borderBottom: `1px solid ${C2.border}`, padding: "12px 32px",
      background: C2.card, position: "relative",
    }}>
      <input
        type="text"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => results && setOpen(true)}
        placeholder="🔍 Buscar tenant o usuario por nombre, email, RUT..."
        style={{
          width: "100%", maxWidth: 600, boxSizing: "border-box",
          padding: "10px 14px", borderRadius: 8,
          background: C2.bg, border: `1px solid ${C2.border}`,
          color: C2.text, fontSize: 13, outline: "none",
        }}
      />

      {open && results && (
        <div style={{
          position: "absolute", top: "calc(100% - 1px)", left: 32, width: 600, maxWidth: "calc(100% - 64px)",
          background: C2.card, border: `1px solid ${C2.border}`, borderTop: "none",
          borderRadius: "0 0 8px 8px", maxHeight: 480, overflowY: "auto", zIndex: 50,
          boxShadow: "0 8px 32px rgba(0,0,0,.4)",
        }}>
          {loading && <div style={{ padding: 14, color: C2.mute, fontSize: 12 }}>Buscando...</div>}

          {!loading && results.tenants.length === 0 && results.users.length === 0 && (
            <div style={{ padding: 14, color: C2.mute, fontSize: 12 }}>
              Sin resultados para "{results.tenants.length === 0 && results.users.length === 0 ? q : ""}"
            </div>
          )}

          {results.tenants.length > 0 && (
            <div>
              <div style={{ padding: "8px 14px", fontSize: 10, fontWeight: 700, color: C2.mute, textTransform: "uppercase", borderBottom: `1px solid ${C2.border}` }}>
                Tenants ({results.tenants.length})
              </div>
              {results.tenants.map((t: any) => (
                <button
                  key={`t-${t.id}`}
                  onClick={() => { router.push(`/superadmin/tenants/${t.id}`); setOpen(false); setQ(""); }}
                  style={{
                    display: "block", width: "100%", textAlign: "left",
                    padding: "10px 14px", background: "none", border: "none",
                    color: C2.text, cursor: "pointer", borderBottom: `1px solid ${C2.border}33`,
                    fontFamily: "inherit",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = C2.bg}
                  onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                >
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    🏢 {t.name}
                    {!t.is_active && <span style={{ color: "#EF4444", fontSize: 10, marginLeft: 8 }}>INACTIVO</span>}
                  </div>
                  <div style={{ fontSize: 11, color: C2.mute, marginTop: 2 }}>
                    {[t.slug, t.rut, t.email].filter(Boolean).join(" · ")}
                  </div>
                </button>
              ))}
            </div>
          )}

          {results.users.length > 0 && (
            <div>
              <div style={{ padding: "8px 14px", fontSize: 10, fontWeight: 700, color: C2.mute, textTransform: "uppercase", borderBottom: `1px solid ${C2.border}` }}>
                Usuarios ({results.users.length})
              </div>
              {results.users.map((u: any) => (
                <button
                  key={`u-${u.id}`}
                  onClick={() => { if (u.tenant) { router.push(`/superadmin/tenants/${u.tenant.id}`); setOpen(false); setQ(""); } }}
                  disabled={!u.tenant}
                  style={{
                    display: "block", width: "100%", textAlign: "left",
                    padding: "10px 14px", background: "none", border: "none",
                    color: C2.text, cursor: u.tenant ? "pointer" : "default",
                    borderBottom: `1px solid ${C2.border}33`, fontFamily: "inherit",
                    opacity: u.tenant ? 1 : 0.6,
                  }}
                  onMouseEnter={(e) => { if (u.tenant) e.currentTarget.style.background = C2.bg; }}
                  onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                >
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    👤 {u.full_name || u.email}
                    {!u.is_active && <span style={{ color: "#EF4444", fontSize: 10, marginLeft: 8 }}>INACTIVO</span>}
                  </div>
                  <div style={{ fontSize: 11, color: C2.mute, marginTop: 2 }}>
                    {u.email} · {u.role}
                    {u.tenant && <> · 🏢 {u.tenant.name}</>}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
