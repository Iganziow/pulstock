"use client";

import { C } from "@/lib/theme";
import { Btn, Spinner, Toggle } from "@/components/ui";
import type { Product, RecipeLine, Recipe, UnitType } from "./types";

interface RecipeEditorProps {
  selectedProduct: Product | null;
  recipe: Recipe | null;
  recipeLoading: boolean;
  recipeLines: RecipeLine[];
  setRecipeLines: React.Dispatch<React.SetStateAction<RecipeLine[]>>;
  recipeNotes: string;
  setRecipeNotes: (v: string) => void;
  recipeActive: boolean;
  setRecipeActive: (v: boolean) => void;
  recipeSaving: boolean;
  recipeErr: string | null;
  setRecipeErr: (v: string | null) => void;
  creatingNew: boolean;
  setCreatingNew: (v: boolean) => void;
  confirmDeleteRecipe: boolean;
  setConfirmDeleteRecipe: (v: boolean) => void;
  ingSearch: string;
  searchIngredients: (q: string) => void;
  ingResults: Product[];
  ingSearching: boolean;
  addIngredient: (p: Product) => void;
  units: UnitType[];
  saveRecipe: () => void;
  deleteRecipe: () => void;
}

export function RecipeEditor({
  selectedProduct, recipe, recipeLoading,
  recipeLines, setRecipeLines,
  recipeNotes, setRecipeNotes,
  recipeActive, setRecipeActive,
  recipeSaving, recipeErr, setRecipeErr,
  creatingNew, setCreatingNew,
  confirmDeleteRecipe, setConfirmDeleteRecipe,
  ingSearch, searchIngredients, ingResults, ingSearching,
  addIngredient, units, saveRecipe, deleteRecipe,
}: RecipeEditorProps) {
  const selectedId = selectedProduct?.id ?? null;
  const showEditor = selectedId !== null && !recipeLoading;
  const hasRecipe = !!recipe;
  const editorVisible = showEditor && (hasRecipe || creatingNew);

  // Bloqueo: si algún ingrediente no tiene unit_obj, NO se puede
  // guardar la receta (riesgo de descuento de stock incorrecto). El
  // backend también rechaza, pero es mejor avisar antes de tipear.
  const hasIngredientWithoutUnit = recipeLines.some(
    l => l.ingredient_unit_obj_id == null || l.ingredient_unit_obj_id <= 0
  );

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, boxShadow: C.sh, minHeight: 460 }}>

      {/* EMPTY STATE: nothing selected */}
      {selectedId === null && (
        <div style={{ padding: "80px 32px", textAlign: "center" }}>
          <div style={{ fontSize: 44, marginBottom: 14 }}>&#x1F4D6;</div>
          <div style={{ fontSize: 15, fontWeight: 700, color: C.text, marginBottom: 6 }}>
            Selecciona un producto
          </div>
          <div style={{ fontSize: 13, color: C.mute }}>
            Haz clic en un producto de la lista izquierda para ver o editar su receta.
          </div>
        </div>
      )}

      {/* LOADING */}
      {selectedId !== null && recipeLoading && (
        <div style={{ padding: "80px 32px", display: "flex", justifyContent: "center", alignItems: "center", gap: 10, color: C.mute }}>
          <Spinner size={20}/><span style={{ fontSize: 14 }}>Cargando receta…</span>
        </div>
      )}

      {/* PANEL CONTENT */}
      {showEditor && (
        <div>
          {/* Panel header */}
          <div style={{
            padding: "16px 22px", borderBottom: `1px solid ${C.border}`,
            display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12,
          }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>{selectedProduct?.name}</div>
              <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>
                {hasRecipe
                  ? `${recipeLines.length} ingrediente${recipeLines.length !== 1 ? "s" : ""} · ${recipeActive ? "Receta activa" : "Receta inactiva"}`
                  : "Sin receta configurada"}
              </div>
            </div>
            {hasRecipe || creatingNew ? (
              <Toggle on={recipeActive} onChange={setRecipeActive}/>
            ) : null}
          </div>

          {/* NO RECIPE + not creating */}
          {!hasRecipe && !creatingNew && (
            <div style={{ padding: "60px 32px", textAlign: "center" }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>&#x1F373;</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                Este producto no tiene receta
              </div>
              <div style={{ fontSize: 13, color: C.mute, marginBottom: 20 }}>
                Crea una receta para definir que ingredientes se descuentan al vender este producto.
              </div>
              <Btn variant="primary" onClick={() => setCreatingNew(true)}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
                Crear receta
              </Btn>
            </div>
          )}

          {/* EDITOR (has recipe OR creating new) */}
          {editorVisible && (
            <div style={{ padding: "20px 22px", display: "grid", gap: 18 }}>

              {/* Error */}
              {recipeErr && (
                <div style={{ padding: "10px 14px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r, fontSize: 13, color: C.red, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>{recipeErr}</span>
                  <button type="button" aria-label="Cerrar" onClick={() => setRecipeErr(null)} style={{ background: "none", border: "none", color: C.red, cursor: "pointer", fontSize: 16, padding: 0 }}>&#x2715;</button>
                </div>
              )}

              {/* Ingredient search */}
              <div style={{ display: "grid", gap: 6 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Agregar ingrediente
                </div>
                <div style={{ position: "relative" }}>
                  <input
                    value={ingSearch}
                    onChange={e => searchIngredients(e.target.value)}
                    placeholder="Buscar producto o ingrediente…"
                    disabled={recipeSaving}
                    style={{
                      width: "100%", padding: "9px 12px",
                      border: `1px solid ${C.borderMd}`, borderRadius: C.r,
                      fontSize: 13, boxSizing: "border-box",
                    }}
                  />
                  {ingSearching && (
                    <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)" }}>
                      <Spinner/>
                    </div>
                  )}
                </div>
                {ingResults.length > 0 && (
                  <div style={{ border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", background: C.surface, boxShadow: C.shMd }}>
                    {ingResults.map(ing => (
                      <button type="button" key={ing.id}
                        onClick={() => addIngredient(ing)}
                        disabled={recipeSaving || recipeLines.some(l => l.ingredient_id === ing.id)}
                        style={{
                          display: "flex", width: "100%", alignItems: "center", justifyContent: "space-between",
                          padding: "9px 14px", background: "none", border: "none", cursor: "pointer",
                          fontSize: 13, textAlign: "left", gap: 12, borderBottom: `1px solid ${C.border}`,
                        }}>
                        <span style={{ fontWeight: 600 }}>{ing.name}</span>
                        <span style={{ fontSize: 11, color: C.mute, fontFamily: C.mono }}>{ing.sku ?? ""} · {ing.unit ?? "UN"}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Ingredient lines */}
              {recipeLines.length > 0 ? (
                <div style={{ display: "grid", gap: 4 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                    Ingredientes
                  </div>
                  <div style={{ border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden" }}>
                    {/* Header */}
                    <div style={{
                      display: "grid", gridTemplateColumns: "1fr 100px 90px 36px",
                      gap: 8, padding: "7px 12px",
                      background: C.bg, borderBottom: `1px solid ${C.border}`,
                      fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.04em",
                    }}>
                      <span>Ingrediente</span>
                      <span style={{ textAlign: "right" }}>Cantidad</span>
                      <span>Unidad</span>
                      <span/>
                    </div>
                    {recipeLines.map((l, i) => {
                      const familyUnits = l.ingredient_unit_family
                        ? units.filter(u => u.family === l.ingredient_unit_family)
                        : [];
                      // Warnings de blindaje (Mario lo pidió):
                      //   Riesgo 1: ingrediente sin unit_obj configurada
                      //     → no se puede convertir, el sistema asume
                      //     unidad raw. Si la receta dice 0,15 y el
                      //     ingrediente es "1 unidad", se descuenta
                      //     0,15 unidades en vez de 0,15 L.
                      //   Riesgo 2: ingrediente con unit_obj de COUNT
                      //     (UN/conteo) en una receta donde claramente
                      //     debería ser MASS o VOLUME (leche, café...).
                      const hasUnitObj = l.ingredient_unit_obj_id != null && l.ingredient_unit_obj_id > 0;
                      const isCountFamily = l.ingredient_unit_family === "COUNT";
                      const showWarning = !hasUnitObj || (isCountFamily && Number(l.qty) > 0 && Number(l.qty) < 1);
                      return (
                      <div key={l.ingredient_id} style={{
                        borderBottom: i < recipeLines.length - 1 ? `1px solid ${C.border}` : "none",
                      }}>
                      <div style={{
                        display: "grid", gridTemplateColumns: "1fr 100px 90px 36px",
                        gap: 8, padding: "9px 12px", alignItems: "center",
                      }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 600 }}>{l.ingredient_name}</div>
                          <div style={{ fontSize: 11, color: C.mute, fontFamily: C.mono }}>
                            {l.ingredient_sku && `${l.ingredient_sku} · `}{l.ingredient_unit ?? "UN"}
                          </div>
                        </div>
                        <input
                          value={l.qty}
                          onChange={e => setRecipeLines(prev => prev.map((x, j) => j === i ? { ...x, qty: e.target.value } : x))}
                          inputMode="decimal"
                          disabled={recipeSaving}
                          style={{
                            padding: "5px 8px", border: `1px solid ${C.borderMd}`,
                            borderRadius: 4, fontSize: 13, textAlign: "right", width: "100%",
                          }}
                        />
                        {familyUnits.length > 1 ? (
                          <select
                            value={l.unit_id ?? ""}
                            onChange={e => {
                              const uid = e.target.value ? Number(e.target.value) : null;
                              const u = units.find(u => u.id === uid);
                              setRecipeLines(prev => prev.map((x, j) => j === i ? { ...x, unit_id: uid, unit_code: u?.code ?? null } : x));
                            }}
                            disabled={recipeSaving}
                            style={{
                              padding: "5px 6px", border: `1px solid ${C.borderMd}`,
                              borderRadius: 4, fontSize: 12, width: "100%", background: C.surface,
                            }}
                          >
                            {familyUnits.map(u => (
                              <option key={u.id} value={u.id}>{u.code}</option>
                            ))}
                          </select>
                        ) : (
                          <span style={{ fontSize: 12, color: C.mute, padding: "5px 6px" }}>
                            {l.unit_code ?? l.ingredient_unit ?? "UN"}
                          </span>
                        )}
                        <button type="button" aria-label="Eliminar" onClick={() => setRecipeLines(prev => prev.filter((_, j) => j !== i))}
                          disabled={recipeSaving}
                          style={{ background: "none", border: "none", cursor: "pointer", color: C.red, fontSize: 18, padding: 4, display: "flex", alignItems: "center", justifyContent: "center" }}>
                          &#x2715;
                        </button>
                      </div>
                      {showWarning && (
                        <div style={{
                          margin: "0 12px 9px", padding: "8px 10px",
                          background: !hasUnitObj ? "#FEF2F2" : "#FFFBEB",
                          border: `1px solid ${!hasUnitObj ? "#FCA5A5" : "#F59E0B"}`,
                          borderRadius: 6,
                          fontSize: 11,
                          color: !hasUnitObj ? "#991B1B" : "#92400E",
                          display: "flex", alignItems: "flex-start", gap: 6,
                        }}>
                          <span style={{ fontSize: 13, flexShrink: 0 }}>{!hasUnitObj ? "🛑" : "⚠️"}</span>
                          <span>
                            {!hasUnitObj ? (
                              <><b>Sin unidad de medida.</b>{" "}
                                Edita el producto <b>{l.ingredient_name}</b> y asigna una unidad
                                (KG, GR, L, ML, UN…) antes de usarlo en recetas. Sin esto,
                                el stock se descuenta de forma incorrecta.
                              </>
                            ) : (
                              <><b>Cantidad fraccionaria en producto contable.</b>{" "}
                                Estás indicando <b>{l.qty}</b> de <b>{l.ingredient_name}</b>{" "}
                                (cargado como <b>{l.ingredient_unit ?? "UN"}</b>).{" "}
                                Si querías por ejemplo gramos o litros, edita el producto y
                                cambia su unidad a una de masa (KG/GR) o volumen (L/ML).
                              </>
                            )}
                          </span>
                        </div>
                      )}
                      </div>
                      );
                    })}
                  </div>
                  <div style={{ fontSize: 11, color: C.mute }}>Cantidades por 1 unidad vendida del producto.</div>
                </div>
              ) : (
                <div style={{ padding: "24px 16px", textAlign: "center", color: C.mute, fontSize: 13, border: `1px dashed ${C.border}`, borderRadius: C.r }}>
                  Busca ingredientes arriba para armar la receta.
                </div>
              )}

              {/* Notes */}
              <div style={{ display: "grid", gap: 5 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Notas internas (opcional)
                </label>
                <input
                  value={recipeNotes}
                  onChange={e => setRecipeNotes(e.target.value)}
                  placeholder="Ej: Usar leche entera, cafe de tueste oscuro…"
                  disabled={recipeSaving}
                  style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 13 }}
                />
              </div>

              {/* Toggle active */}
              <div style={{ padding: "12px 14px", background: C.bg, borderRadius: C.r, display: "flex", alignItems: "center", gap: 10 }}>
                <Toggle on={recipeActive} onChange={setRecipeActive}/>
                <span style={{ fontSize: 13, fontWeight: 600, color: recipeActive ? C.text : C.mid }}>
                  Receta {recipeActive ? "activa" : "inactiva"}
                </span>
                <span style={{ fontSize: 12, color: C.mute }}>
                  {recipeActive
                    ? "— Los ingredientes se descontaran al vender este producto"
                    : "— No se descontaran ingredientes al vender"}
                </span>
              </div>

              {/* Actions */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 4, borderTop: `1px solid ${C.border}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {hasRecipe && !confirmDeleteRecipe && (
                    <Btn variant="danger" onClick={() => setConfirmDeleteRecipe(true)} disabled={recipeSaving}>
                      Eliminar receta
                    </Btn>
                  )}
                  {hasRecipe && confirmDeleteRecipe && (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: C.red }}>¿Eliminar esta receta?</span>
                      <Btn variant="danger" onClick={deleteRecipe} disabled={recipeSaving} size="sm">
                        {recipeSaving ? <><Spinner/>Eliminando…</> : "Si, eliminar"}
                      </Btn>
                      <Btn variant="ghost" onClick={() => setConfirmDeleteRecipe(false)} disabled={recipeSaving} size="sm">
                        Cancelar
                      </Btn>
                    </div>
                  )}
                  {!hasRecipe && creatingNew && (
                    <Btn variant="ghost" onClick={() => { setCreatingNew(false); setRecipeLines([]); searchIngredients(""); setRecipeErr(null); }} disabled={recipeSaving}>
                      Cancelar
                    </Btn>
                  )}
                </div>
                <span title={hasIngredientWithoutUnit ? "Hay ingredientes sin unidad configurada. Editalos antes de guardar." : undefined}>
                  <Btn
                    variant="primary"
                    onClick={saveRecipe}
                    disabled={
                      recipeSaving
                      || recipeLines.filter(l => Number(l.qty) > 0).length === 0
                      || hasIngredientWithoutUnit
                    }
                  >
                    {recipeSaving ? <><Spinner/>Guardando…</> : (hasRecipe ? "Guardar cambios" : "Crear receta")}
                  </Btn>
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
