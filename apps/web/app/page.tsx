"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef, useCallback } from "react";
import { getAccessToken } from "@/lib/api";
import { LogoIcon } from "@/components/ui/Logo";

const C = {
  accent: "#4F46E5", accentDark: "#4338CA", violet: "#7C3AED",
  bg: "#FAFAFA", white: "#FFFFFF", text: "#18181B", mid: "#52525B",
  mute: "#71717A", light: "#A1A1AA", border: "#E4E4E7",
  green: "#16A34A", greenBg: "#ECFDF5", red: "#DC2626",
  amber: "#D97706", amberBg: "#FFFBEB",
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const fCLP = (n: number) => "$" + n.toLocaleString("es-CL");

/* ═══════════════════════════════════════════════════════════════
   DATA
   ═══════════════════════════════════════════════════════════════ */

const PROBLEMS = [
  {
    icon: "🚫", title: "Quiebre de stock",
    cost: "Pierdes ventas cada semana",
    desc: "Un cliente pide un producto y no lo tienes. Se va a la competencia y no vuelve. Esto pasa todos los días en negocios sin predicción de demanda.",
    solution: "Pulstock te avisa 7 días antes de que se agote un producto.",
  },
  {
    icon: "📦", title: "Sobrestock",
    cost: "Plata muerta en bodega",
    desc: "Compraste de más \"por si acaso\". Ahora tienes capital estancado, productos vencidos y espacio desperdiciado.",
    solution: "Te muestra qué productos no rotan y cuánta plata tienes estancada.",
  },
  {
    icon: "🎲", title: "Compras a ciegas",
    cost: "Compras por intuición, no por datos",
    desc: "Sin historial ni predicción, cada orden de compra es una apuesta. A veces aciertas, muchas veces no.",
    solution: "Genera órdenes de compra automáticas basadas en tu demanda real.",
  },
];

const HOW_IT_WORKS = [
  { num: "01", title: "Registra tu inventario", desc: "Sube tu catálogo desde Excel o créalo desde cero. Categorías, barcodes, unidades de medida, costos y precios.", icon: "📦" },
  { num: "02", title: "Vende y registra compras", desc: "Cada venta y cada compra actualiza el stock automáticamente. Costo promedio ponderado se recalcula en tiempo real.", icon: "🛒" },
  { num: "03", title: "La IA analiza tu demanda", desc: "11 algoritmos de forecasting compiten entre sí. El sistema elige el mejor para cada producto, automáticamente.", icon: "🤖" },
  { num: "04", title: "Actúa con datos, no intuición", desc: "Recibes alertas de quiebre, sugerencias de compra, y un reporte ABC semanal. Decides con información, no con miedo.", icon: "📊" },
];

const BENEFITS = [
  { icon: "🔮", title: "Predicción de demanda con IA", desc: "11 algoritmos (Holt-Winters, Theta, ETS, Croston) compiten para predecir la demanda de cada producto. Se auto-selecciona el mejor.", tag: "Solo en Pulstock" },
  { icon: "🚨", title: "Alertas antes del quiebre", desc: "Sabes 7 días antes qué productos se van a agotar. Con nivel de confianza y sugerencia de cantidad a comprar.", tag: "Automático" },
  { icon: "📊", title: "Análisis ABC semanal", desc: "Cada lunes recibes un email con tus productos A (los que generan el 80% del ingreso), los B y los C.", tag: "Automático" },
  { icon: "💰", title: "Margen real por producto", desc: "Costo promedio ponderado (PPP) se recalcula con cada compra. Sabes el margen real de cada venta, no un estimado.", tag: "Tiempo real" },
  { icon: "🏪", title: "Multi-local + transferencias", desc: "Gestiona bodegas y sucursales. Transfiere stock entre locales con trazabilidad completa y costeo automático.", tag: "Incluido" },
];

const BUSINESS_TYPES = [
  { type: "restaurant", label: "Restaurant / Cafetería", icon: "🍽️",
    headline: "Sabe cuántos kilos de pollo necesitas el viernes",
    desc: "Maneja recetas, porciones y mermas — todo conectado con el inventario. El forecast aprende los patrones de tu carta.",
    features: ["Recetas con costeo automático", "Forecast por día de la semana", "Mesas y órdenes en tiempo real", "Unidades: OZ, tazas, porciones"] },
  { type: "retail", label: "Minimarket / Retail", icon: "🏪",
    headline: "Deja de perder ventas por estantes vacíos",
    desc: "Alertas de reposición antes de que se acabe. POS rápido con scanner. Análisis ABC para saber qué rinde.",
    features: ["Alertas de stock mínimo", "POS con búsqueda por barcode", "Análisis ABC automático", "11 reportes de ventas y margen"] },
  { type: "hardware", label: "Ferretería / Materiales", icon: "🔧",
    headline: "Miles de SKUs bajo control real",
    desc: "Categorías jerárquicas, unidades especiales (pulgadas, m², pies), y ABC para saber cuáles generan el 80% de tu ingreso.",
    features: ["Categorías multinivel", "Unidades: PLG, M², PIE, GAL", "Análisis ABC por revenue", "Transferencias entre bodegas"] },
  { type: "pharmacy", label: "Farmacia", icon: "💊",
    headline: "Nunca le digas a un paciente 'no tenemos'",
    desc: "Control preciso con unidades farmacéuticas (mg, ml, gotas). Alertas de stock mínimo para medicamentos críticos.",
    features: ["Unidades: MG, MCG, CC, gotas", "Alertas de stock crítico", "Trazabilidad completa", "Multi-bodega"] },
  { type: "wholesale", label: "Distribuidora / Mayorista", icon: "🚛",
    headline: "Planifica tu cadena de distribución con datos",
    desc: "Multi-bodega con transferencias y costeo PPP. Forecast de demanda para planificar compras a proveedores.",
    features: ["Multi-bodega con transferencias", "Costeo PPP automático", "Forecast para planificar compras", "Unidades: bulto, pallet, tonelada"] },
];

const COMPARISON = [
  { feature: "POS / Punto de venta", us: true, them: true },
  { feature: "Inventario básico", us: true, them: true },
  { feature: "Predicción de demanda (11 algoritmos)", us: true, them: false },
  { feature: "Alertas de quiebre 7 días antes", us: true, them: false },
  { feature: "Análisis ABC semanal por email", us: true, them: false },
  { feature: "Multi-bodega con costo PPP", us: true, them: false },
  { feature: "Reportes de margen real", us: true, them: false },
  { feature: "Recetas con costeo", us: true, them: false },
  { feature: "Forecast por tipo de negocio", us: true, them: false },
];

const IMPACT_STATS = [
  { value: "40%", label: "Menos quiebres de stock", desc: "con alertas predictivas" },
  { value: "25%", label: "Menos sobrestock", desc: "con análisis ABC" },
  { value: "4h", label: "Ahorro semanal", desc: "en órdenes de compra" },
  { value: "11", label: "Algoritmos de forecast", desc: "auto-selección por producto" },
];

const PLANS = [
  { key: "inicio", name: "Inicio", price: 19000, popular: false, features: ["Hasta 120 productos", "1 local · 1 bodega", "Hasta 10 usuarios", "POS completo", "Reportes básicos", "Soporte por email"] },
  { key: "crecimiento", name: "Crecimiento", price: 25990, popular: true, features: ["Hasta 400 productos", "2 locales · 3 bodegas", "Hasta 15 usuarios", "Forecast con IA", "Análisis ABC semanal", "11 reportes avanzados", "Soporte prioritario"] },
  { key: "pro", name: "Pro", price: 59990, popular: false, features: ["Hasta 1000 productos", "5 locales · bodegas ilimitadas", "Usuarios ilimitados", "Forecast con IA", "Análisis ABC + email semanal", "Transferencias entre locales", "PDF exports", "Soporte dedicado"] },
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

function useCounter(target: number, suffix: string, duration = 1500) {
  const [val, setVal] = useState("0");
  const [started, setStarted] = useState(false);
  const start = useCallback(() => setStarted(true), []);

  useEffect(() => {
    if (!started) return;
    const t = typeof target === "number" ? target : parseInt(target);
    const s = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - s) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setVal(String(Math.round(t * eased)));
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [started, target, duration]);

  return { val: val + suffix, start };
}

/* ═══════════════════════════════════════════════════════════════
   MICRO COMPONENTS
   ═══════════════════════════════════════════════════════════════ */

function SectionTitle({ tag, title, subtitle }: { tag: string; title: string; subtitle?: string }) {
  return (
    <div style={{ textAlign: "center", marginBottom: 56 }}>
      <p style={{ fontSize: 13, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 8 }}>{tag}</p>
      <h2 style={{ fontSize: "clamp(26px, 4vw, 40px)", fontWeight: 900, margin: 0, lineHeight: 1.15 }}>{title}</h2>
      {subtitle && <p style={{ fontSize: 16, color: C.mid, marginTop: 12, maxWidth: 600, margin: "12px auto 0", lineHeight: 1.6 }}>{subtitle}</p>}
    </div>
  );
}

function RevealSection({ children, style, delay = 0 }: { children: React.ReactNode; style?: React.CSSProperties; delay?: number }) {
  const { ref, visible } = useScrollReveal();
  return (
    <div ref={ref} style={{ ...style, opacity: visible ? 1 : 0, transform: visible ? "none" : "translateY(32px)",
      transition: `opacity .7s cubic-bezier(.16,1,.3,1) ${delay}ms, transform .7s cubic-bezier(.16,1,.3,1) ${delay}ms` }}>
      {children}
    </div>
  );
}

function ImpactCounter({ target, suffix, label, desc }: { target: string; suffix: string; label: string; desc: string }) {
  const numericTarget = parseInt(target) || 0;
  const { val, start } = useCounter(numericTarget, suffix);
  const { ref, visible } = useScrollReveal();
  useEffect(() => { if (visible) start(); }, [visible, start]);
  return (
    <div ref={ref} style={{ textAlign: "center" }}>
      <div style={{ fontSize: 48, fontWeight: 900, color: "#fff", lineHeight: 1 }}>{visible ? val : "0" + suffix}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: "rgba(255,255,255,.9)", marginTop: 6 }}>{label}</div>
      <div style={{ fontSize: 12, color: "rgba(255,255,255,.5)", marginTop: 2 }}>{desc}</div>
    </div>
  );
}

