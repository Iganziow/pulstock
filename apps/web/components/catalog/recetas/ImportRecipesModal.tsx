"use client";

import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";

interface ImportRecipesModalProps {
  showImport: boolean;
  importing: boolean;
  importFile: File | null;
  importResult: any;
  importErr: string | null;
  setImportFile: (f: File | null) => void;
  setImportResult: (r: any) => void;
  setImportErr: (e: string | null) => void;
  setShowImport: (v: boolean) => void;
  downloadSample: () => void;
  runImport: () => void;
}

export function ImportRecipesModal({
  showImport, importing, importFile, importResult, importErr,
  setImportFile, setImportResult, setImportErr, setShowImport,
  downloadSample, runImport,
}: ImportRecipesModalProps) {
  if (!showImport) return null;

  return (
    <div className="bd-in" onClick={() => !importing && setShowImport(false)}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div className="m-in" onClick={e => e.stopPropagation()}
        style={{ background: C.surface, borderRadius: C.rMd, width: 600, maxWidth: "100%", boxShadow: C.shLg, overflow: "hidden" }}>

        {/* Header */}
        <div style={{ padding: "18px 22px", borderBottom: `1px solid ${C.border}` }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>Importar recetas (CSV)</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 2 }}>Carga masiva de recetas: cada fila vincula un producto con un ingrediente</div>
        </div>

        {/* Body */}
        <div style={{ padding: "20px 22px", display: "grid", gap: 14 }}>
          {importErr && (
            <div style={{ padding: "10px 14px", background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, fontSize: 13, color: "#DC2626", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>{importErr}</span>
              <button onClick={() => setImportErr(null)} style={{ background: "none", border: "none", color: "#DC2626", cursor: "pointer", fontSize: 16, padding: 0 }}>&#x2715;</button>
            </div>
          )}

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button className="xb" onClick={downloadSample}
              style={{ background: "none", border: `1px solid ${C.accent}`, color: C.accent, borderRadius: 6,
                padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Descargar ejemplo Excel
            </button>
            <span style={{ fontSize: 11, color: C.mute }}>Con ejemplos de pizza, sandwich y cafe</span>
          </div>

          <div style={{ display: "grid", gap: 5 }}>
            <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>Archivo CSV</label>
            <input type="file" accept=".csv,text/csv"
              onChange={e => { setImportFile(e.target.files?.[0] ?? null); setImportResult(null); }}
              style={{ padding: "9px 12px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, cursor: "pointer" }}
              disabled={importing}
            />
            <div style={{ fontSize: 11, color: C.mute }}>Columnas: product_sku, product_name, ingredient_sku, ingredient_name, qty</div>
          </div>

          {importResult && (
            <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" }}>
              <div style={{ padding: "11px 16px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 13 }}>Resultado</div>
              <div style={{ padding: "14px 18px", display: "flex", gap: 28 }}>
                {[
                  { l: "Creadas", v: importResult.created, c: C.green },
                  { l: "Actualizadas", v: importResult.updated, c: C.accent },
                ].map(s => (
                  <div key={s.l} style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 26, fontWeight: 900, color: s.c, letterSpacing: "-0.04em" }}>{s.v}</div>
                    <div style={{ fontSize: 10.5, color: C.mute, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em" }}>{s.l}</div>
                  </div>
                ))}
              </div>
              {importResult.errors?.length > 0 && (
                <div style={{ borderTop: `1px solid ${C.border}` }}>
                  <div style={{ padding: "9px 16px", fontWeight: 600, fontSize: 12, color: "#DC2626", background: "#FEF2F2" }}>
                    Errores ({importResult.errors.length})
                  </div>
                  <div style={{ maxHeight: 200, overflowY: "auto" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "64px 1fr", fontSize: 11.5, fontWeight: 700, color: C.mute, padding: "7px 16px", background: C.bg, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      <div>Fila</div><div>Error</div>
                    </div>
                    {importResult.errors.map((x: any, idx: number) => (
                      <div key={idx} style={{ display: "grid", gridTemplateColumns: "64px 1fr", padding: "7px 16px", borderBottom: `1px solid ${C.border}`, fontSize: 12 }}>
                        <span style={{ fontFamily: "'JetBrains Mono', monospace", color: C.mute }}>{x.line ?? "-"}</span>
                        <span style={{ color: "#DC2626" }}>{x.error}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "14px 22px", borderTop: `1px solid ${C.border}`, display: "flex", justifyContent: "flex-end", gap: 8, background: C.bg }}>
          <Btn variant="secondary" onClick={() => !importing && setShowImport(false)} disabled={importing}>Cerrar</Btn>
          <Btn variant="primary" onClick={runImport} disabled={importing || !importFile}>
            {importing ? <><Spinner/>Importando\u2026</> : "Importar recetas"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
