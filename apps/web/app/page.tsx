"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef, useCallback } from "react";
import { getAccessToken } from "@/lib/api";

const C = {
  accent: "#4F46E5", accentDark: "#4338CA", violet: "#7C3AED",
  bg: "#FAFAFA", white: "#FFFFFF", text: "#18181B", mid: "#52525B",
  mute: "#71717A", light: "#A1A1AA", border: "#E4E4E7",
  green: "#16A34A", greenBg: "#ECFDF5", red: "#DC2626",
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const fCLP = (n: number) => "$" + n.toLocaleString("es-CL");

/* ═══════════════════════════════════════════════════════════════
   DATA
   ═══════════════════════════════════════════════════════════════ */

const PROBLEMS = [
  { icon: "📋", before: "Planillas de Excel", problem: "Errores manuales, datos desactualizados, stock fantasma y horas perdidas cuadrando inventario." },
  { icon: "🔍", before: "Sin visibilidad", problem: "No sabes qué productos se venden más, cuáles tienen margen bajo o cuándo vas a quedarte sin stock." },
  { icon: "🏪", before: "Múltiples locales", problem: "Cada sucursal maneja su propio control y no hay una vista centralizada del negocio." },
  { icon: "💸", before: "Pérdidas ocultas", problem: "Mermas, robos y sobre-stock que no se detectan a tiempo impactan directamente tu rentabilidad." },
];

const STEPS = [
  { num: "01", title: "Registra tus productos", desc: "Carga tu catálogo con categorías, precios, códigos de barra y unidades de medida. Importa desde Excel si ya tienes datos.", icon: "📦" },
  { num: "02", title: "Vende desde el POS", desc: "Punto de venta rápido con búsqueda inteligente, múltiples medios de pago y generación automática de boletas.", icon: "🛒" },
  { num: "03", title: "Controla tu inventario", desc: "El stock se actualiza automáticamente con cada venta y compra. Recibe alertas cuando un producto está bajo.", icon: "📊" },
  { num: "04", title: "Toma mejores decisiones", desc: "Reportes de ventas, márgenes, rotación y predicción de demanda con IA te dicen exactamente qué comprar y cuándo.", icon: "🤖" },
];

const BENEFITS = [
  { icon: "⚡", title: "Ahorra tiempo", desc: "Automatiza el control de inventario, ventas y compras. Lo que antes tomaba horas, ahora toma segundos." },
  { icon: "📉", title: "Reduce pérdidas", desc: "Detecta mermas, sobre-stock y productos sin rotación antes de que afecten tu rentabilidad." },
  { icon: "🎯", title: "Predicción con IA", desc: "Nuestro motor de forecasting analiza tu historial de ventas y te dice qué comprar y cuánto." },
  { icon: "🏪", title: "Multi-local", desc: "Gestiona todos tus locales y bodegas desde un solo lugar. Transferencias entre sucursales." },
  { icon: "💰", title: "Margen real", desc: "Costo promedio ponderado automático. Conoce el margen real de cada producto y cada venta." },
  { icon: "📱", title: "Desde cualquier lugar", desc: "100% en la nube. Accede desde computador, tablet o celular. Sin instalaciones." },
];

const PLANS = [
  { key: "inicio", name: "Inicio", price: 19000, popular: false, features: ["Hasta 120 productos", "1 local", "Hasta 10 usuarios", "POS completo", "Reportes básicos", "Soporte por email"] },
  { key: "crecimiento", name: "Crecimiento", price: 25990, popular: true, features: ["Hasta 400 productos", "2 locales", "Hasta 15 usuarios", "Forecast con IA", "Análisis ABC", "11 reportes avanzados", "Soporte prioritario"] },
  { key: "pro", name: "Pro", price: 59990, popular: false, features: ["Hasta 1000 productos", "5 locales", "Usuarios ilimitados", "Forecast con IA", "Análisis ABC", "Transferencias entre locales", "Soporte dedicado"] },
];

/* ═══════════════════════════════════════════════════════════════
   HOOKS
   ═══════════════════════════════════════════════════════════════ */

function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setVisible(true); obs.disconnect(); } }, { threshold: 0.15 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return { ref, visible };
}