function DashboardMockup() {
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", perspective: "1200px" }}>
      <div style={{
        background: C.white, borderRadius: 16, overflow: "hidden",
        boxShadow: "0 40px 80px rgba(0,0,0,.12), 0 0 0 1px rgba(0,0,0,.05)",
        transform: "rotateX(4deg) rotateY(-2deg)", transition: "transform .4s ease",
      }}>
        <div style={{ background: "#F4F4F5", padding: "10px 16px", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid #E4E4E7" }}>
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#EF4444" }} />
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#F59E0B" }} />
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#22C55E" }} />
          <div style={{ flex: 1, textAlign: "center", fontSize: 11, color: C.mute }}>pulstock.cl/dashboard</div>
        </div>
        <div style={{ display: "flex", minHeight: 320 }}>
          <div className="mockup-sidebar" style={{ width: 180, background: "#18181B", padding: "16px 12px", flexShrink: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 800, color: C.accent, marginBottom: 16 }}>Pulstock</div>
            {["Dashboard", "Catálogo", "POS", "Inventario", "Forecast IA", "Reportes"].map((item, i) => (
              <div key={item} style={{ padding: "8px 10px", borderRadius: 6, marginBottom: 2, fontSize: 12,
                background: i === 4 ? C.accent + "22" : "transparent",
                color: i === 4 ? C.white : "#A1A1AA", fontWeight: i === 4 ? 700 : 400 }}>{item}</div>
            ))}
          </div>
          <div style={{ flex: 1, padding: 20 }}>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
              Predicción de Demanda
              <span style={{ fontSize: 10, padding: "3px 8px", borderRadius: 10, background: "#EEF2FF", color: C.accent, fontWeight: 700 }}>IA</span>
            </div>
            <div className="mockup-kpis" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10, marginBottom: 16 }}>
              {[
                { label: "En riesgo", value: "3", color: C.red },
                { label: "Sugerencias", value: "7", color: C.amber },
                { label: "Precisión", value: "87%", color: C.green },
                { label: "Productos", value: "342", color: C.accent },
              ].map((kpi) => (
                <div key={kpi.label} style={{ background: "#F9FAFB", borderRadius: 10, padding: "10px 12px", border: "1px solid #F3F4F6" }}>
                  <div style={{ fontSize: 9, color: C.mute, textTransform: "uppercase" }}>{kpi.label}</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color: kpi.color, marginTop: 2 }}>{kpi.value}</div>
                </div>
              ))}
            </div>
            {/* Alert banner */}
            <div style={{ background: "#FEF2F2", borderRadius: 10, padding: "10px 14px", border: "1px solid #FECACA", marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 14 }}>🚨</span>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: C.red }}>Arroz Grado 1 se agota en 3 dias</div>
                <div style={{ fontSize: 10, color: C.mute }}>Sugerencia: comprar 50 KG a Proveedor SA</div>
              </div>
            </div>
            <div style={{ background: "#F9FAFB", borderRadius: 10, padding: 14, border: "1px solid #F3F4F6" }}>
              <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 8 }}>Forecast vs real (7 dias)</div>
              <svg viewBox="0 0 300 60" style={{ width: "100%", height: 60 }}>
                <defs>
                  <linearGradient id="mockGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={C.accent} stopOpacity="0.2" />
                    <stop offset="100%" stopColor={C.accent} stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path d="M 0 45 Q 30 35, 50 38 T 100 28 T 150 32 T 200 18 T 250 22 T 300 10" fill="none" stroke={C.accent} strokeWidth="2.5" strokeLinecap="round" />
                <path d="M 0 45 Q 30 35, 50 38 T 100 28 T 150 32 T 200 18 T 250 22 T 300 10 V 60 H 0 Z" fill="url(#mockGrad)" />
                <path d="M 0 42 Q 30 38, 50 40 T 100 30 T 150 28 T 200 20 T 250 24 T 300 12" fill="none" stroke={C.green} strokeWidth="1.5" strokeDasharray="4 3" strokeLinecap="round" />
              </svg>
              <div style={{ display: "flex", gap: 16, marginTop: 4 }}>
                <span style={{ fontSize: 9, color: C.accent, display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ width: 12, height: 2, background: C.accent, borderRadius: 1 }} /> Predicho
                </span>
                <span style={{ fontSize: 9, color: C.green, display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ width: 12, height: 2, background: C.green, borderRadius: 1, borderStyle: "dashed" }} /> Real
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   PAGE
   ═══════════════════════════════════════════════════════════════ */

