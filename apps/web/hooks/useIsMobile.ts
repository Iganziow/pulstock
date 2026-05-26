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
 * Hook unificado con los breakpoints de la app — preferido sobre
 * llamar useIsMobile + useIsTablet por separado (un solo listener,
 * un solo render por resize).
 *
 *   isMobile         < 768px       → teléfono
 *   isTablet         768-1099px    → tablet o ventana chica de desktop
 *   isCompactDesktop 1100-1365px   → laptop antiguo de Mario (PC compacto)
 *                                    sidebar cómodo pero tablas con muchas
 *                                    columnas pierden ancho para Producto
 *   isDesktop        ≥ 1100px      → laptop/monitor con sidebar cómodo
 *                                    (incluye compactDesktop — flag aparte
 *                                    para detalle de layout fino)
 *
 * Uso típico:
 *   const { isMobile, isTablet } = useBreakpoint();
 *   const cols = isMobile ? "1fr" : isTablet ? "1fr 1fr" : "repeat(4, 1fr)";
 */
export function useBreakpoint() {
  const [bp, setBp] = useState({
    isMobile: false, isTablet: false,
    isCompactDesktop: false, isDesktop: true,
  });
  useEffect(() => {
    const fn = () => {
      const w = window.innerWidth;
      setBp({
        isMobile: w < 768,
        isTablet: w >= 768 && w < 1100,
        // isCompactDesktop: laptop antiguo (Mario lo usa, 1280x720 tipico).
        // Sidebar visible pero ancho util ~1100px → columnas extras (SKU,
        // Barcodes, Costo) le roban espacio al nombre del producto.
        isCompactDesktop: w >= 1100 && w < 1366,
        isDesktop: w >= 1100,
      });
    };
    fn();
    window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, []);
  return bp;
}
