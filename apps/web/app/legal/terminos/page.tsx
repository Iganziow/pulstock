import type { Metadata } from "next";
import { DocumentoLegal } from "@/components/legal/DocumentoLegal";
import { TERMINOS } from "@/lib/legal/documentos";

export const metadata: Metadata = {
  title: "Términos de Servicio | Pulstock",
  description:
    "Las reglas del servicio Pulstock: qué incluye, qué cuesta, de quién son los datos y hasta dónde responde Pulstock.",
};

export default function TerminosPage() {
  return <DocumentoLegal doc={TERMINOS} />;
}