const FAQ_ITEMS = [
  {
    q: "¿Ya tengo mis datos en Excel, puedo importarlos?",
    a: "Sí. Pulstock importa productos desde Excel (.xlsx) o CSV en un solo paso. Categorías, SKU, precios, costos y barcodes se mapean automáticamente.",
  },
  {
    q: "¿Cuánto demora configurar todo?",
    a: "Si importas desde Excel, en 10 minutos ya estás vendiendo. Si partes de cero, el asistente de configuración te guía paso a paso: negocio, local, bodega, y tus primeros productos.",
  },
  {
    q: "¿Funciona con boleta electrónica del SII?",
    a: "Pulstock se enfoca en gestión de inventario y POS interno. Para facturación electrónica puedes conectarlo con tu sistema de boletas actual. Estamos trabajando en integración directa con el SII.",
  },
  {
    q: "¿Qué pasa con mis datos si cancelo?",
    a: "Tus datos se conservan por 30 días después de cancelar. Puedes exportar todo a Excel en cualquier momento desde Reportes. No hay penalidad por cancelar.",
  },
  {
    q: "¿Cómo funciona la predicción de demanda?",
    a: "El sistema analiza tu historial de ventas con 11 algoritmos de forecasting. Automáticamente elige el mejor para cada producto según su patrón de demanda (estacional, intermitente, lineal). No necesitas configurar nada.",
  },
  {
    q: "¿Puedo usar Pulstock en varios locales?",
    a: "Sí. Cada local tiene sus propias bodegas, stock y usuarios. Puedes transferir productos entre locales con trazabilidad completa y costeo automático.",
  },
  {
    q: "¿Necesito instalar algo?",
    a: "No. Pulstock es 100% en la nube. Funciona desde cualquier navegador en computador, tablet o celular. También puedes instalarlo como app desde Chrome.",
  },
  {
    q: "¿Mis datos están seguros?",
    a: "Sí. Usamos HTTPS con cifrado TLS, autenticación JWT con tokens seguros, y cada negocio tiene sus datos completamente aislados (multi-tenant). Los respaldos son automáticos.",
  },
];

function FAQSection() {
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <section id="faq" style={{ padding: "100px 24px", background: C.white }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <RevealSection>
          <SectionTitle tag="Preguntas frecuentes" title="Todo lo que necesitas saber"
            subtitle="Si no encuentras tu respuesta, escríbenos." />
        </RevealSection>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {FAQ_ITEMS.map((item, i) => {
            const isOpen = openIdx === i;
            return (
              <RevealSection key={i} delay={i * 40}>
                <div style={{
                  background: isOpen ? "#FAFAFE" : C.white,
                  border: `1px solid ${isOpen ? C.accent + "30" : C.border}`,
                  borderRadius: 12, overflow: "hidden",
                  transition: "all .2s ease",
                }}>
                  <button
                    type="button"
                    onClick={() => setOpenIdx(isOpen ? null : i)}
                    style={{
                      width: "100%", padding: "18px 22px",
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      gap: 16, background: "none", border: "none", cursor: "pointer",
                      textAlign: "left", fontFamily: "inherit",
                    }}
                  >
                    <span style={{ fontSize: 15, fontWeight: 600, color: C.text, lineHeight: 1.4 }}>
                      {item.q}
                    </span>
                    <span style={{
                      fontSize: 18, color: C.accent, flexShrink: 0,
                      transform: isOpen ? "rotate(45deg)" : "none",
                      transition: "transform .2s ease",
                      fontWeight: 300, lineHeight: 1,
                    }}>+</span>
                  </button>
                  <div style={{
                    maxHeight: isOpen ? 200 : 0,
                    overflow: "hidden",
                    transition: "max-height .3s cubic-bezier(.16,1,.3,1)",
                  }}>
                    <p style={{
                      margin: 0, padding: "0 22px 18px",
                      fontSize: 14, color: C.mid, lineHeight: 1.7,
                    }}>
                      {item.a}
                    </p>
                  </div>
                </div>
              </RevealSection>
            );
          })}
        </div>
      </div>
    </section>
  );
}

const DEMO_PRODUCTS = [
  { name: "Arroz Grado 1", sku: "ARR-001", stock: 12, min: 50, daily: 8.5, days: 1, status: "critical" as const },
  { name: "Aceite Vegetal 1L", sku: "ACE-002", stock: 28, min: 40, daily: 5.2, days: 5, status: "warning" as const },
  { name: "Harina Sin Preparar", sku: "HAR-003", stock: 8, min: 30, daily: 3.8, days: 2, status: "critical" as const },
  { name: "Azúcar Granulada", sku: "AZU-004", stock: 95, min: 60, daily: 6.1, days: 15, status: "ok" as const },
  { name: "Sal de Mar 1KG", sku: "SAL-005", stock: 45, min: 20, daily: 2.3, days: 19, status: "ok" as const },
];

