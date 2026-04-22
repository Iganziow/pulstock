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
