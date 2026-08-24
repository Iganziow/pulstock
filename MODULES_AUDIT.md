# MODULES_AUDIT.md — Auditoría módulo a módulo vs técnicas establecidas

> 17-jul-2026. 6 auditores de código (read-only) evaluaron cada módulo contra los estándares de la
> industria (Odoo/ERPNext, Square/Toast/Fudo, Apicbase/meez, prácticas de cash management).
> Complementa `SAAS_RESEARCH.md` (investigación externa) — esto es el mapeo AL CÓDIGO, con archivo:línea.
> Convención: ✅ tenemos · 🟡 parcial · ❌ falta.

---

## 0. Bugs y placebos encontrados (arreglos quirúrgicos, alta confianza)

| # | Módulo | Bug | Evidencia | Esfuerzo |
|---|---|---|---|---|
| B1 | Compras | Filtro de fechas placebo: backend lee `from`/`to`, frontend manda `date_from`/`date_to` — los botones Hoy/7d/30d no filtran | purchases/views.py:266,270 vs purchases/page.tsx:100 | Trivial |
| B2 | Compras | `_find_best_supplier` filtra `status in ["CONFIRMED","RECEIVED"]` — estados que JAMÁS existieron → lookup de lead time es no-op, el motor corre 100% con defaults | forecast/services.py:2175 | 1 línea |
| B3 | Ventas | Motivo de anulación descartado: el front lo exige y envía, el backend nunca lee `request.data["reason"]` | sales/views.py:349-508 vs sales/[id]/page.tsx:136 | Trivial |
| B4 | Ventas | "Nota de venta" del POS es placebo: `payload.note` no existe en serializer ni modelo | pos/page.tsx:277 | Trivial |
| B5 | POS | `idemKey` no se persiste en el CartDraft → recarga tras timeout = clave nueva = posible venta duplicada | pos/page.tsx:218-222 | Trivial |
| B6 | Inventario | Kardex: saldo acumulado se REINICIA en página 2+ (offset ignora filas previas); CSV sin columnas de costo | inventory/views.py:1002-1015, kardex/page.tsx:58-79 | Bajo |
| B7 | Caja | `SaleEditPayments` cambia método de pago retroactivo SIN `log_audit` — única escritura sensible sin rastro | sales/views.py:511-608 | 1 línea |
| B8 | Mesas | Notas de cocina NUNCA llegan a la comanda impresa (payload solo name/qty/total) y el picker móvil ni permite escribirlas | OrderPanel.tsx:284, AddItemFullscreen.tsx:264 | Bajo |
| B9 | Mesas | Reenviar comanda reimprime TODAS las líneas impagas (sin delta) → doble preparación | OrderPanel.tsx:246-271 | Bajo-medio |
| B10 | Inventario | Clamp de venta sin stock: si el decremento queda en 0 NO se crea move — el consumo desaparece del ledger (pariente de la demanda fantasma) | sales/services.py:463-466, 492-495 | Bajo |
| B11 | Catálogo | `convert_qty` devuelve factor 1 SILENCIOSO si `conversion_factor` es 0/None | catalog/unit_conversion.py:32-33 | Bajo |
| B12 | Catálogo | Lista de Precios muestra margen 100% FALSO en todo producto con receta (usa Product.cost=0, no el costo teórico) | catalog/views.py:1644-1645, 1722-1731 | Medio |
| B13 | Mesas | `cancelled_by` no existe en OpenOrderLine; motivo obligatorio solo en front; tables no llama log_audit | tables/models.py:105-107, views.py:565-588 | Bajo |
| B14 | Catálogo | Desactivar un ingrediente usado en recetas activas: la receta sigue vendiendo pero re-guardarla se vuelve imposible (callejón sin salida) | catalog/views.py:1482 | Bajo |
| B15 | Compras | Form de compra parte con costo $0 y postear a $0 diluye el PPP en silencio; sin prefill del último costo | new/page.tsx:57, purchases/views.py:360 | Bajo |

