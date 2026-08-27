import type { Metadata } from "next";
import { DocumentoLegal } from "@/components/legal/DocumentoLegal";
import { PRIVACIDAD } from "@/lib/legal/documentos";

export const metadata: Metadata = {
  title: "Política de Privacidad | Pulstock",
  description:
    "Qué datos personales trata Pulstock, con qué base legal, dónde se guardan y cómo se ejercen los derechos sobre ellos.",
};

export default function PrivacidadPage() {
  return <DocumentoLegal doc={PRIVACIDAD} />;
}