function LiveDemoWidget() {
  const { ref, visible } = useScrollReveal();
  const [step, setStep] = useState(0);
  const [showSuggestion, setShowSuggestion] = useState(false);

  // Auto-animate through steps
  useEffect(() => {
    if (!visible) return;
    const timers = [
      setTimeout(() => setStep(1), 800),
      setTimeout(() => setStep(2), 2000),
      setTimeout(() => setShowSuggestion(true), 3200),
    ];
    return () => timers.forEach(clearTimeout);
  }, [visible]);

  const statusColors = {
    critical: { bg: "#FEF2F2", bd: "#FECACA", text: "#DC2626", label: "Agotándose" },
    warning: { bg: "#FFFBEB", bd: "#FDE68A", text: "#D97706", label: "Bajo" },
    ok: { bg: "#ECFDF5", bd: "#A7F3D0", text: "#16A34A", label: "OK" },
  };

  return (
    <section ref={ref} style={{ padding: "80px 24px", background: `linear-gradient(180deg, #F7F7F8 0%, ${C.white} 100%)` }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <p style={{ fontSize: 13, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 8 }}>Demo en vivo</p>
          <h2 style={{ fontSize: "clamp(26px, 4vw, 36px)", fontWeight: 900, margin: 0, lineHeight: 1.15 }}>
            Así trabaja Pulstock por ti
          </h2>
          <p style={{ fontSize: 15, color: C.mid, marginTop: 10 }}>
            Mira cómo detecta problemas y sugiere acciones automáticamente.
          </p>
        </div>

        {/* Simulated dashboard */}
        <div style={{
          background: C.white, borderRadius: 16, overflow: "hidden",
          boxShadow: "0 20px 60px rgba(0,0,0,.08), 0 0 0 1px rgba(0,0,0,.04)",
          border: `1px solid ${C.border}`,
        }}>
          {/* Top bar */}
          <div style={{ padding: "12px 20px", background: "#F9FAFB", borderBottom: `1px solid ${C.border}`,
            display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <LogoIcon size={24} />
              <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Dashboard de Inventario</span>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 10, background: "#FEF2F2",
                color: "#DC2626", fontWeight: 700, border: "1px solid #FECACA" }}>2 Críticos</span>
              <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 10, background: "#FFFBEB",
                color: "#D97706", fontWeight: 700, border: "1px solid #FDE68A" }}>1 Bajo</span>
            </div>
          </div>

          {/* Product table */}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#F9FAFB", borderBottom: `2px solid ${C.border}` }}>
                  {["Producto", "SKU", "Stock", "Mínimo", "Venta/día", "Días restantes", "Estado"].map(h => (
                    <th key={h} style={{ padding: "10px 14px", fontSize: 10, fontWeight: 700, color: C.mute,
                      textTransform: "uppercase", letterSpacing: ".05em", textAlign: h === "Producto" ? "left" : "right" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {DEMO_PRODUCTS.map((p, i) => {
                  const sc = statusColors[p.status];
                  const isHighlighted = step >= 1 && p.status === "critical";
                  return (
                    <tr key={p.sku} style={{
                      borderBottom: `1px solid ${C.border}`,
                      background: isHighlighted ? "#FEF2F240" : "transparent",
                      transition: "background .5s ease",
                    }}>
                      <td style={{ padding: "12px 14px", fontWeight: 600 }}>{p.name}</td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "monospace", color: C.mute, fontSize: 11 }}>{p.sku}</td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontWeight: 700,
                        color: p.status === "critical" ? "#DC2626" : p.status === "warning" ? "#D97706" : C.text }}>
                        {p.stock}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", color: C.mute }}>{p.min}</td>
                      <td style={{ padding: "12px 14px", textAlign: "right", color: C.mid }}>{p.daily}</td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontWeight: 700,
                        color: p.days <= 3 ? "#DC2626" : p.days <= 7 ? "#D97706" : C.text }}>
                        {p.days} días
                      </td>
                      <td style={{ padding: "12px 8px", textAlign: "right" }}>
                        <span style={{ display: "inline-block", padding: "3px 10px", borderRadius: 10,
                          fontSize: 10, fontWeight: 700, background: sc.bg, color: sc.text,
                          border: `1px solid ${sc.bd}`,
                          opacity: step >= 1 ? 1 : 0, transition: "opacity .5s ease",
                          transitionDelay: `${i * 100}ms`,
                        }}>{sc.label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Alert banner — slides in */}
          <div style={{
            margin: "0 16px 16px", padding: step >= 2 ? "14px 18px" : "0 18px",
            borderRadius: 12, background: "#FEF2F2", border: "1px solid #FECACA",
            maxHeight: step >= 2 ? 80 : 0, overflow: "hidden",
            transition: "all .6s cubic-bezier(.16,1,.3,1)",
            display: "flex", alignItems: "center", gap: 12,
          }}>
            <span style={{ fontSize: 20 }}>🚨</span>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#DC2626" }}>
                Arroz Grado 1 se agota en 1 día
              </div>
              <div style={{ fontSize: 11, color: C.mute }}>
                Ventas promedio: 8.5 un/día · Stock actual: 12 · Mínimo: 50
              </div>
            </div>
          </div>

          {/* Suggestion card — slides in */}
          <div style={{
            margin: "0 16px 16px", padding: showSuggestion ? "14px 18px" : "0 18px",
            borderRadius: 12, background: "#EEF2FF", border: `1px solid #C7D2FE`,
            maxHeight: showSuggestion ? 100 : 0, overflow: "hidden",
            transition: "all .6s cubic-bezier(.16,1,.3,1)",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 20 }}>📋</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.accent }}>
                  Sugerencia de compra generada
                </div>
                <div style={{ fontSize: 12, color: C.mid }}>
                  Arroz Grado 1: <strong>comprar 50 KG</strong> · Harina: <strong>comprar 30 KG</strong>
                </div>
              </div>
            </div>
            <div style={{
              padding: "8px 16px", borderRadius: 8, fontSize: 12, fontWeight: 700,
              background: C.accent, color: "#fff", whiteSpace: "nowrap",
            }}>
              Aprobar pedido
            </div>
          </div>
        </div>

        {/* Caption */}
        <div style={{ textAlign: "center", marginTop: 20 }}>
          <p style={{ fontSize: 13, color: C.mute, margin: 0 }}>
            Todo esto pasa automáticamente. Solo tienes que aprobar.
          </p>
        </div>
      </div>
    </section>
  );
}


