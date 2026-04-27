"use client";
import { useEffect, useState } from "react";

export function useIsMobile() {
  const [m, setM] = useState(false);
  useEffect(() => {
    const fn = () => setM(window.innerWidth < 768);
    fn();
    window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, []);
  return m;
}

/**
 * Tablet horizontal (iPad acostado, 1024x768): es desktop pero el espacio
 * útil después del sidebar se queda chico. Útil para auto-colapsar la
 * sidebar y para grids que necesitan menos columnas en este ancho.
 */
export function useIsTablet() {
  const [t, setT] = useState(false);
  useEffect(() => {
    const fn = () => {
      const w = window.innerWidth;
      // tablet horizontal = entre mobile y desktop con sidebar cómodo.
      setT(w >= 768 && w < 1100);
    };
    fn();
    window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, []);
  return t;
}

/**
 * Hook unificado con los 3 breakpoints de la app — preferido sobre
 * llamar useIsMobile + useIsTablet por separado (un solo listener,
 * un solo render por resize).
 *
 *   isMobile   < 768px   → teléfono (Mario, dueño de cafetería)
 *   isTablet   768-1099  → tablet o ventana chica de desktop
 *   isDesktop  ≥ 1100px  → laptop/monitor con sidebar cómodo
 *
 * Uso típico:
 *   const { isMobile, isTablet } = useBreakpoint();
 *   const cols = isMobile ? "1fr" : isTablet ? "1fr 1fr" : "repeat(4, 1fr)";
 */
export function useBreakpoint() {
  const [bp, setBp] = useState({ isMobile: false, isTablet: false, isDesktop: true });
  useEffect(() => {
    const fn = () => {
      const w = window.innerWidth;
      setBp({
        isMobile: w < 768,
        isTablet: w >= 768 && w < 1100,
        isDesktop: w >= 1100,
      });
    };
    fn();
    window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, []);
  return bp;
}
