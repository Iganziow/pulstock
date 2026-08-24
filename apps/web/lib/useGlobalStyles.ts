"use client";
import { useEffect } from "react";

/**
 * Shared CSS injected once across all dashboard pages.
 * Page-specific extras can be passed as `extraCSS`.
 */
const SHARED_CSS = `
*{box-sizing:border-box}
body{font-family:'DM Sans','Helvetica Neue',system-ui,sans-serif}
.prow{transition:background 0.1s ease;cursor:pointer}
.prow:hover{background:#F4F4F5}
.prow:hover .ra{opacity:1!important}
.ra{opacity:0;transition:opacity 0.13s ease}
.xb{transition:all 0.15s cubic-bezier(0.4,0,0.2,1);cursor:pointer}
.xb:hover:not(:disabled){filter:brightness(0.91);transform:translateY(-1px)}
.xb:active:not(:disabled){transform:scale(0.97)}
.xb:disabled{opacity:0.38;cursor:not-allowed;pointer-events:none}
.ib{transition:background 0.11s ease;cursor:pointer}
.ib:hover{background:#F4F4F5!important}
.m-in{animation:mIn 0.22s cubic-bezier(0.34,1.38,0.64,1) both}
@keyframes mIn{from{opacity:0;transform:translateY(14px) scale(0.97)}to{opacity:1;transform:none}}
.bd-in{animation:bdIn 0.17s ease both}
@keyframes bdIn{from{opacity:0}to{opacity:1}}
.sc{transition:all 0.15s ease}
.sc:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,0.09),0 1px 4px rgba(0,0,0,0.04)}
input,select,textarea{font-family:'DM Sans','Helvetica Neue',system-ui,sans-serif;font-size:14px;color:#18181B}
input:focus,select:focus,textarea:focus{outline:2px solid #4F46E5;outline-offset:-1px;border-color:#4F46E5!important}
input::placeholder,textarea::placeholder{color:#A1A1AA}
select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2371717A' stroke-width='2.5'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 11px center;padding-right:34px!important}
html{scrollbar-width:auto;scrollbar-color:#B4B4BB transparent}
::-webkit-scrollbar{width:12px;height:12px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#C4C4CC;border-radius:99px;border:3px solid transparent;background-clip:content-box;min-height:40px}
::-webkit-scrollbar-thumb:hover{background:#8E8E96;background-clip:content-box}
@keyframes spin{to{transform:rotate(360deg)}}
.qty-input-no-spin::-webkit-inner-spin-button,.qty-input-no-spin::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
.qty-input-no-spin{-moz-appearance:textfield}

/* ── Scroll suave ──────────────────────────────────────────────────
   Al saltar a una seccion, volver arriba o abrir un modal largo, el salto
   seco desorienta: no queda claro si la pagina cambio o solo se movio. */
html{scroll-behavior:smooth}

/* Los encabezados pegajosos tapan aquello a lo que se salta. Este margen
   hace que el elemento quede DEBAJO del encabezado y no detras. */
[id]{scroll-margin-top:80px}

/* Las tablas largas no arrastran el scroll de la pagina al llegar al final. */
.tbl-scroll{overscroll-behavior:contain}

/* El anillo de foco solo con teclado. Antes aparecia tambien al hacer clic
   con el mouse, que es ruido visual constante para quien no lo necesita. */
input:focus:not(:focus-visible),select:focus:not(:focus-visible),textarea:focus:not(:focus-visible){outline:none}
button:focus-visible,a:focus-visible,[role="button"]:focus-visible{outline:2px solid #4F46E5;outline-offset:2px;border-radius:4px}

/* ── Respetar a quien pidio menos movimiento ───────────────────────
   La app tenia seis animaciones y ninguna miraba esta preferencia. Para
   alguien con sensibilidad al movimiento --o con vertigo, o simplemente en
   un equipo lento-- cada modal era una molestia. El sistema operativo ya lo
   sabe; solo habia que preguntarle. */
@media (prefers-reduced-motion: reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{
    animation-duration:0.01ms!important;
    animation-iteration-count:1!important;
    transition-duration:0.01ms!important;
    scroll-behavior:auto!important;
  }
  .sc:hover{transform:none}
  .xb:hover:not(:disabled){transform:none}
}
`;

const SHARED_ID = "pulstock-shared-ds";

export function useGlobalStyles(extraCSS?: string) {
  useEffect(() => {
    if (!document.getElementById(SHARED_ID)) {
      const el = document.createElement("style");
      el.id = SHARED_ID;
      el.textContent = SHARED_CSS;
      document.head.appendChild(el);
    }
  }, []);

  useEffect(() => {
    if (!extraCSS) return;
    const extraId = "pulstock-page-ds";
    let el = document.getElementById(extraId) as HTMLStyleElement | null;
    if (el) {
      el.textContent = extraCSS;
    } else {
      el = document.createElement("style");
      el.id = extraId;
      el.textContent = extraCSS;
      document.head.appendChild(el);
    }
    return () => {
      el?.remove();
    };
  }, [extraCSS]);
}