export default function LandingPage() {
  const router = useRouter();
  const [scrolled, setScrolled] = useState(false);
  const [formData, setFormData] = useState({ name: "", email: "", phone: "", business: "", message: "" });
  const [formStatus, setFormStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [activeStep, setActiveStep] = useState(0);
  const [activeBiz, setActiveBiz] = useState(0);
  const [mobileMenu, setMobileMenu] = useState(false);

  useEffect(() => {
    if (getAccessToken()) { router.replace("/dashboard"); return; }
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const iv = setInterval(() => setActiveStep((s) => (s + 1) % HOW_IT_WORKS.length), 4000);
    return () => clearInterval(iv);
  }, []);

  const go = (path: string) => router.push(path);

  const handleContact = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormStatus("sending");
    try {
      await fetch(`${API}/core/contact/`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      }).catch(() => {});
      setFormStatus("sent");
      setFormData({ name: "", email: "", phone: "", business: "", message: "" });
    } catch { setFormStatus("error"); }
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
        .biz-tab { transition: all .2s; cursor: pointer; border: none; background: none; }
        .biz-tab:hover { background: #EEF2FF; }
        html { scroll-behavior: smooth; }
        @media (max-width: 768px) {
          .desk-nav { display: none !important; }
          .mob-toggle { display: flex !important; }
          .steps-grid { grid-template-columns: 1fr !important; }
          .contact-row { grid-template-columns: 1fr !important; }
          .mockup-sidebar { display: none !important; }
          .mockup-kpis { grid-template-columns: 1fr 1fr !important; }
          .benefits-grid { grid-template-columns: 1fr !important; }
          .comparison-table { font-size: 12px !important; }
          .biz-tabs { flex-wrap: wrap !important; }
          .impact-grid { grid-template-columns: 1fr 1fr !important; }
          .footer-inner { flex-direction: column !important; text-align: center; }
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
            <LogoIcon size={36} />
            <span style={{ fontSize: 18, fontWeight: 800 }}>Pulstock</span>
          </div>
          <div className="desk-nav" style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {[["#problema","Problema"],["#como-funciona","Cómo funciona"],["#beneficios","Beneficios"],["#negocios","Tu negocio"],["#precios","Precios"],["#faq","FAQ"],["#contacto","Contacto"]].map(([href,label]) => (
              <a key={href} href={href} style={{ padding: "8px 12px", fontSize: 13, color: C.mid, textDecoration: "none", fontWeight: 500, borderRadius: 6 }}>{label}</a>
            ))}
            <button onClick={() => go("/login")} style={{ padding: "8px 16px", fontSize: 13, fontWeight: 600, background: "transparent", color: C.accent, border: `1px solid ${C.border}`, borderRadius: 8, cursor: "pointer", marginLeft: 4 }}>Ingresar</button>
            <button onClick={() => go("/#precios")} className="l-btn" style={{ padding: "8px 16px", fontSize: 13, fontWeight: 700, background: C.accent, color: "#fff", border: "none", borderRadius: 8, cursor: "pointer" }}>Ver planes</button>
          </div>
          <button className="mob-toggle" onClick={() => setMobileMenu(!mobileMenu)} style={{ display: "none", background: "none", border: "none", fontSize: 22, cursor: "pointer", padding: 4, color: C.text }}>
            {mobileMenu ? "\u2715" : "\u2630"}
          </button>
        </div>
        {mobileMenu && (
          <div className="mob-menu" style={{ background: C.white, borderTop: `1px solid ${C.border}`, padding: "12px 24px" }}>
            {[["#problema","Problema"],["#como-funciona","Cómo funciona"],["#beneficios","Beneficios"],["#negocios","Tu negocio"],["#precios","Precios"],["#faq","FAQ"],["#contacto","Contacto"]].map(([href,label]) => (
              <a key={href} href={href} onClick={() => setMobileMenu(false)} style={{ display: "block", padding: "10px 0", fontSize: 14, color: C.mid, textDecoration: "none" }}>{label}</a>
            ))}
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button onClick={() => go("/login")} style={{ flex: 1, padding: "10px 0", fontSize: 13, fontWeight: 600, background: "transparent", color: C.accent, border: `1px solid ${C.border}`, borderRadius: 8, cursor: "pointer" }}>Ingresar</button>
              <button onClick={() => go("/#precios")} style={{ flex: 1, padding: "10px 0", fontSize: 13, fontWeight: 700, background: C.accent, color: "#fff", border: "none", borderRadius: 8, cursor: "pointer" }}>Ver planes</button>
            </div>
          </div>
        )}
      </nav>

      {/* ═══ HERO — Value proposition ═══ */}
      <section style={{
        minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        background: `linear-gradient(135deg, #FAFAFA 0%, #EEF2FF 40%, #F5F3FF 70%, #FAFAFA 100%)`,
        position: "relative", overflow: "hidden", paddingTop: 80,
      }}>
        <div style={{ position: "absolute", inset: 0, backgroundImage: `linear-gradient(${C.accent}06 1px, transparent 1px), linear-gradient(90deg, ${C.accent}06 1px, transparent 1px)`, backgroundSize: "60px 60px" }} />
        <div style={{ position: "absolute", top: "15%", left: "10%", width: 300, height: 300, borderRadius: "50%", background: `radial-gradient(circle, ${C.accent}0A, transparent)`, animation: "float 6s ease-in-out infinite" }} />
        <div style={{ position: "absolute", bottom: "20%", right: "8%", width: 200, height: 200, borderRadius: "50%", background: `radial-gradient(circle, ${C.violet}0A, transparent)`, animation: "float 8s ease-in-out infinite 1s" }} />

        <div style={{ textAlign: "center", maxWidth: 760, padding: "0 24px", position: "relative", zIndex: 1, animation: "fadeUp .6s cubic-bezier(.16,1,.3,1)" }}>
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "6px 16px", borderRadius: 20, fontSize: 12, fontWeight: 600,
            background: C.greenBg, color: C.green, marginBottom: 20,
            border: "1px solid #A7F3D0", animation: "pulse 2s ease-in-out infinite",
          }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: C.green }} />
            No es otro POS — es inteligencia de inventario
          </div>
          <h1 style={{ fontSize: "clamp(34px, 5.5vw, 58px)", fontWeight: 900, lineHeight: 1.08, margin: "0 0 20px", letterSpacing: "-.025em" }}>
            Tu inventario te cuesta plata.
            <br />
            <span style={{ background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              Nosotros lo hacemos rentable.
            </span>
          </h1>
          <p style={{ fontSize: "clamp(16px, 2vw, 19px)", color: C.mid, lineHeight: 1.6, maxWidth: 580, margin: "0 auto 36px" }}>
            Pulstock predice tu demanda, te avisa antes de quedarte sin stock,
            y te dice exactamente qué comprar y cuándo. Para pymes chilenas que quieren crecer con datos, no con intuición.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <button onClick={() => go("/#precios")} className="l-btn" style={{
              padding: "16px 36px", fontSize: 16, fontWeight: 800,
              background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`,
              color: "#fff", border: "none", borderRadius: 12, cursor: "pointer",
              boxShadow: `0 4px 14px ${C.accent}40`,
            }}>Comenzar ahora</button>
            <a href="#como-funciona" className="l-btn" style={{
              padding: "16px 36px", fontSize: 16, fontWeight: 600,
              background: C.white, color: C.text, border: `1px solid ${C.border}`,
              borderRadius: 12, cursor: "pointer", textDecoration: "none", display: "inline-flex", alignItems: "center",
            }}>Ver cómo funciona</a>
          </div>
        </div>

        <div style={{ maxWidth: 1000, width: "100%", padding: "60px 24px 0", position: "relative", zIndex: 1, animation: "fadeUp .8s cubic-bezier(.16,1,.3,1) .2s both" }}>
          <DashboardMockup />
        </div>
      </section>

      {/* ═══ 1. PROBLEMA QUE RESUELVE ═══ */}
      <section id="problema" style={{ padding: "100px 24px", maxWidth: 1140, margin: "0 auto" }}>
        <RevealSection>
          <SectionTitle tag="El problema" title="3 costos invisibles que destruyen tu margen"
            subtitle="La mayoría de las pymes pierden entre un 5% y 15% de sus ingresos por problemas de inventario que ni siquiera miden." />
        </RevealSection>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 20 }}>
          {PROBLEMS.map((p, i) => (
            <RevealSection key={i} delay={i * 100}>
              <div className="l-card" style={{
                background: C.white, borderRadius: 16, padding: 28, height: "100%",
                border: `1px solid ${C.border}`, boxShadow: "0 1px 3px rgba(0,0,0,.04)",
              }}>
                <div style={{ width: 52, height: 52, borderRadius: 14, background: "#FEF2F2",
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, marginBottom: 16 }}>{p.icon}</div>
                <h3 style={{ fontSize: 18, fontWeight: 800, margin: "0 0 4px" }}>{p.title}</h3>
                <p style={{ fontSize: 12, fontWeight: 700, color: C.red, margin: "0 0 8px", textTransform: "uppercase", letterSpacing: ".04em" }}>{p.cost}</p>
                <p style={{ fontSize: 14, color: C.mid, lineHeight: 1.7, margin: "0 0 16px" }}>{p.desc}</p>
                <div style={{ padding: "10px 14px", borderRadius: 10, background: "#EEF2FF", border: "1px solid #C7D2FE" }}>
                  <p style={{ fontSize: 13, fontWeight: 600, color: C.accent, margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 16 }}>&#10003;</span> {p.solution}
                  </p>
                </div>
              </div>
            </RevealSection>
          ))}
        </div>
      </section>

      {/* ═══ 2. CÓMO FUNCIONA ═══ */}
      <section id="como-funciona" style={{ padding: "100px 24px", background: C.white }}>
        <div style={{ maxWidth: 960, margin: "0 auto" }}>
          <RevealSection>
            <SectionTitle tag="Cómo funciona" title="De Excel a inteligencia artificial en 4 pasos"
              subtitle="Configura en minutos. El sistema aprende de tus ventas y empieza a predecir." />
          </RevealSection>
          <RevealSection>
            <div className="steps-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 40, alignItems: "start" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {HOW_IT_WORKS.map((s, i) => (
                  <div key={i} className="l-step" onClick={() => setActiveStep(i)} style={{
                    display: "flex", gap: 16, alignItems: "center", padding: "16px 18px", borderRadius: 14,
                    background: activeStep === i ? "#EEF2FF" : "transparent",
                    borderLeft: `3px solid ${activeStep === i ? C.accent : "transparent"}`,
                  }}>
                    <div style={{
                      width: 44, height: 44, borderRadius: 12, flexShrink: 0,
                      background: activeStep === i ? `linear-gradient(135deg, ${C.accent}, ${C.violet})` : "#F3F4F6",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 20, color: activeStep === i ? "#fff" : C.mute, transition: "all .3s",
                    }}>{s.icon}</div>
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: C.accent, marginBottom: 2 }}>PASO {s.num}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: activeStep === i ? C.text : C.mid }}>{s.title}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ background: "#F9FAFB", borderRadius: 20, padding: 36, border: `1px solid ${C.border}`, animation: "slideIn .35s ease" }} key={activeStep}>
                <div style={{ width: 72, height: 72, borderRadius: 18, marginBottom: 20,
                  background: `linear-gradient(135deg, ${C.accent}14, ${C.violet}14)`,
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 36 }}>{HOW_IT_WORKS[activeStep].icon}</div>
                <div style={{ fontSize: 11, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 6 }}>Paso {HOW_IT_WORKS[activeStep].num}</div>
                <h3 style={{ fontSize: 24, fontWeight: 900, margin: "0 0 12px" }}>{HOW_IT_WORKS[activeStep].title}</h3>
                <p style={{ fontSize: 15, color: C.mid, lineHeight: 1.8, margin: 0 }}>{HOW_IT_WORKS[activeStep].desc}</p>
                <div style={{ display: "flex", gap: 6, marginTop: 24 }}>
                  {HOW_IT_WORKS.map((_, i) => (
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

      {/* ═══ 3. BENEFICIOS — What makes us different ═══ */}
      <section id="beneficios" style={{ padding: "100px 24px", maxWidth: 1140, margin: "0 auto" }}>
        <RevealSection>
          <SectionTitle tag="Por qué Pulstock" title="No es otro POS. Es inteligencia de inventario."
            subtitle="Herramientas que solo encuentras en sistemas enterprise, ahora para tu pyme." />
        </RevealSection>
        <div className="benefits-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 20 }}>
          {BENEFITS.map((b, i) => (
            <RevealSection key={i} delay={i * 80}>
              <div className="l-card" style={{
                background: C.white, borderRadius: 16, padding: 28, height: "100%",
                border: `1px solid ${C.border}`, boxShadow: "0 1px 3px rgba(0,0,0,.04)", position: "relative", overflow: "hidden",
              }}>
                <div style={{ position: "absolute", top: -20, right: -20, width: 80, height: 80, borderRadius: "50%", background: `${C.accent}06` }} />
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                  <div style={{ width: 52, height: 52, borderRadius: 14, background: "#EEF2FF",
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, position: "relative" }}>{b.icon}</div>
                  <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 10px", borderRadius: 10,
                    background: b.tag === "Solo en Pulstock" ? "#EEF2FF" : b.tag === "Automático" ? C.greenBg : "#F4F4F5",
                    color: b.tag === "Solo en Pulstock" ? C.accent : b.tag === "Automático" ? C.green : C.mute,
                    border: `1px solid ${b.tag === "Solo en Pulstock" ? "#C7D2FE" : b.tag === "Automático" ? "#A7F3D0" : C.border}`,
                    textTransform: "uppercase", letterSpacing: ".04em" }}>{b.tag}</span>
                </div>
                <h3 style={{ fontSize: 17, fontWeight: 800, margin: "0 0 8px" }}>{b.title}</h3>
                <p style={{ fontSize: 14, color: C.mid, lineHeight: 1.7, margin: 0 }}>{b.desc}</p>
              </div>
            </RevealSection>
          ))}
        </div>
      </section>

      {/* ═══ LIVE DEMO WIDGET ═══ */}
      <LiveDemoWidget />

      {/* ═══ COMPARISON TABLE — vs tu sistema actual ═══ */}
      <section style={{ padding: "80px 24px", background: C.white }}>
        <div style={{ maxWidth: 700, margin: "0 auto" }}>
          <RevealSection>
            <SectionTitle tag="Comparativa" title="Tu sistema actual vs Pulstock" subtitle="Compara lo que tienes hoy con lo que podrías tener." />
          </RevealSection>
          <RevealSection delay={100}>
            <div className="comparison-table" style={{ borderRadius: 16, overflow: "hidden", border: `1px solid ${C.border}` }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 100px 100px", background: "#F9FAFB", borderBottom: `2px solid ${C.border}` }}>
                <div style={{ padding: "12px 20px", fontSize: 12, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Feature</div>
                <div style={{ padding: "12px 8px", fontSize: 12, fontWeight: 700, color: C.accent, textAlign: "center" }}>Pulstock</div>
                <div style={{ padding: "12px 8px", fontSize: 12, fontWeight: 700, color: C.mute, textAlign: "center" }}>Tu sistema actual</div>
              </div>
              {COMPARISON.map((row, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 100px 100px", borderBottom: i < COMPARISON.length - 1 ? `1px solid ${C.border}` : "none",
                  background: !row.them ? "#FAFAFE" : C.white }}>
                  <div style={{ padding: "11px 20px", fontSize: 13, color: C.mid, fontWeight: !row.them ? 600 : 400 }}>{row.feature}</div>
                  <div style={{ padding: "11px 8px", textAlign: "center", fontSize: 16, color: C.green }}>&#10003;</div>
                  <div style={{ padding: "11px 8px", textAlign: "center", fontSize: 16, color: row.them ? C.green : "#D4D4D8" }}>{row.them ? "\u2713" : "\u2715"}</div>
                </div>
              ))}
            </div>
          </RevealSection>
        </div>
      </section>

      {/* ═══ IMPACT STATS ═══ */}
      <section style={{ background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`, padding: "64px 24px", position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, backgroundImage: `radial-gradient(circle at 20% 50%, rgba(255,255,255,.08) 0%, transparent 50%)` }} />
        <div className="impact-grid" style={{ maxWidth: 900, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 30, position: "relative" }}>
          {IMPACT_STATS.map((s, i) => (
            <ImpactCounter key={i} target={s.value.replace(/[^0-9]/g, "")} suffix={s.value.replace(/[0-9]/g, "")} label={s.label} desc={s.desc} />
          ))}
        </div>
      </section>

      {/* ═══ 4. POR TIPO DE NEGOCIO ═══ */}
      <section id="negocios" style={{ padding: "100px 24px", maxWidth: 1000, margin: "0 auto" }}>
        <RevealSection>
          <SectionTitle tag="Tu negocio" title="Diseñado para tu tipo de negocio"
            subtitle="Cada giro tiene sus propios desafíos. Pulstock se adapta." />
        </RevealSection>
        <RevealSection delay={100}>
          <div className="biz-tabs" style={{ display: "flex", gap: 4, marginBottom: 32, justifyContent: "center", flexWrap: "wrap" }}>
            {BUSINESS_TYPES.map((b, i) => (
              <button key={b.type} className="biz-tab" onClick={() => setActiveBiz(i)} style={{
                padding: "10px 18px", borderRadius: 10, fontSize: 13, fontWeight: 600,
                background: activeBiz === i ? "#EEF2FF" : "transparent",
                color: activeBiz === i ? C.accent : C.mid,
                border: activeBiz === i ? `1px solid #C7D2FE` : `1px solid transparent`,
              }}>
                <span style={{ marginRight: 6 }}>{b.icon}</span>{b.label}
              </button>
            ))}
          </div>
          <div style={{ background: C.white, borderRadius: 20, padding: "40px 36px", border: `1px solid ${C.border}`, boxShadow: "0 4px 20px rgba(0,0,0,.04)" }} key={activeBiz}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <span style={{ fontSize: 36 }}>{BUSINESS_TYPES[activeBiz].icon}</span>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: ".04em" }}>{BUSINESS_TYPES[activeBiz].label}</div>
                <h3 style={{ fontSize: 22, fontWeight: 900, margin: 0 }}>{BUSINESS_TYPES[activeBiz].headline}</h3>
              </div>
            </div>
            <p style={{ fontSize: 15, color: C.mid, lineHeight: 1.7, margin: "0 0 24px" }}>{BUSINESS_TYPES[activeBiz].desc}</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {BUSINESS_TYPES[activeBiz].features.map((f, j) => (
                <div key={j} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, color: C.text, padding: "6px 0" }}>
                  <span style={{ color: C.green, fontWeight: 700, fontSize: 15, flexShrink: 0 }}>&#10003;</span> {f}
                </div>
              ))}
            </div>
          </div>
        </RevealSection>
      </section>

      {/* ═══ 5. PLANES ═══ */}
      <section id="precios" style={{ padding: "100px 24px", background: C.white }}>
        <div style={{ maxWidth: 1000, margin: "0 auto" }}>
          <RevealSection>
            <SectionTitle tag="Precios" title="Planes simples, sin letra chica"
              subtitle="Paga mensual, sin contratos. Cancela cuando quieras." />
          </RevealSection>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 20 }}>
            {PLANS.map((p, i) => (
              <RevealSection key={i} delay={i * 100}>
                <div className="l-card" style={{
                  background: C.white, borderRadius: 20, padding: 32,
                  border: p.popular ? `2px solid ${C.accent}` : `1px solid ${C.border}`,
                  boxShadow: p.popular ? `0 12px 40px ${C.accent}18` : "0 1px 3px rgba(0,0,0,.04)",
                  position: "relative", height: "100%", transform: p.popular ? "scale(1.03)" : "none",
                }}>
                  {p.popular && (
                    <div style={{
                      position: "absolute", top: -13, left: "50%", transform: "translateX(-50%)",
                      padding: "5px 20px", borderRadius: 20, fontSize: 11, fontWeight: 800,
                      background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`,
                      color: "#fff", textTransform: "uppercase", letterSpacing: ".06em",
                    }}>Recomendado</div>
                  )}
                  <h3 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 4px" }}>{p.name}</h3>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 4, margin: "12px 0 24px" }}>
                    <span style={{ fontSize: 42, fontWeight: 900, letterSpacing: "-.02em" }}>{fCLP(p.price)}</span>
                    <span style={{ fontSize: 14, color: C.mute }}>/mes + IVA</span>
                  </div>
                  <ul style={{ listStyle: "none", padding: 0, margin: "0 0 28px" }}>
                    {p.features.map((f, j) => (
                      <li key={j} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", fontSize: 14, color: C.mid }}>
                        <span style={{ color: C.green, fontWeight: 700, fontSize: 16, flexShrink: 0 }}>&#10003;</span> {f}
                      </li>
                    ))}
                  </ul>
                  <button onClick={() => go(`/checkout?plan=${p.key}`)} className="l-btn" style={{
                    width: "100%", padding: "13px 0", borderRadius: 10, fontSize: 14, fontWeight: 700,
                    background: p.popular ? `linear-gradient(135deg, ${C.accent}, ${C.violet})` : "transparent",
                    color: p.popular ? "#fff" : C.accent,
                    border: p.popular ? "none" : `1.5px solid ${C.accent}`, cursor: "pointer",
                    boxShadow: p.popular ? `0 4px 14px ${C.accent}30` : "none",
                  }}>Elegir plan</button>
                </div>
              </RevealSection>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ FAQ ═══ */}
      <FAQSection />

      {/* ═══ 6. CONTACTO ═══ */}
      <section id="contacto" style={{ padding: "100px 24px", background: "#F7F7F8" }}>
        <div style={{ maxWidth: 680, margin: "0 auto" }}>
          <RevealSection>
            <SectionTitle tag="Contacto" title="¿Tienes preguntas? Conversemos" subtitle="Nuestro equipo te responde en menos de 24 horas." />
          </RevealSection>
          <RevealSection delay={100}>
            {formStatus === "sent" ? (
              <div style={{ textAlign: "center", padding: "48px 24px", borderRadius: 20, background: C.greenBg, border: "1px solid #A7F3D0" }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>&#10004;&#65039;</div>
                <h3 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>Mensaje enviado</h3>
                <p style={{ fontSize: 15, color: C.mid, margin: "0 0 20px" }}>Te responderemos a la brevedad.</p>
                <button onClick={() => setFormStatus("idle")} className="l-btn" style={{ padding: "10px 24px", borderRadius: 10, fontSize: 14, fontWeight: 600, background: C.accent, color: "#fff", border: "none", cursor: "pointer" }}>Enviar otro</button>
              </div>
            ) : (
              <form onSubmit={handleContact} style={{
                background: C.white, borderRadius: 20, padding: "36px 32px",
                border: `1px solid ${C.border}`, boxShadow: "0 4px 20px rgba(0,0,0,.04)",
              }}>
                <div className="contact-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                  <div>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Nombre *</label>
                    <input className="l-input" required placeholder="Tu nombre" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} style={inputStyle} />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Email *</label>
                    <input className="l-input" required type="email" placeholder="tu@email.com" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} style={inputStyle} />
                  </div>
                </div>
                <div className="contact-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                  <div>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Teléfono</label>
                    <input className="l-input" placeholder="+56 9 1234 5678" value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })} style={inputStyle} />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Negocio</label>
                    <input className="l-input" placeholder="Nombre de tu negocio" value={formData.business} onChange={(e) => setFormData({ ...formData, business: e.target.value })} style={inputStyle} />
                  </div>
                </div>
                <div style={{ marginBottom: 20 }}>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Mensaje *</label>
                  <textarea className="l-input" required placeholder="Cuéntanos qué necesitas..." value={formData.message} onChange={(e) => setFormData({ ...formData, message: e.target.value })} rows={4} style={{ ...inputStyle, resize: "vertical", minHeight: 100 }} />
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
        padding: "80px 24px", background: `linear-gradient(135deg, ${C.text} 0%, #27272A 100%)`,
        textAlign: "center", position: "relative", overflow: "hidden",
      }}>
        <div style={{ position: "absolute", inset: 0, backgroundImage: `radial-gradient(circle at 30% 50%, ${C.accent}12 0%, transparent 50%)` }} />
        <div style={{ maxWidth: 600, margin: "0 auto", position: "relative" }}>
          <h2 style={{ fontSize: "clamp(26px, 4vw, 40px)", fontWeight: 900, color: "#fff", margin: "0 0 12px" }}>Deja de adivinar. Empieza a decidir con datos.</h2>
          <p style={{ fontSize: 16, color: "rgba(255,255,255,.6)", margin: "0 0 32px" }}>Elige tu plan y configura tu negocio en 5 minutos.</p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <button onClick={() => go("/#precios")} className="l-btn" style={{
              padding: "16px 40px", fontSize: 17, fontWeight: 800,
              background: `linear-gradient(135deg, ${C.accent}, ${C.violet})`,
              color: "#fff", border: "none", borderRadius: 12, cursor: "pointer",
              boxShadow: `0 4px 20px ${C.accent}50`,
            }}>Ver planes</button>
            <a href="#contacto" className="l-btn" style={{
              padding: "16px 40px", fontSize: 17, fontWeight: 600,
              background: "transparent", color: "#fff", border: "1px solid rgba(255,255,255,.3)",
              borderRadius: 12, cursor: "pointer", textDecoration: "none",
            }}>Contactar ventas</a>
          </div>
        </div>
      </section>

      {/* ═══ FOOTER ═══ */}
      <footer style={{ padding: "40px 24px", background: C.text, borderTop: "1px solid #27272A" }}>
        <div className="footer-inner" style={{ maxWidth: 1140, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <LogoIcon size={28} />
            <span style={{ fontSize: 14, fontWeight: 700, color: "rgba(255,255,255,.8)" }}>Pulstock</span>
          </div>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            {[["#problema","Problema"],["#como-funciona","Cómo funciona"],["#beneficios","Beneficios"],["#negocios","Tu negocio"],["#precios","Precios"],["#faq","FAQ"],["#contacto","Contacto"]].map(([href,label]) => (
              <a key={href} href={href} style={{ fontSize: 13, color: "rgba(255,255,255,.5)", textDecoration: "none" }}>{label}</a>
            ))}
          </div>
          <p style={{ fontSize: 12, color: "rgba(255,255,255,.3)" }}>&copy; 2026 Pulstock. Todos los derechos reservados.</p>
        </div>
      </footer>
    </div>
  );
}
