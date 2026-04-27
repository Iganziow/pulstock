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
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#D4D4D8;border-radius:99px}
::-webkit-scrollbar-thumb:hover{background:#A1A1AA}
@keyframes spin{to{transform:rotate(360deg)}}
.qty-input-no-spin::-webkit-inner-spin-button,.qty-input-no-spin::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
.qty-input-no-spin{-moz-appearance:textfield}
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