function useCounter(target: number, duration = 1500) {
  const [val, setVal] = useState(0);
  const [started, setStarted] = useState(false);
  const start = useCallback(() => setStarted(true), []);

  useEffect(() => {
    if (!started) return;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setVal(Math.round(target * eased));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [started, target, duration]);

  return { val, start };
}

/* ═══════════════════════════════════════════════════════════════
   COMPONENTS
   ═══════════════════════════════════════════════════════════════ */

function SectionTitle({ tag, title, subtitle }: { tag: string; title: string; subtitle?: string }) {
  return (
    <div style={{ textAlign: "center", marginBottom: 56 }}>
      <p style={{ fontSize: 13, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 8 }}>{tag}</p>
      <h2 style={{ fontSize: "clamp(26px, 4vw, 40px)", fontWeight: 900, margin: 0, lineHeight: 1.2 }}>{title}</h2>
      {subtitle && <p style={{ fontSize: 16, color: C.mid, marginTop: 12, maxWidth: 560, margin: "12px auto 0" }}>{subtitle}</p>}
    </div>
  );
}

function RevealSection({ children, style, delay = 0 }: { children: React.ReactNode; style?: React.CSSProperties; delay?: number }) {
  const { ref, visible } = useScrollReveal();
  return (
    <div ref={ref} style={{
      ...style,
      opacity: visible ? 1 : 0,
      transform: visible ? "none" : "translateY(32px)",
      transition: `opacity .7s cubic-bezier(.16,1,.3,1) ${delay}ms, transform .7s cubic-bezier(.16,1,.3,1) ${delay}ms`,
    }}>
      {children}
    </div>
  );
}

function DashboardMockup() {
  return (
    <div style={{
      maxWidth: 900, margin: "0 auto", perspective: "1200px",
    }}>
      <div style={{
        background: C.white, borderRadius: 16, overflow: "hidden",
        boxShadow: "0 40px 80px rgba(0,0,0,.12), 0 0 0 1px rgba(0,0,0,.05)",
        transform: "rotateX(4deg) rotateY(-2deg)",
        transition: "transform .4s ease",
      }}>
        {/* Title bar */}
        <div style={{ background: "#F4F4F5", padding: "10px 16px", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid #E4E4E7" }}>
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#EF4444" }} />
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#F59E0B" }} />
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#22C55E" }} />
          <div style={{ flex: 1, textAlign: "center", fontSize: 11, color: C.mute }}>pulstock.cl/dashboard</div>
        </div>
        {/* Mock dashboard */}
        <div style={{ display: "flex", minHeight: 320 }}>
          {/* Sidebar */}
          <div style={{ width: 180, background: "#18181B", padding: "16px 12px", flexShrink: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 800, color: C.accent, marginBottom: 16 }}>Pulstock</div>
            {["Dashboard", "Catálogo", "Ventas", "Inventario", "Reportes", "Forecast IA"].map((item, i) => (
              <div key={item} style={{
                padding: "8px 10px", borderRadius: 6, marginBottom: 2, fontSize: 12,
                background: i === 0 ? C.accent + "22" : "transparent",
                color: i === 0 ? C.white : "#A1A1AA", fontWeight: i === 0 ? 700 : 400,
              }}>{item}</div>
            ))}
          </div>
          {/* Content */}
          <div style={{ flex: 1, padding: 20 }}>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 16 }}>Dashboard</div>
            {/* KPI cards */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10, marginBottom: 16 }}>
              {[
                { label: "Ventas hoy", value: "$847.500", color: C.accent },
                { label: "Productos", value: "342", color: C.green },
                { label: "Stock bajo", value: "12", color: "#F59E0B" },
                { label: "Margen", value: "34.2%", color: C.violet },
              ].map((kpi) => (
                <div key={kpi.label} style={{ background: "#F9FAFB", borderRadius: 10, padding: "10px 12px", border: "1px solid #F3F4F6" }}>
                  <div style={{ fontSize: 9, color: C.mute, textTransform: "uppercase" }}>{kpi.label}</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color: kpi.color, marginTop: 2 }}>{kpi.value}</div>
                </div>
              ))}
            </div>
            {/* Mini chart */}
            <div style={{ background: "#F9FAFB", borderRadius: 10, padding: 14, border: "1px solid #F3F4F6" }}>
              <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 8 }}>Ventas últimos 7 días</div>
              <svg viewBox="0 0 300 60" style={{ width: "100%", height: 60 }}>
                <defs>
                  <linearGradient id="mockGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={C.accent} stopOpacity="0.2" />
                    <stop offset="100%" stopColor={C.accent} stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path d="M 0 45 Q 30 35, 50 38 T 100 28 T 150 32 T 200 18 T 250 22 T 300 10" fill="none" stroke={C.accent} strokeWidth="2.5" strokeLinecap="round" />
                <path d="M 0 45 Q 30 35, 50 38 T 100 28 T 150 32 T 200 18 T 250 22 T 300 10 V 60 H 0 Z" fill="url(#mockGrad)" />
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCounter({ target, suffix, label }: { target: number; suffix: string; label: string }) {
  const { val, start } = useCounter(target);
  const { ref, visible } = useScrollReveal();

  useEffect(() => { if (visible) start(); }, [visible, start]);

  return (
    <div ref={ref} style={{ textAlign: "center" }}>
      <div style={{ fontSize: 44, fontWeight: 900, color: "#fff" }}>{visible ? val : 0}{suffix}</div>
      <div style={{ fontSize: 13, color: "rgba(255,255,255,.7)", marginTop: 4 }}>{label}</div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════
   PAGE
   ═══════════════════════════════════════════════════════════════ */

export default function LandingPage() {
  const router = useRouter();
  const [scrolled, setScrolled] = useState(false);
  const [formData, setFormData] = useState({ name: "", email: "", phone: "", business: "", message: "" });
  const [formStatus, setFormStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [activeStep, setActiveStep] = useState(0);
  const [mobileMenu, setMobileMenu] = useState(false);

  useEffect(() => {
    if (getAccessToken()) { router.replace("/dashboard"); return; }
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Auto-rotate steps
  useEffect(() => {
    const iv = setInterval(() => setActiveStep((s) => (s + 1) % STEPS.length), 4000);
    return () => clearInterval(iv);
  }, []);

  const go = (path: string) => router.push(path);

  const handleContact = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormStatus("sending");
    try {
      await new Promise((r) => setTimeout(r, 1200));
      setFormStatus("sent");
      setFormData({ name: "", email: "", phone: "", business: "", message: "" });
    } catch {
      setFormStatus("error");
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "14px 16px", borderRadius: 10,
    border: `1.5px solid ${C.border}`, fontSize: 14, color: C.text,
    outline: "none", fontFamily: "inherit", background: C.white,
    transition: "border-color .2s, box-shadow .2s",
  };

  return (
    <div style={{ fontFamily: "'DM Sans','Helvetica Neue',system-ui,sans-serif", color: C.text, background: C.bg }}>
      <style>{`
        @keyframes fadeUp { from { opacity: 0; transform: translateY(24px) } to { opacity: 1; transform: none } }
        @keyframes float { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-12px) } }
        @keyframes pulse { 0%,100% { opacity: .6 } 50% { opacity: 1 } }
        @keyframes slideIn { from { opacity: 0; transform: translateX(-16px) } to { opacity: 1; transform: none } }
        .l-btn { transition: all .2s cubic-bezier(.4,0,.2,1); }
        .l-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(79,70,229,.25); }
        .l-card { transition: all .25s cubic-bezier(.4,0,.2,1); }
        .l-card:hover { transform: translateY(-6px); box-shadow: 0 16px 48px rgba(0,0,0,.1); }
        .l-input:focus { border-color: ${C.accent} !important; box-shadow: 0 0 0 3px rgba(79,70,229,.1); }
        .l-step { transition: all .3s ease; cursor: pointer; }
        .l-step:hover { background: #EEF2FF !important; }
        html { scroll-behavior: smooth; }
        @media (max-width: 768px) {
          .desk-nav { display: none !important; }
          .mob-toggle { display: flex !important; }
        }
        @media (min-width: 769px) {
          .mob-toggle { display: none !important; }
          .mob-menu { display: none !important; }
        }
      `}</style>

      {/* ═══ NAVBAR ═══ */}
      <nav style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 50,
        background: scrolled ? "rgba(255,255,255,.95)" : "transparent",
        backdropFilter: scrolled ? "blur(16px)" : "none",
        borderBottom: scrolled ? `1px solid ${C.border}` : "none",
        transition: "all .3s",
      }}>
        <div style={{ maxWidth: 1140, margin: "0 auto", padding: "0 24px", display: "flex", alignItems: "center", justifyContent: "space-between", height: 64 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 16, fontWeight: 900, color: "#fff",
            }}>P</div>
            <span style={{ fontSize: 18, fontWeight: 800 }}>Pulstock</span>
          </div>
          {/* Desktop nav */}
          <div className="desk-nav" style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {[["#problema","Problema"],["#como-funciona","Cómo funciona"],["#beneficios","Beneficios"],["#precios","Precios"],["#contacto","Contacto"]].map(([href,label]) => (
              <a key={href} href={href} style={{ padding: "8px 12px", fontSize: 13, color: C.mid, textDecoration: "none", fontWeight: 500, borderRadius: 6, transition: "color .2s" }}>{label}</a>
            ))}
            <button onClick={() => go("/login")} style={{ padding: "8px 16px", fontSize: 13, fontWeight: 600, background: "transparent", color: C.accent, border: `1px solid ${C.border}`, borderRadius: 8, cursor: "pointer", marginLeft: 4 }}>Ingresar</button>
            <button onClick={() => go("/#precios")} className="l-btn" style={{ padding: "8px 16px", fontSize: 13, fontWeight: 700, background: C.accent, color: "#fff", border: "none", borderRadius: 8, cursor: "pointer" }}>Ver planes</button>
          </div>
          {/* Mobile toggle */}
          <button className="mob-toggle" onClick={() => setMobileMenu(!mobileMenu)} style={{ display: "none", background: "none", border: "none", fontSize: 22, cursor: "pointer", padding: 4, color: C.text }}>
            {mobileMenu ? "\u2715" : "\u2630"}
          </button>
        </div>
        {/* Mobile menu */}
        {mobileMenu && (
          <div className="mob-menu" style={{ background: C.white, borderTop: `1px solid ${C.border}`, padding: "12px 24px" }}>
            {[["#problema","Problema"],["#como-funciona","Cómo funciona"],["#beneficios","Beneficios"],["#precios","Precios"],["#contacto","Contacto"]].map(([href,label]) => (
              <a key={href} href={href} onClick={() => setMobileMenu(false)} style={{ display: "block", padding: "10px 0", fontSize: 14, color: C.mid, textDecoration: "none" }}>{label}</a>
            ))}
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button onClick={() => go("/login")} style={{ flex: 1, padding: "10px 0", fontSize: 13, fontWeight: 600, background: "transparent", color: C.accent, border: `1px solid ${C.border}`, borderRadius: 8, cursor: "pointer" }}>Ingresar</button>
              <button onClick={() => go("/#precios")} style={{ flex: 1, padding: "10px 0", fontSize: 13, fontWeight: 700, background: C.accent, color: "#fff", border: "none", borderRadius: 8, cursor: "pointer" }}>Ver planes</button>
            </div>
          </div>
        )}
      </nav>

      {/* ═══ HERO ═══ */}
      <section style={{
        minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        background: `linear-gradient(135deg, #FAFAFA 0%, #EEF2FF 40%, #F5F3FF 70%, #FAFAFA 100%)`,
        position: "relative", overflow: "hidden", paddingTop: 80,
      }}>
        {/* Grid background */}
        <div style={{
          position: "absolute", inset: 0,
          backgroundImage: `linear-gradient(${C.accent}06 1px, transparent 1px), linear-gradient(90deg, ${C.accent}06 1px, transparent 1px)`,
          backgroundSize: "60px 60px",
        }} />
        {/* Floating orbs */}
        <div style={{ position: "absolute", top: "15%", left: "10%", width: 300, height: 300, borderRadius: "50%", background: `radial-gradient(circle, ${C.accent}0A, transparent)`, animation: "float 6s ease-in-out infinite" }} />
        <div style={{ position: "absolute", bottom: "20%", right: "8%", width: 200, height: 200, borderRadius: "50%", background: `radial-gradient(circle, ${C.violet}0A, transparent)`, animation: "float 8s ease-in-out infinite 1s" }} />

        <div style={{ textAlign: "center", maxWidth: 720, padding: "0 24px", position: "relative", zIndex: 1, animation: "fadeUp .6s cubic-bezier(.16,1,.3,1)" }}>
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "6px 16px", borderRadius: 20, fontSize: 12, fontWeight: 600,
            background: C.greenBg, color: C.green, marginBottom: 20,
            border: "1px solid #A7F3D0", animation: "pulse 2s ease-in-out infinite",
          }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: C.green }} />
            Gestión de inventario inteligente para PYMES
          </div>
          <h1 style={{ fontSize: "clamp(34px, 5.5vw, 60px)", fontWeight: 900, lineHeight: 1.08, margin: "0 0 20px", letterSpacing: "-.025em" }}>
            El sistema de inventario
            <br />
            <span style={{ background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              que tu negocio necesita
            </span>
          </h1>
          <p style={{ fontSize: "clamp(16px, 2vw, 19px)", color: C.mid, lineHeight: 1.6, maxWidth: 560, margin: "0 auto 36px" }}>
            Controla inventario, ventas y compras desde un solo lugar.
            Con predicción de demanda con inteligencia artificial y reportes en tiempo real.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <button onClick={() => go("/#precios")} className="l-btn" style={{
              padding: "16px 36px", fontSize: 16, fontWeight: 800,
              background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`,
              color: "#fff", border: "none", borderRadius: 12, cursor: "pointer",
              boxShadow: `0 4px 14px ${C.accent}40`,
            }}>Ver planes</button>
            <a href="#contacto" className="l-btn" style={{
              padding: "16px 36px", fontSize: 16, fontWeight: 600,
              background: C.white, color: C.text, border: `1px solid ${C.border}`,
              borderRadius: 12, cursor: "pointer", textDecoration: "none",
              display: "inline-flex", alignItems: "center",
            }}>Contactar ventas</a>
          </div>
        </div>

        {/* Dashboard mockup */}
        <div style={{ maxWidth: 1000, width: "100%", padding: "60px 24px 0", position: "relative", zIndex: 1, animation: "fadeUp .8s cubic-bezier(.16,1,.3,1) .2s both" }}>
          <DashboardMockup />
        </div>
      </section>

      {/* ═══ TRUSTED BY (logos strip) ═══ */}
      <section style={{ padding: "40px 24px", borderBottom: `1px solid ${C.border}`, background: C.white }}>
        <div style={{ maxWidth: 800, margin: "0 auto", textAlign: "center" }}>
          <p style={{ fontSize: 12, fontWeight: 600, color: C.light, textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 16 }}>
            Diseñado para PYMES de Chile
          </p>
          <div style={{ display: "flex", justifyContent: "center", gap: 40, alignItems: "center", flexWrap: "wrap", opacity: .4 }}>
            {["Minimarkets", "Ferreterías", "Tiendas de ropa", "Bodegas", "Distribuidoras"].map((t) => (
              <span key={t} style={{ fontSize: 14, fontWeight: 700, color: C.text }}>{t}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 1. PROBLEMA QUE RESUELVE ═══ */}
      <section id="problema" style={{ padding: "100px 24px", maxWidth: 1140, margin: "0 auto" }}>
        <RevealSection>
          <SectionTitle
            tag="El problema"
            title="¿Tu negocio todavía controla el inventario con Excel?"
            subtitle="Estos son los problemas más comunes que enfrentan los negocios sin un sistema profesional de gestión."
          />
        </RevealSection>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20 }}>
          {PROBLEMS.map((p, i) => (
            <RevealSection key={i} delay={i * 80}>
              <div className="l-card" style={{
                background: C.white, borderRadius: 16, padding: 28, height: "100%",
                border: `1px solid ${C.border}`, boxShadow: "0 1px 3px rgba(0,0,0,.04)",
              }}>
                <div style={{
                  width: 52, height: 52, borderRadius: 14,
                  background: "#FEF2F2", display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 24, marginBottom: 16,
                }}>{p.icon}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: C.red, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 6 }}>
                  {p.before}
                </div>
                <p style={{ fontSize: 14, color: C.mid, lineHeight: 1.7, margin: 0 }}>{p.problem}</p>
              </div>
            </RevealSection>
          ))}
        </div>
        <RevealSection delay={350}>
          <div style={{
            marginTop: 40, padding: "24px 32px", borderRadius: 16,
            background: `linear-gradient(135deg, ${C.accent}08, ${C.violet}08)`,
            border: `1px solid ${C.accent}20`, textAlign: "center",
          }}>
            <p style={{ fontSize: 18, fontWeight: 700, margin: "0 0 4px" }}>Pulstock resuelve todos estos problemas</p>
            <p style={{ fontSize: 14, color: C.mid, margin: 0 }}>Un sistema completo que reemplaza las planillas, centraliza la información y te da visibilidad total de tu negocio.</p>
          </div>
        </RevealSection>
      </section>

      {/* ═══ 2. CÓMO FUNCIONA (interactive) ═══ */}
      <section id="como-funciona" style={{ padding: "100px 24px", background: C.white }}>
        <div style={{ maxWidth: 960, margin: "0 auto" }}>
          <RevealSection>
            <SectionTitle
              tag="Cómo funciona"
              title="En 4 pasos simples"
              subtitle="Configura tu negocio en minutos y empieza a tener el control total de tu operación."
            />
          </RevealSection>
          <RevealSection>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 40, alignItems: "start" }}>
              {/* Steps list */}
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {STEPS.map((s, i) => (
                  <div key={i}
                    className="l-step"
                    onClick={() => setActiveStep(i)}
                    style={{
                      display: "flex", gap: 16, alignItems: "center",
                      padding: "16px 18px", borderRadius: 14,
                      background: activeStep === i ? "#EEF2FF" : "transparent",
                      borderLeft: `3px solid ${activeStep === i ? C.accent : "transparent"}`,
                    }}
                  >
                    <div style={{
                      width: 44, height: 44, borderRadius: 12, flexShrink: 0,
                      background: activeStep === i ? `linear-gradient(135deg, ${C.accent}, ${C.violet})` : "#F3F4F6",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 20, color: activeStep === i ? "#fff" : C.mute,
                      transition: "all .3s",
                    }}>{s.icon}</div>
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: C.accent, marginBottom: 2 }}>PASO {s.num}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: activeStep === i ? C.text : C.mid }}>{s.title}</div>
                    </div>
                  </div>
                ))}
              </div>
              {/* Active step detail */}
              <div style={{
                background: "#F9FAFB", borderRadius: 20, padding: 36,
                border: `1px solid ${C.border}`,
                animation: "slideIn .35s ease",
              }} key={activeStep}>
                <div style={{
                  width: 72, height: 72, borderRadius: 18, marginBottom: 20,
                  background: `linear-gradient(135deg, ${C.accent}14, ${C.violet}14)`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 36,
                }}>{STEPS[activeStep].icon}</div>
                <div style={{ fontSize: 11, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 6 }}>
                  Paso {STEPS[activeStep].num}
                </div>
                <h3 style={{ fontSize: 24, fontWeight: 900, margin: "0 0 12px" }}>{STEPS[activeStep].title}</h3>
                <p style={{ fontSize: 15, color: C.mid, lineHeight: 1.8, margin: 0 }}>{STEPS[activeStep].desc}</p>
                {/* Progress dots */}
                <div style={{ display: "flex", gap: 6, marginTop: 24 }}>
                  {STEPS.map((_, i) => (
                    <button key={i} onClick={() => setActiveStep(i)} style={{
                      width: activeStep === i ? 24 : 8, height: 8, borderRadius: 4,
                      background: activeStep === i ? C.accent : "#D4D4D8",
                      border: "none", cursor: "pointer", transition: "all .3s",
                    }} />
                  ))}
                </div>
              </div>
            </div>
          </RevealSection>
        </div>
      </section>

      {/* ═══ 3. BENEFICIOS PRINCIPALES ═══ */}
      <section id="beneficios" style={{ padding: "100px 24px", maxWidth: 1140, margin: "0 auto" }}>
        <RevealSection>
          <SectionTitle
            tag="Beneficios"
            title="¿Por qué elegir Pulstock?"
            subtitle="Herramientas profesionales diseñadas para PYMES chilenas que quieren crecer."
          />
        </RevealSection>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 20 }}>
          {BENEFITS.map((b, i) => (
            <RevealSection key={i} delay={i * 80}>
              <div className="l-card" style={{
                background: C.white, borderRadius: 16, padding: 28, height: "100%",
                border: `1px solid ${C.border}`, boxShadow: "0 1px 3px rgba(0,0,0,.04)",
                position: "relative", overflow: "hidden",
              }}>
                <div style={{
                  position: "absolute", top: -20, right: -20, width: 80, height: 80, borderRadius: "50%",
                  background: `${C.accent}06`,
                }} />
                <div style={{
                  width: 52, height: 52, borderRadius: 14,
                  background: "#EEF2FF", display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 24, marginBottom: 16, position: "relative",
                }}>{b.icon}</div>
                <h3 style={{ fontSize: 17, fontWeight: 800, margin: "0 0 8px" }}>{b.title}</h3>
                <p style={{ fontSize: 14, color: C.mid, lineHeight: 1.7, margin: 0 }}>{b.desc}</p>
              </div>
            </RevealSection>
          ))}
        </div>
      </section>

      {/* ═══ STATS BAR (animated counters) ═══ */}
      <section style={{ background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`, padding: "64px 24px", position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, backgroundImage: `radial-gradient(circle at 20% 50%, rgba(255,255,255,.08) 0%, transparent 50%), radial-gradient(circle at 80% 50%, rgba(255,255,255,.05) 0%, transparent 50%)` }} />
        <div style={{ maxWidth: 900, margin: "0 auto", display: "flex", justifyContent: "space-around", flexWrap: "wrap", gap: 30, position: "relative" }}>
          <StatCounter target={99} suffix=".9%" label="Disponibilidad" />
          <StatCounter target={200} suffix="ms" label="Tiempo de respuesta" />
          <StatCounter target={11} suffix="+" label="Reportes avanzados" />
          <StatCounter target={24} suffix="/7" label="Acceso continuo" />
        </div>
      </section>

      {/* ═══ 4. PLANES DE PRECIOS ═══ */}
      <section id="precios" style={{ padding: "100px 24px", background: C.white }}>
        <div style={{ maxWidth: 1000, margin: "0 auto" }}>
          <RevealSection>
            <SectionTitle
              tag="Precios"
              title="Planes simples y transparentes"
              subtitle="Elige tu plan, paga y accede inmediatamente."
            />
          </RevealSection>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 20 }}>
            {PLANS.map((p, i) => (
              <RevealSection key={i} delay={i * 100}>
                <div className="l-card" style={{
                  background: C.white, borderRadius: 20, padding: 32,
                  border: p.popular ? `2px solid ${C.accent}` : `1px solid ${C.border}`,
                  boxShadow: p.popular ? `0 12px 40px ${C.accent}18` : "0 1px 3px rgba(0,0,0,.04)",
                  position: "relative", height: "100%",
                  transform: p.popular ? "scale(1.03)" : "none",
                }}>
                  {p.popular && (
                    <div style={{
                      position: "absolute", top: -13, left: "50%", transform: "translateX(-50%)",
                      padding: "5px 20px", borderRadius: 20, fontSize: 11, fontWeight: 800,
                      background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`,
                      color: "#fff", textTransform: "uppercase", letterSpacing: ".06em",
                    }}>Más popular</div>
                  )}
                  <h3 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 4px" }}>Plan {p.name}</h3>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 4, margin: "12px 0 24px" }}>
                    <span style={{ fontSize: 42, fontWeight: 900, letterSpacing: "-.02em" }}>{fCLP(p.price)}</span>
                    <span style={{ fontSize: 14, color: C.mute }}>/mes</span>
                  </div>
                  <ul style={{ listStyle: "none", padding: 0, margin: "0 0 28px" }}>
                    {p.features.map((f, j) => (
                      <li key={j} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", fontSize: 14, color: C.mid }}>
                        <span style={{ color: C.green, fontWeight: 700, fontSize: 16, flexShrink: 0 }}>&#10003;</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                  <button onClick={() => go(`/checkout?plan=${p.key}`)} className="l-btn" style={{
                    width: "100%", padding: "13px 0", borderRadius: 10, fontSize: 14, fontWeight: 700,
                    background: p.popular ? `linear-gradient(135deg, ${C.accent}, ${C.violet})` : "transparent",
                    color: p.popular ? "#fff" : C.accent,
                    border: p.popular ? "none" : `1.5px solid ${C.accent}`,
                    cursor: "pointer",
                    boxShadow: p.popular ? `0 4px 14px ${C.accent}30` : "none",
                  }}>Elegir {p.name}</button>
                </div>
              </RevealSection>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 5. FORMULARIO DE CONTACTO ═══ */}
      <section id="contacto" style={{ padding: "100px 24px", background: "#F7F7F8" }}>
        <div style={{ maxWidth: 680, margin: "0 auto" }}>
          <RevealSection>
            <SectionTitle
              tag="Contacto"
              title="¿Tienes preguntas? Escríbenos"
              subtitle="Nuestro equipo te responderá en menos de 24 horas."
            />
          </RevealSection>
          <RevealSection delay={100}>
            {formStatus === "sent" ? (
              <div style={{
                textAlign: "center", padding: "48px 24px", borderRadius: 20,
                background: C.greenBg, border: "1px solid #A7F3D0",
              }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>&#10004;&#65039;</div>
                <h3 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>Mensaje enviado</h3>
                <p style={{ fontSize: 15, color: C.mid, margin: "0 0 20px" }}>Gracias por contactarnos. Te responderemos a la brevedad.</p>
                <button onClick={() => setFormStatus("idle")} className="l-btn" style={{ padding: "10px 24px", borderRadius: 10, fontSize: 14, fontWeight: 600, background: C.accent, color: "#fff", border: "none", cursor: "pointer" }}>Enviar otro mensaje</button>
              </div>
            ) : (
              <form onSubmit={handleContact} style={{
                background: C.white, borderRadius: 20, padding: "36px 32px",
                border: `1px solid ${C.border}`, boxShadow: "0 4px 20px rgba(0,0,0,.04)",
              }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                  <div>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Nombre *</label>
                    <input className="l-input" required placeholder="Tu nombre completo" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} style={inputStyle} />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Email *</label>
                    <input className="l-input" required type="email" placeholder="tu@email.com" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} style={inputStyle} />
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                  <div>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Teléfono</label>
                    <input className="l-input" placeholder="+56 9 1234 5678" value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })} style={inputStyle} />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Nombre del negocio</label>
                    <input className="l-input" placeholder="Mi negocio" value={formData.business} onChange={(e) => setFormData({ ...formData, business: e.target.value })} style={inputStyle} />
                  </div>
                </div>
                <div style={{ marginBottom: 20 }}>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Mensaje *</label>
                  <textarea className="l-input" required placeholder="Cuéntanos sobre tu negocio y qué necesitas..." value={formData.message} onChange={(e) => setFormData({ ...formData, message: e.target.value })} rows={4} style={{ ...inputStyle, resize: "vertical", minHeight: 100 }} />
                </div>
                {formStatus === "error" && (
                  <div style={{ padding: "10px 16px", borderRadius: 10, background: "#FEF2F2", color: C.red, fontSize: 13, marginBottom: 16, border: "1px solid #FECACA" }}>Error al enviar. Intenta nuevamente.</div>
                )}
                <button type="submit" disabled={formStatus === "sending"} className="l-btn" style={{
                  width: "100%", padding: "14px 0", borderRadius: 12, fontSize: 15, fontWeight: 700,
                  background: formStatus === "sending" ? C.mute : `linear-gradient(135deg, ${C.accent}, ${C.violet})`,
                  color: "#fff", border: "none", cursor: formStatus === "sending" ? "wait" : "pointer",
                  boxShadow: formStatus === "sending" ? "none" : `0 4px 14px ${C.accent}30`,
                }}>{formStatus === "sending" ? "Enviando..." : "Enviar mensaje"}</button>
                <p style={{ fontSize: 12, color: C.light, textAlign: "center", marginTop: 12 }}>
                  También puedes escribirnos a <a href="mailto:contacto@pulstock.cl" style={{ color: C.accent, textDecoration: "none" }}>contacto@pulstock.cl</a>
                </p>
              </form>
            )}
          </RevealSection>
        </div>
      </section>

      {/* ═══ CTA FINAL ═══ */}
      <section style={{
        padding: "80px 24px",
        background: `linear-gradient(135deg, ${C.text} 0%, #27272A 100%)`,
        textAlign: "center", position: "relative", overflow: "hidden",
      }}>
        <div style={{ position: "absolute", inset: 0, backgroundImage: `radial-gradient(circle at 30% 50%, ${C.accent}12 0%, transparent 50%)` }} />
        <div style={{ maxWidth: 600, margin: "0 auto", position: "relative" }}>
          <h2 style={{ fontSize: "clamp(26px, 4vw, 40px)", fontWeight: 900, color: "#fff", margin: "0 0 12px" }}>Empieza a controlar tu negocio hoy</h2>
          <p style={{ fontSize: 16, color: "rgba(255,255,255,.6)", margin: "0 0 32px" }}>Paga y accede hoy. Configura en 5 minutos.</p>
          <button onClick={() => go("/#precios")} className="l-btn" style={{
            padding: "16px 40px", fontSize: 17, fontWeight: 800,
            background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`,
            color: "#fff", border: "none", borderRadius: 12, cursor: "pointer",
            boxShadow: `0 4px 20px ${C.accent}50`,
          }}>Ver planes</button>
        </div>
      </section>

      {/* ═══ FOOTER ═══ */}
      <footer style={{ padding: "40px 24px", background: C.text, borderTop: "1px solid #27272A" }}>
        <div style={{ maxWidth: 1140, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              width: 28, height: 28, borderRadius: 8,
              background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, fontWeight: 900, color: "#fff",
            }}>P</div>
            <span style={{ fontSize: 14, fontWeight: 700, color: "rgba(255,255,255,.8)" }}>Pulstock</span>
          </div>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            {[["#problema","Problema"],["#como-funciona","Cómo funciona"],["#precios","Precios"],["#contacto","Contacto"]].map(([href,label]) => (
              <a key={href} href={href} style={{ fontSize: 13, color: "rgba(255,255,255,.5)", textDecoration: "none" }}>{label}</a>
            ))}
          </div>
          <p style={{ fontSize: 12, color: "rgba(255,255,255,.3)" }}>&copy; 2026 Pulstock. Todos los derechos reservados.</p>
        </div>
      </footer>
    </div>
  );
}
