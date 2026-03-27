"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getAccessToken, isSuperAdmin, clearTokens } from "@/lib/api";

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
      <main style={{ flex: 1, marginLeft: 220, padding: "24px 32px", minHeight: "100vh" }}>
        {children}
      </main>
    </div>
  );
}