| B16 | Dashboard | `dashboard/views.py` (302 líneas, versión "rica" del summary) es HUÉRFANO: `urls.py` importa la versión de `__init__.py` — dos implementaciones del mismo endpoint divergiendo | dashboard/urls.py:4 | Decidir: activar o borrar |
| B17 | Reportes | `top-products`, `profitability` y `dead-stock` son views backend completas SIN página en el frontend (sus export configs en ExportButtons son inalcanzables); `transfer-suggestion-sheet` tiene página pero no está en el índice de reportes | reports/urls.py vs reports/page.tsx:71-123 | Bajo (crear páginas o linkear) |
| B18 | Stock | El listado de stock no muestra cobertura en días ni cruza con el forecast — `days_to_stockout` solo vive en la página de forecast; mínimos estáticos y forecast son dos mundos separados | inventory/stock/page.tsx (sin columna) | Medio |

**Extra:** PurchaseInvoice/PurchaseInvoiceLine = código muerto; no hay edición de Purchase DRAFT;
ProductSearch rama barcode no filtra `deleted_at`. **Corrección de nota histórica:** el filtro
`risk` del forecast YA NO es placebo — arreglado 18/05/26 (forecast/views.py:85-88).

## 1. Mesas (tables/)

**Sólido:** idempotencia doble (add-lines + checkout) para WiFi inestable; cobro parcial intra-línea "1 de 2"
(ni Fudo básico lo tiene); propinas SaleTip completas; promos server-side; plano de salón.

| Técnica | Estado | Nota |
|---|---|---|
| Split bill | 🟡 | Por ítems + intra-línea ✅; falta seat/comensal y N boletas (cubre ~90% del caso real) |
| Transferencia de mesa / unir / cambiar garzón | ❌ | No hay endpoints; bajo-medio esfuerzo (re-apuntar FKs con lock) — "nos cambiamos de mesa" es diario |
| ATP virtual ("quedan ~2") | 🟡 | Motor `compute_virtual_stock_map` existe y testeado; falta endpoint + badge en picker; hoy el garzón se entera al cobrar (plato ya servido) |
| Auto-86 | ❌ | Depende del anterior; badge "Agotado" + override manager |
| Notas de cocina | 🟡 | Modelo/API ✅; NO se imprimen (B8) |
| Coursing/fire | ❌ | No prioritario para cafetería |
| Deltas post-comanda | ❌ | B9; diseño: `sent_to_kitchen_at` por línea, imprimir solo nuevas + ticket "ANULADO: X" |
| Maker-checker anulaciones | 🟡 | Venta cobrada exige manager ✅; cancelar línea comandada lo hace cualquiera |
| Propinas | ✅ | Completo; falta solo reparto automático |
| Auditoría | 🟡 | added_by/paid_by ✅; falta cancelled_by (B13) |

**Top 3:** (1) delta de comanda + nota impresa + nota en móvil (cierra B8+B9, bajo esfuerzo, alto impacto);
(2) ATP virtual + auto-86 en el picker; (3) transferencia de mesa + cancelled_by/log_audit.

## 2. Caja (caja/)

**Sólido:** snapshot inmutable de cierre; absorción determinística de ventas huérfanas; propinas por método
con retiro dedicado; fórmula de cuadre correcta y bien testeada (~50 tests); multi-caja en modelo.

