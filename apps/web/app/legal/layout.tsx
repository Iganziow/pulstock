import type { Metadata } from "next";
import { BORRADOR } from "@/lib/legal/documentos";

/**
 * Chrome compartido de los documentos legales públicos.
 *
 * Mientras BORRADOR sea true no se indexan: un contrato en borrador que
 * aparece en Google es un contrato que alguien puede creer vigente.
 */
export const metadata: Metadata = BORRADOR
  ? { robots: { index: false, follow: false } }
  : {};

const CSS = `
.legal-grid { grid-template-columns: minmax(0,1fr); }
.legal-indice a:hover { color: #4F46E5; }
.legal-indice a:focus-visible { outline: 2px solid #4F46E5; outline-offset: 2px; border-radius: 2px; }
@media (min-width: 900px) {
  .legal-grid { grid-template-columns: 220px minmax(0,1fr); gap: 56px !important; }
}
@media (max-width: 899px) {
  .legal-indice { border: 1px solid #E4E4E7; border-radius: 10px; padding: 16px 18px; }
  .legal-indice > div { position: static !important; }
}
@media print {
  .legal-indice, header, footer { display: none !important; }
  section { break-inside: avoid; }
}
`;

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      {children}
    </>
  );
}
