# UX_AUDIT.md — Auditoría de experiencia de usuario y arquitectura de información

> 18-jul-2026. 4 auditores (caja/ventas, reportes, configuración/navegación, transversal).
> Complementa MODULES_AUDIT.md (backend). Todo con archivo:línea verificado.
> Diagnóstico global: base de componentes decente pero adopción desigual — "la app se siente
> escrita por 3 personas que nunca acordaron un estándar". Las pantallas insignia (dashboard,
> forecast, mesas) están pulidas; el resto reinventa patrones localmente.

## 1. Hallazgos mayores (los "cómo no lo vimos antes")

| # | Hallazgo | Evidencia | Fix |
|---|---|---|---|
| U1 | **La campana de notificaciones existe solo en código muerto.** `Topbar.tsx` (con bell + dropdown + polling de /core/notifications/) nunca se importa; el topbar real vive en `layout.tsx` y no la tiene → todo el tab "Alertas" de settings no tiene salida visible | layout.tsx:498-625 vs Topbar.tsx:250-325 | Portar el bloque al layout (bajo) |
| U2 | **"Mi cuenta" atrapada tras menú owner-only**: cajero/manager llegan por el avatar a una página de config de negocio que no pueden usar, solo para cambiar su contraseña | settings/page.tsx:119 + layout.tsx:134 | Ruta propia /dashboard/perfil para todos |
| U3 | **Bottom nav móvil sin Mesas ni Caja** — las 2 tareas del garzón en celular a 2 taps; Stock (que no usa) a 1 | layout.tsx:137-142 | Inicio·POS·Mesas·Caja·Más |
| U4 | **Sidebar.tsx y Topbar.tsx = código muerto divergente** (riesgo "edité el archivo equivocado", ya ocurrió según comentarios) | layout.tsx:105-117 | Borrarlos |
| U5 | **4 reportes con export listo (backend Excel/PDF + config) sin cablear** — solo ABC lo muestra | falta `<ExportButtons>` en sales-summary/losses/stock-valued/audit-trail | Copiar patrón de abc-analysis:130 |
| U6 | **2 pills del índice de reportes rotos** (leen campos con nombre equivocado — "$ hoy" y stock valorizado nunca aparecen) | reports/page.tsx:227,230 | 2 líneas |
| U7 | **La ficha de venta no muestra cajero ni garzón** (el dato viaja en la respuesta) ni el motivo de anulación (write-only) | DetailPanel.tsx:436-443, [id]/page.tsx:294-306 | Renderizar lo que ya llega |
| U8 | **Botones Editar/Anular visibles para cajeros** → 403 frustrante al guardar (sin gate de rol en front) | DetailPanel.tsx:80-87 etc. | Ocultar por rol |
| U9 | **Scrollbar 5px casi invisible en PC** (queja explícita de Mario) y sin estilo Firefox | useGlobalStyles.ts:31-34 | 10-12px + scrollbar-width/color |
| U10 | **Estado vacío del catálogo = mensaje de developer** ("revisa que tu usuario tenga tenant asignado") en LA pantalla de activación | catalog/page.tsx:836-845 | EmptyState con CTA "Crear producto" |

## 2. Caja (tab por tab)

- "Movimientos ↗" es un Link que saca de la sección (las otras 3 son tabs reales) — inconsistencia confirmada (page.tsx:274-285).
- Historial: **sin filtros, búsqueda ni export** (CajaHistory.tsx). Propinas: **sin resumen por persona** (hay que filtrar garzón por garzón); el botón "Retirar propinas" vive en el tab equivocado (Arqueo activo).
- Apertura: no preselecciona la única caja ("-- Selecciona --" con 1 caja). Cierre: no ciego (ya B-caja) y se puede cerrar con faltante **sin motivo obligatorio**. Refresh manual reemplaza la vista por spinner (el auto-refresh de 30s es suave — usar ese mismo path). Cualquier rol puede crear cajas (backend IsAuthenticated).

## 3. Ventas (modificaciones)

Qué se puede modificar hoy: editar pagos (IsManager), editar propina (IsManager), anular (IsManager + motivo + audit). NO existe: cambiar garzón/cliente, editar líneas (bloqueado por diseño).
- **Paradoja anti-fraude**: cantidades blindadas pero editar pagos/propina es silencioso — sin motivo ni log_audit ni rastro visible (sales/views.py:511-608; conecta con B7).
- Dos fichas de venta distintas (panel lateral vs página [id]) con datos inconsistentes; la página muestra "Bodega #3 / Store #1" (IDs crudos). Export en 2 pasos poco obvios; backdrop del modal descarta la edición sin confirmar.

## 4. Reportes (uno por uno)