| Práctica | Estado | Nota |
|---|---|---|
| Conteo ciego | ❌ | El modal MUESTRA el esperado antes de contar + diferencia en vivo (anti-patrón #1). Fix = UI + flag por tenant/rol; backend ya calcula server-side |
| Over/short primera clase | 🟡 | Se persiste por sesión ✅; CERO reporte de tendencia por cajero (faltantes chicos repetidos invisibles) |
| Drops (retiros parciales) | 🟡 | Existen con categoría/autor/confirmación; sin conteo al momento ni segmentación del descuadre |
| Denominaciones | ❌ | Solo montos totales |
| Fórmula de cuadre | ✅ | Sólida (excluye voids, internos, discrimina propinas legacy/Fase-A) |
| Cuadre de tarjetas vs voucher | ❌ | Sin campos para total del terminal Transbank — el rito diario chileno queda fuera. Fix: 2 columnas + paso en modal |
| Eventos auditados | 🟡 | Apertura/cierre en modelo ✅; B7 (EditPayments sin audit) |
| Reporte X/Z | 🟡 | Existen de facto en pantalla; nada imprimible/exportable |
| Multi-caja | 🟡 | Modelo sí; la venta se engancha a la PRIMERA sesión abierta del store, no a la caja del cajero |
| Propinas efectivo | ✅ | Mejor que Fudo |

**Top 3:** (1) conteo ciego (flag `blind_close`, puro frontend); (2) cuadre de tarjetas al cierre;
(3) reporte de tendencia over/short por cajero + fix B7.

## 3. Inventario (inventory/)

**Sólido:** ledger append-only real (cero endpoints de edición, reversas por contra-movimiento);
transferencias atómicas con PPP en destino; invariante stock_value vigilado; motivos de merma tipificados.

| Punto | Estado | Nota |
|---|---|---|
| Shortfall del clamp | ❌ | B10 — diseño: campo `qty_short` en StockMove, crear move aunque decremento=0 |
| Auditoría ledger vs caché | ❌ | No existe `on_hand == Σ moves`; command `audit_stock_ledger` ~80 líneas (molde recalc_stock_value), nightly con alerta |
| Inmutabilidad | ✅ | Formal de facto |
| Costo 0 entradas | 🟡 | Warning solo si el avg RESULTANTE queda 0; costo 0 explícito diluye en silencio |
| Toma física | 🟡 | No persiste sesión, no aplica ajustes (producto por producto a mano), el contador VE la columna Sistema. Diseño: StockCount/StockCountLine + aplicar ADJ en transacción + umbral $ con aprobación + flag ciego |
| Transferencias | ✅ | Sin "en tránsito" (aceptable) |
| UoM en compras | ❌ | Ver Compras |
| Kardex valorizado | 🟡 | B6 + saldo solo en cantidad; contador chileno espera valorizado |
| Mermas | 🟡 | Motivos OK; faltan categorías finas + reporte por motivo |
| Available virtual | 🟡 | Producible por receta ✅; "on_hand − comandas abiertas" no existe (ver Mesas ATP) |

**Top 3:** (1) qty_short del clamp; (2) command audit_stock_ledger nightly; (3) toma física persistente
con aprobación y conteo ciego.

## 4. Catálogo y recetas (catalog/)

**Sólido:** expansión recursiva con ciclos/profundidad/locks; costeo recursivo con la MISMA conversión que
stock; sub-recetas ✅; combos reutilizan Recipe; soft-delete con SKU reutilizable; warnings heurísticos
post-bug-115 en el editor.

| Punto | Estado | Nota |
|---|---|---|
| Modificadores | ❌ | Brecha #1. Diseño: ModifierGroup/ModifierOption con price_delta + ingredient/qty_delta (receta delta inyectada al agg ANTES de expand_recipes). F1 price_delta+comanda (2-3 días); F2 recipe_delta (2-4 sem). Colapsa los 13 capuccinos en 1 producto |
| Yield % (merma prep.) | ❌ | Campo en RecipeLine + 2 líneas en recipes.py + input en editor (1-2 días) |
| Sub-recetas | ✅ | Siempre virtual (sin producción por lotes — no urge) |
| Linter de recetas | 🟡 | Hay validaciones estructurales; FALTA cota de sanidad: qty=115 pasaría HOY sin aviso. Diseño lint_recipe con 6 reglas (R2 outlier-vs-mediana atrapaba el bug real; R1 costo>precio; R3 consumo>stock; R4 costo cero; R5 conversión degenerada; R6 delta 3× al editar) + 422 salvo force + barrido semanal |
| Food cost % visible | 🟡 | B12 — solo se calcula al vender; PriceList con costo teórico recursivo + alerta "margen de X cayó a 12% porque la carne subió 18%" (el reverse FK ya existe) |
| UoM | 🟡 | B11 + caso legacy factor 1 con solo warning en logs |
| Barcode GS1 pesables | ❌ | Punto de enchufe mapeado (parse_scanned_code en ProductLookup); no urgente |
| Categorías | ✅ | Menores: unique global de nombre, sin orden manual para grid POS |
| Precios/happy hour | ❌ | Promotion solo ventana única datetime; falta recurrencia día-semana + franja (2-3 días sobre Promotion) |
| Ciclo de vida | 🟡 | B14 |

**Top 3:** (1) linter de recetas; (2) food cost % en catálogo + alerta de margen; (3) modificadores F1→F2.

## 5. POS / Ventas (sales/)

**Sólido:** create_sale único compartido con mesas (sin lógica duplicada); idempotencia constraint DB +
early-return; void simétrico por StockMoves reales; cost snapshot con fallback; exclusión de promos del
baseline del forecast BIEN hecha (promo_qty separado + peso 0.6 + pseudo-stockout días 100% promo).

| Punto | Estado | Nota |
|---|---|---|
| Descuento por línea | 🟡 | Existe SIN control: cualquier CASHIER descuenta sin tope y edita unit_price libre; sin motivo. Diseño: discount_reason + tope % por rol + PIN manager (endpoint authorize-action con token efímero) |
| Happy hour | ❌ | Ver Catálogo #9 |
| Devoluciones parciales | ❌ | Solo void total. Diseño SaleRefund/SaleRefundLine espejo de create_sale, reversa proporcional de moves; PREREQUISITO de nota de crédito DTE |
| Anulación autorizada | 🟡 | IsManager ✅ + audit ✅; B3 (reason descartado); sin PIN; sin límite temporal |
| Demanda censurada | 🟡 | Hora existe (created_at indexado), NADIE la consume; diseño: sellout_hour en DailySales + escalar demanda por horas-hasta-quiebre + reporte ventas-por-hora (heatmap, estándar Fudo/Toast, hoy no existe) |
| Promos y baseline | ✅ | Matiz: descuentos MANUALES no marcan promo y contaminan levemente |
| Hooks boleta DTE | — | Insertar post-payment/pre-impresión; Tenant ya tiene rut/dirección; nota de crédito requiere devoluciones |
| Un solo camino venta | ✅ | Mesas no pasa descuentos al checkout (gap menor) |
| Cliente | ❌ | No existe modelo Customer (necesario para boleta con RUT, cuenta corriente, fidelización) |
| Offline groundwork | 🟡 | Carrito en localStorage + retry idempotente ✅; B5 |

**Top 3:** (1) devoluciones parciales; (2) control de descuentos con PIN (+B3+B4+B5 en el mismo sprint);
(3) señal horaria de quiebre + ventas por hora.

## 6. Compras (purchases/)

**Sólido:** posteo atómico con PPP/locks/invariante; void con precheck; idempotencia; audit.
**Estructural:** es un registro de facturas, no procurement — no existe "orden" separada de "recepción".

| Punto | Estado | Nota |
|---|---|---|
| Filtro fechas | ❌ | B1 confirmado |
| Recepción parcial | ❌ | received_qty + estados PARTIAL/SENT + endpoint receive reutilizando el bloque de PurchasePost |
| Estados del ciclo | 🟡 | Solo DRAFT/POSTED/VOID; B2 (bug fósil) |
| Lead time por proveedor | 🟡 | **Supplier es un modelo huérfano: sin API, sin admin, sin página** — imposible cargar proveedores; min_order_amount y order_frequency_days son dead fields; match por nombre exacto contra CharField libre. El motor YA consume lead_time — falta que existan datos |
| Historial de precios | ❌ | Datos en PurchaseLine (indexado); falta endpoint + prefill último costo (B15) + alerta alza >X% |
| Pack/UoM compra | ❌ | "Caja de 12 L" se digita a mano; conversión existe en catalog y compras no la usa |
| Sugerencia → OC | 🟡 | Funciona hasta crear DRAFT ✅; costo $0 en producto nuevo, agrupa por bodega (no proveedor), sin navegación ni envío |
| Costo 0 | ❌ | B15 |
| Landed costs | ❌ | tax_amount no se prorratea; falta campo flete + prorrateo por valor |
| OC por WhatsApp | ❌ | ~1 día (link wa.me con OC en texto plano) — cierra la última milla del pipeline |

**Top 3:** (1) proveedores operables + fix B2 + agrupar sugerencias por proveedor con delivery_days →
desbloquea la política (R,S); (2) historial de precios + prefill + alerta de alza (+B15); (3) envío
WhatsApp de la OC, luego recepción parcial.

## 7. Reportes (reports/)

**Inventario actual:** 12 views backend (stock-valued, transfer-suggestion-sheet, losses, sales-summary,
top-products, profitability, dead-stock, count-sheet, inventory-diff, audit-trail, abc-analysis,
inventory-health) + 9 exports (4 Excel, 5 PDF). Frontend: 9 páginas; el índice linkea 8.

**Sólido:** mermas CON desglose por motivo (`by_reason`, reports/services.py:289) ✅; exports respetan
filtros (fix reciente) ✅; y — mejor de lo esperado — **entrega proactiva por email YA existe y está
agendada en beat**: `send_weekly_abc_report` (lunes 8am, HTML al OWNER) y `send_low_stock_alerts`
(diario 7:30am) en reports/tasks.py e inventory/tasks.py (settings.py:521,526). *Pendiente verificar
que efectivamente lleguen en prod (sin dead-man's switch nadie lo sabe — conecta con healthchecks).*

| Punto | Estado | Nota |
|---|---|---|
| Menu engineering / PMix | ❌ | No existe. PERO top-products + profitability (huérfanos, B17) son el 70% de la materia prima: cruzarlos en una matriz popularidad × margen con cuadrantes = página nueva sobre datos ya calculados |
| Ventas por hora (heatmap) | ❌ | Cero `TruncHour` en el repo — ningún reporte horario. Estándar Fudo/Toast; el diseño quedó en la auditoría de POS (§5) |
| Por garzón (margen) | ❌ | Cero referencias a waiter en reports/dashboard — no hay reporte de performance por garzón pese a que Sale.waiter existe |
| Por canal (mostrador/mesas/llevar) | ❌ | Los reportes solo filtran VENTA vs interno; el canal no es dimensión |
| AvT (teórico vs real) | ❌ | No existe; inventory-diff (toma física) es una pieza; falta el cruce recetas×ventas vs consumo real valorizado por ingrediente |
| Mermas por motivo | ✅ | by_reason + filtro |
| KPIs (turns/DSI/GMROI) | ❌ | Stock valorizado sí; rotación/días de inventario/GMROI no se calculan en ningún reporte |
| Comparativos vs período anterior | 🟡 | El dashboard trae variaciones día-a-día; los reportes no comparan contra período equivalente |
| Calidad técnica | 🟡 | Fixes recientes OK; B17 (3 reportes huérfanos + export configs muertos) |
| Email proactivo | ✅ | ABC semanal + low-stock diario agendados; falta el "resumen semanal del negocio" (ventas/margen/mermas) que la investigación de retención recomienda |

**Top 3:** (1) página Menu Engineering reutilizando top-products+profitability (B17 de paso);
(2) reporte AvT por ingrediente (la brecha competitiva #1 de reportes);
(3) ventas por hora + por garzón (los otros 2 reportes que los dueños piden).

## 8. Stock / alertas / dashboard

**Sólido:** min_stock editable en catálogo y visible en dashboard + inventory-health; alerta email diaria
de stock bajo agendada ✅; filtro risk del forecast FUNCIONA (arreglado 18/05, nota vieja obsoleta);
página de sugerencias con KPI de valor en riesgo.

| Punto | Estado | Nota |
|---|---|---|
| Mínimos configurables | 🟡 | Product.min_stock global (no por bodega), editable producto a producto en catálogo; SIN edición masiva (tabla/import) — el ítem #1 de Mario pide cargar decenas de mínimos |
| Alertas stock bajo | 🟡 | Email diario ✅ + dashboard; pero umbral = min_stock estático, sin cruce con forecast |
| Cobertura en días | ❌ | B18 — el listado de stock no muestra días de cobertura; days_to_stockout solo en la página forecast (dos mundos separados). El estándar Walmart: in-stock medido contra forecast, alerta cuando cobertura < lead time |
| Dead stock | 🟡 | View backend existe (dead-stock) pero huérfana (B17); inventory-health cubre parte |
| ABC | ✅ | Página completa con stock virtual por receta; no se usa aún para frecuencia de conteo ni nivel de servicio (conexión futura con conteo cíclico y cuantiles) |
| Dashboard principal | 🟡 | B16 — versión rica huérfana; decidir activar (auditar diferencias primero) o borrar |
| Rotación/GMROI en dashboard | ❌ | No existen |
| Sugerencias UI | 🟡 | Funciona; margin_at_risk (modelo) NO se muestra en la UI; sin navegación a la OC creada |
| Notificaciones | 🟡 | Email diario/semanal ✅; sin centro de alertas en la app (campana); todo lo demás es pull |
| Páginas legacy | ✅ | stock/adjust existe y rutea (nota vieja de 404 no reproducida) |

**Top 3:** (1) edición masiva de mínimos (tabla editable con sugerencia = demanda×(R+L) del forecast
como valor propuesto — une el ítem #1 de Mario con la política (R,S));
(2) columna "cobertura (días)" en el listado de stock usando el forecast (mata B18 y unifica los dos mundos);
(3) resolver B16 (dashboard rico: activar o borrar) + mostrar margin_at_risk en sugerencias.

## 9. Billing (billing/ + checkout) — DINERO

**Sólido:** montos 100% server-side (plan desde DB, webhooks re-validan monto+moneda), locks + guard anti-doble-pago,
Invoice/PaymentAttempt con registro contable completo, PAST_DUE con gracia, emails en español bien producidos.

**🔴 B20 — CRÍTICO: "link de pago creado" se cuenta como cobro exitoso.** `_charge_via_flow` cae a link cuando
no hay tarjeta O cuando el cargo es rechazado, y retorna `success:True` (gateway.py:280-394); `process_renewals`,
`retry_failed_payments`, `expire_trials` y `Reactivate` hacen `if success → activate_period` (tasks.py:91,294,398)
→ **la renovación se marca PAID y regala 30 días sin cobrar**. Verificar en prod:
`Invoice.objects.filter(status="paid").filter(Q(gateway_tx_id="")|Q(gateway_tx_id__startswith="MOCK"))`.
Fix: distinguir `paid:True` de `success:True` + email con el link de pago al cliente.

Otros: **B21** la cancelación miente (dice "acceso hasta fin de período" pero `cancel_subscription` corta en ≤60s
— reclamo garantizado; falta `cancel_at_period_end`); **B22** el email de fallo de pago casi nunca se envía
(`notified_past_due=True` se setea ANTES de enviar, services.py:195); **B23** reintento día 7 = código muerto
(suspende día ~4); **B24** webhook de rechazo duplicado acelera la suspensión (sin guard FAILED, views.py:805);
**B25** sin reconciliación contra Flow — webhook perdido con sesión PENDING = cliente pagó y quedó sin cuenta
("contacta soporte"); `flow_token` se guarda y nunca se lee. Cambio de plan sin prorrateo (regala hasta 1 mes).
Anual: no soportado, ~1-2 días (todo pasa por `activate_period`).

## 10. Onboarding / trial / settings

**Sólido:** trial 1 pantalla que crea todo (tenant+store+bodega+unidades+sub trial 7d), checkout race-safe con
fallback, checklist de activación de 7 pasos server-driven, import CSV/Excel de productos y recetas expuesto,
gestión de usuarios con protección de último owner y anti-escalación.

**B19 — business_type roto 2 veces (2h de fix, crítico para Modo Apertura):** el trial manda valores inexistentes
(`ferreteria`, `minimarket`… vs choices `hardware`, `retail`…) y el backend guarda sin validar; el checkout captura
los valores CORRECTOS pero los descarta al crear el Tenant (siempre "retail") (billing/views.py:907,1244).
**B26** el trial no recibe email de bienvenida (solo el checkout pagado); el aviso "quedan 7 días" dispara la
mañana siguiente al signup. Faltan: pasos "primer conteo" y "primera sugerencia" en el checklist (la definición
real de activación), horarios del local (forecast + demanda censurada), business_type editable por el owner.
Modo Apertura: punto de enchufe exacto = junto a `seed_units_for_tenant` (onboarding/views.py:171-176) +
campo `expected_daily_sales`.

## 11. Printing (printing/ + pulstock-agent)

**Sólido:** claim atómico de jobs, watchdog, pareo one-shot con TTL, tenant scoping correcto, estaciones con
split multi-job testeado, agente resiliente (backoff, logs rotativos, re-pair guiado).

**B28 — el ticket se arma EN EL NAVEGADOR** (escpos.ts/receipt-builder.ts): bloquea la boleta DTE (el timbre
PDF417 exige render server-side; el builder ni soporta QR/raster) y causa el bug de ancho 58/80 (el flujo
auto/estación no conoce el ancho de la impresora destino). Mejora #1: renderer backend (printing/render.py,
1-2 sem) — prerequisito de la boleta. **B27** exactly-once débil: si el `complete` se pierde por red el agente
no reintenta y el watchdog re-encola (hasta 3 reimpresiones); "done" = el spooler aceptó (impresora apagada =
éxito); PrintJob sin idempotency_key; api_key viaja como query param (queda en logs nginx) y re-parear NO la
rota. Sin alerta proactiva de agente offline; sin auto-update del .exe (3 copias del fuente sincronizadas a mano).

## 12. Promotions / prices / transversal frontend

**Sólido:** enforcement server-side, precedencia "mejor precio gana" definida, soft-delete, clonado, badges,
edición masiva de precios bien hecha, CORS/HSTS/headers correctos.

**B29** promo + descuento manual SE ACUMULAN sin marca (el POS hornea el precio promo en unit_price y el manual
va encima; pricing.py:90 solo aplica promo si line_discount==0) — margen invisible + contamina baseline.
**B30** sin historial de cambios de precio (bulk hace UPDATE directo — un MANAGER cambia todo sin rastro).
Sin medición de promos (uplift vs baseline — el dato ya está en SaleLine.promotion; reporte ~1-2 días).
Sin 2x1/NxM (el tipo más pedido). Precedencia de solapamiento sin ningún test. **B36** Sidebar: flash inicial
con todos los links + tab "Plan" (billing) visible para CASHIER. 9 de 10 configs de ExportButtons muertas
(supersede B17). api.ts: sin retry en GETs, 402 no manejado post-refresh ni en apiUpload, 403 genérico.

## 13. Core / stores / superadmin — seguridad

**Sólido:** permisos centralizados y consistentes (54 views HasTenant + 62 con rol), JWT con rotación+blacklist
reales, claims mínimos (role/tenant se leen de DB por request), desactivar usuario invalida al instante,
protección de último owner testeada, ~15 tests adversariales cross-tenant, CORS/HSTS bien.

**B31** purge de tenant = 1 DELETE sin confirmación server-side, sin auditoría persistente, sin test (la lista
manual de 35 modelos puede desincronizarse) — destrucción total de un cliente con 1 request. **B32** access token
duplicado en localStorage (la cookie httpOnly ya existe — el localStorage es el único motivo por el que un XSS
roba sesión) + CSP con `unsafe-inline`/`unsafe-eval` que la neutraliza. **B33** password de staff solo exige
len≥8 ("12345678" pasa) y AdminUserCreate no valida nada; 2FA inexistente. **B34** StoreContextMiddleware +
stores/context.py = código muerto (y el middleware no valida UserStoreAccess — trampa latente si alguien lo usa).
**B35** SuggestionApprove no valida bodega∈store activo (confirmado). Enforcement de tenant: 100% manual, 10
helpers duplicados, ~200 call-sites — plan incremental: helper único (1 día) → TenantScopedManager → test
paramétrico de todas las rutas con tenants A/B. Tests cross-tenant faltan en: purchases, caja, mesas, reports,
printing. BootstrapView auto-crea tenant (legacy, contradice onboarding).

---

## Plan de ejecución sugerido

**Sprint quirúrgico (3-5 días, todo junto):** B1-B15 — quince arreglos triviales/bajos que eliminan
placebos, cierran agujeros de auditoría y el hueco del ledger. Testeables uno a uno, deploy único.

**Luego, por valor/esfuerzo (cada uno 1-2 semanas):**
1. Proveedores operables + pipeline sugerido por proveedor (desbloquea pedido sugerido v2 / mínimos de Mario)
2. Conteo ciego + cuadre tarjetas + tendencia over/short (pack antifraude caja)
3. Delta comanda + notas + ATP/86 en picker (pack operación mesas)
4. Linter de recetas + food cost % + alerta margen (pack recetas)
5. Historial precios compras + recepción parcial + WhatsApp OC (pack compras)
6. Devoluciones parciales + control descuentos + Customer (pack ventas — prerequisitos boleta DTE)
7. Modificadores F1→F2 (el proyecto grande; conecta con helados de Mario)

Todo bajo el protocolo: backup → local + tests → validación prod → go/revert.