Índice dice "8" pero 1 es link a Forecast; enlaza 7 de 8 páginas (transfer-suggestion-sheet huérfana de navegación, con estética dev: Warehouse ID numérico, labels en inglés, endpoint impreso).
- Veredictos: útiles = sales-summary, ABC (el mejor, único con export), inventory-health (score 0-100), toma física (la hoja imprimible es lo mejor del set), audit-trail. Mejorables = losses (backend filtra por motivo/bodega, UI no lo expone), stock-valued (**trunca a 100 filas/bodega en silencio**, page.tsx:96).
- Huérfanos backend (top-products/profitability/dead-stock): **NO exponer** — redundantes con ABC e inventory-health; borrar o dejar como API.
- Transversal: sin drill-down en ninguno (filas no clickeables, #ref no navega), sin filtro de bodega expuesto, filtros no persisten en URL, sin fila de totales en varias tablas.

## 5. Configuración — propuesta de reorganización

ANTES: 9 tabs planos. DESPUÉS:
- **Mi cuenta → /dashboard/perfil** (todos los roles, desde el avatar)
- **Negocio** = Empresa + Boleta + Tiendas · **Equipo** = Usuarios · **Dispositivos** = Impresoras + Estaciones fusionadas (ocultar Estaciones si ≤1 impresora — es el concepto más confuso; el propio tab trae instructivo de 5 pasos porque no se entiende solo) · **Cuenta y Plan** = Plan + Alertas
- Detalles: falta business_type editable (B19) y horarios del local; Alertas sin umbrales ni destinatarios; roles con etiquetas confusas ("Dueño/Gerente" vs "Administrador"=manager) y sin matriz de permisos; contraseña sin medidor de fortaleza y sin pedir la actual.

## 6. Navegación

- Sidebar bien agrupado en general. Mover **Ofertas** de "Ventas" a "Productos" (es catalog_write, gestión de precios).
- Huérfanas/duplicadas: /dashboard/propinas (duplica el tab de Caja — decidir una), inventory/stock/adjust y /moves (solo por URL), índice /dashboard/inventory semi-huérfano. Icono de Precios equivocado (usa $ de sales).
- Headers de sección pinneados a ítems → el agrupamiento se desplaza raro según rol (Ofertas queda bajo "Productos" para INVENTORY).

## 7. Transversal (patrones)

| Dimensión | Veredicto | Clave |
|---|---|---|
| Estados vacíos | Disparejo | Dashboard/forecast excelentes; catálogo (U10) y ventas ("cambia los filtros" a quien nunca vendió) mal |
| Carga | Disparejo | 3 patrones: Skeleton (5 págs) / spinner / texto+tabla en blanco (prices) |
| Errores | Disparejo | `humanizeError` existe y traduce ~30 patrones… pero caja/movimientos, propinas y categorías usan `alert(e.message)` crudo |
| Confirmaciones | Disparejo (grave) | `window.confirm()` nativo en 10 call-sites incluido el garzón en celular (OrderPanel:213,217,524) |
| Toasts | Disparejo | `flash()` copy-pasteado 5+ veces con timings 3000/4000/4500 y shapes distintos |
| Formularios | Ausente | Sin validación por campo, sin aria-invalid; todo botón-disabled + error de backend |
| Formato | Disparejo | formatCLP compartido (16 archivos) pero 23 archivos con copias locales (¡que sí redondean, el compartido no!); 4 formatos de fecha distintos; sin formatDate compartido |
| Móvil | Mayormente bien | useIsMobile en 38 archivos; flash de layout desktop en primer render; targets 28-30px (<44 WCAG) |
| A11y | Disparejo | Modal con Escape ✅; Toggle es div sin teclado; filas clickeables no son botones |

## 8. Componentes compartidos propuestos (entran a components/ui/)

1. **`<ConfirmDialog>` + useConfirm()** — migrar los 10 confirm() nativos (basado en el Modal existente; los modales de anular-venta y borrar-producto son el patrón bueno).
2. **`<EmptyState>`** (variant zero|filtered) — migrar ~8 bloques; referencia visual: el de forecast.
3. **`useToast()` + ToastHost** en el layout — mata los 5 flash() y los alert().
4. **`<StatusBadge>` único** (hay ≥4 copias) + `formatDate/formatDateTime` en lib/format.ts (paso 1 del futuro DataTable).

## 9. Plan por olas

**Ola 1 — quick wins visibles (2-4 días):** U6 pills rotos · U5 cablear 4 exports · U9 scrollbar ·
U7 cajero/garzón/motivo en ficha de venta · U8 gate de rol en botones · preselección de caja única ·
U3 bottom nav con Mesas/Caja · U10 EmptyState del catálogo · icono Precios.

**Ola 2 — consistencia (1-2 semanas):** ConfirmDialog + EmptyState + useToast + StatusBadge/formatDate
compartidos con migración; U1 campana al topbar real; U4 borrar código muerto + huérfanas (propinas
standalone, adjust/moves); tab Movimientos como tab real; filtros+export en Historial de caja; resumen
de propinas por garzón; motivo obligatorio al cerrar con descuadre.

**Ola 3 — arquitectura de información (2-3 semanas):** /dashboard/perfil + Configuración en 4 grupos +
fusión Impresoras/Estaciones; unificar las 2 fichas de venta; drill-down en reportes + filtros de bodega
+ persistencia en URL; auditoría visible de ediciones de pago/propina (con B7 backend); matriz de permisos
en Usuarios; validación por campo en formularios clave.
