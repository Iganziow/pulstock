# FORECAST_RESEARCH.md — Ciencia de inventario y práctica industrial aplicable a Pulstock

> Investigación 17-jul-2026 (2 rondas, ~30 fuentes primarias: papers M5/IJF, MIT OCW, Chopra-Meindl,
> King/APICS, Kostenko-Hyndman, RELEX/Blue Yonder/SAP F&R, Amazon Science, caso 7-Eleven, Lokad, Nixtla).
> Complementa `FORECAST_ENGINE.md` (lo que el motor hace hoy) y `FORMULAS.md` (fórmulas de costeo).
> Objetivo: qué adoptar del estado del arte para forecast + sugerencia de compra, priorizado para
> nuestro caso (1 café, ~175 SKUs, 3-12 meses de historia, CPU, compras 1-2×/semana, lead time 1-3 días).

---

## 1. Validación del enfoque actual (competencia M5, Walmart)

- En M5 (42.840 series jerárquicas de Walmart), la ventaja del ML colapsa a **~3% en el nivel
  SKU-tienda intermitente** (vs ~53% en agregados de cadena). Los métodos estadísticos que ya usamos
  (Croston/SBA, Theta, ETS, medias adaptativas) **son competitivos en nuestro nivel**.
  Solo 7,5% de 2.666 equipos batió al suavizamiento exponencial simple.
  → **No migrar a LightGBM/redes para un café.** Fuente: Makridakis et al., IJF 2022
  (sciencedirect S0169207021001874 y S0169207022000577).
- Selección por backtest rolling ✅, `wape_total` como métrica de tasa ✅, forecast de ingredientes
  vía recetas ✅ — coinciden con la práctica industrial.
- **Advertencia estructural** (HAL hal-03421806, validado en 8.000 SKUs reales): mejor accuracy de
  forecast ≠ mejor desempeño de inventario. Todo cambio futuro se valida contra KPIs de inventario
  (fill rate, merma, quiebres), no solo MASE/WAPE.

## 2. Fórmulas de decisión de compra (lo que falta formalizar)

Notación: `d̄` demanda media diaria · `σ_d` desv. est. diaria · `L` lead time (días) ·
`R` días hasta el próximo pedido · `z = Φ⁻¹(CSL)` factor de servicio.

### 2.1 Política (R,S) "order-up-to" — LA política para compras en días fijos
```
S  = d̄ × (R + L) + z × σ_d × √(R + L)          ← nivel objetivo
Q  = S − stock a mano − pedidos en tránsito      ← cantidad a pedir hoy
```
- La exposición es **R + L** (lo pedido hoy cubre hasta que LLEGUE el pedido siguiente).
  Con compras lunes y jueves, R alterna 3 y 4 — usar el R real de cada ciclo.
- Con proveedor impuntual: `σ = √((R+L)·σ_d² + d̄²·σ_LT²)` (solo si demanda y LT independientes).
- Fuente: Chopra & Meindl cap. 12; King, APICS 2011 (web.mit.edu/2.810/www/files/readings/King_SafetyStock.pdf).

### 2.2 Newsvendor — el nivel de servicio óptimo por producto
```
Cu = precio − costo            (margen perdido por quiebre)
Co = costo − valor de rescate  (pérdida por merma; rescate = reuso/descuento, si basura Co = costo)
CSL* = Cu / (Cu + Co)          →  q* = F⁻¹(CSL*)   (cuantil de la demanda del período)
```
- Croissant margen 3× costo y merma total → ratio 0,75 → cubrir el percentil 75.
- El z-score con distribución normal **falla con demanda intermitente** (Lokad): usar el cuantil
  empírico del backtest/serie, no μ+zσ, para intermitentes.
- Métrica para evaluar cuantiles: **pinball loss** (no MASE — el cuantil es sesgado a propósito).
- Fuente: MIT OCW 15.772J Newsvendor; Lokad quantile forecasting; Amazon Science (compra = cuantil P10-P90 según asimetría).

### 2.3 Par level (industria restaurantes) vs par científico
- Industria: `Par = uso promedio entre entregas + 20-30% de colchón` (plano, folclórico).
- Científico: `Par = S` de la política (R,S) — el colchón se adapta a la variabilidad de CADA
  producto. Ofrecer el % plano como fallback, el científico como default.

### 2.4 EOQ — casi NO aplica
El calendario de compra es fijo (R dado) y el pedido es conjunto por proveedor → Q lo determina
(R,S), no el lote económico. Uso residual: decidir si comprar 1 o 2 veces/semana.

### 2.5 Fill rate vs CSL
```
ESC = σ_L × [φ(z) − z·(1−Φ(z))]     (faltante esperado por ciclo)
fill rate = 1 − ESC/Q
```
CSL mide frecuencia de quiebres; fill rate mide volumen servido. Reportar ambos.

## 3. Algoritmos que faltan en el motor

| Técnica | Qué corrige | Fuente |
|---|---|---|
| **TSB** (Teunter-Syntetos-Babai 2011) | Croston/SBA solo actualizan cuando HAY demanda → el helado en invierno nunca decae (el bug estacional de los intermitentes, visto 16-jul). TSB actualiza probabilidad TODOS los días. | nixtlaverse (statsforecast TSB) |
| **Modified SBA** (HAL hal-03421806) | Híbrido SBA→modo TSB cuando el intervalo real excede el estimado. Mejor que SES/Croston/SBA/TSB en sesgo (hasta −80%) en 8.000 SKUs reales. Para lumpy severo SBA > TSB; el modified gana en ambos. | hal.science/hal-03421806 |
| **Clasificación SBC correcta** (Kostenko-Hyndman) | Croston SOLO para smooth; **SBA para intermittent/erratic/lumpy**. Regla fina: SBA si CV² > 2 − 1,5·ADI (cortes aprox: ADI 1,32 / CV² 0,49). Verificar nuestro selector. | robjhyndman.com/papers/idcat.pdf |
| **ADIDA / buckets de reposición** | Pronosticar en buckets = R+L (3-7 días) en vez de diario: menos ceros y es lo que la compra necesita. | orca.cardiff.ac.uk (ADIDA, JORS 2011) |
| **TD-FP para variantes** (13 capuccinos) | Forecast de FAMILIA (serie suave) + desagregar por proporciones pronosticadas. MinT es frágil con series cortas (explosión de covarianza); bottom-up es el PEOR en el agregado. | Estudio SME retail 554 series; otexts.com/fpp3 |
| **Cuantiles como salida** | La decisión de compra necesita P50-P95, no solo la media. Ya guardamos lower/upper_bound — formalizar cuantiles calibrados. | Amazon Science; Lokad |

## 4. Prácticas industriales transferibles (ronda 2)

### Mecánica del pedido sugerido (Walmart / Crunchtime / RELEX)
1. Forecast de venta limpio de one-offs (≈ nuestro `clean_phantom_demand`) →
2. explosión de recetas → consumo proyectado de ingredientes →
3. `sugerido = S(forecast, R+L, cuantil) − stock a mano − en tránsito` →
4. **restar la merma proyectada** (spoilage-aware: lo que vencerá antes de venderse, RELEX/SAP F&R) →
5. redondear a pack del proveedor MOSTRANDO el efecto ("pack de 12 = 9 días de cobertura") →
6. calzar con el día de entrega y el perfil semanal (el pedido del jueves cubre el pico vie-dom).

### Tanpin Kanri (7-Eleven Japón) — el modelo para tienda chica
- El sistema PROPONE, el humano DISPONE (nunca auto-enviar la orden). 7-Eleven delega el pedido
  al empleado que ve al cliente; sus tiendas venden ~US$1.000/día más que competidores automatizados.
- Pantalla de pedido con CONTEXTO: clima de mañana, eventos, ventas recientes del ítem, para que
  el humano formule una hipótesis. Al día siguiente el POS muestra si acertó (loop de aprendizaje).
- Explicabilidad: descomponer cada sugerencia (base + día de semana + clima − stock − merma
  proyectada). Sin explicación, los humanos pisan las sugerencias buenas (lección Amazon SCOT).

### Perecederos
- Nivel de servicio deliberadamente <100% en ultra-frescos ("agotarse el 30% de los días en la
  última hora" es ÓPTIMO, no falla).
- **Demanda censurada**: si el stock llegó a 0, mirar LA HORA de la última venta — se acabó a las
  16:00 = quiebre (demanda real mayor); al cierre = sell-through perfecto. Corregir el aprendizaje.
- Markdown de fin de día (liquidar lo que morirá) recupera margen parcial > merma total.
- Zara: lote chico + corrección frecuente > lote grande + forecast perfecto. Ante duda, pedir menos:
  con reposición en 3 días, corregir al alza es barato; la merma no.

## 5. Clima (el fix estructural del lag estacional)

- **Umbral real del helado: ~15°C** (media 15,6°C en 97 negocios UK), no 25°C. Respuesta no lineal
  con saturación (calor extremo → migra a bebidas frías) → factor por BANDAS, no pendiente lineal.
- Sopa/caliente: −1°C ≈ +2% (Campbell's, décadas de uso). Bebidas frías: +1,6%/°C (UK).
  Taproom Denver: temp máxima explica 64% de la varianza; la LLUVIA resultó mal predictor.
- Receta práctica (RELEX-style sin ML): factor multiplicativo por bandas sobre el baseline usando
  la **anomalía** (pronóstico − normal histórica del mes, para no confundir clima con estacionalidad),
  SOLO en productos con sensibilidad detectada (correlación histórica temp-ventas, umbral R²≥0,3).
  El espresso es inelástico — no tocarlo.
- API: **Open-Meteo** (pronóstico 16 días, histórico ERA5 desde 1940 para calibrar, 10k calls/día
  gratis NO comercial; plan comercial para el SaaS en producción). La objeción de Lokad ("el clima
  rara vez paga") aplica a lead times largos — con decisión a 1-3 días el pronóstico es muy bueno.

## 6. Cold start, promociones, calendario

- **Prior→datos con κ₀ explícito** (normal-normal): peso de datos propios = `n/(n+κ₀)`.
  Con κ₀=14 días: a los 14 días el dato propio pesa 50%, a los 42 pesa 75%. Empirical Bayes estima
  el prior desde la propia categoría (shrinkage `B = σ²/(τ̂²+σ²)`), sin umbrales manuales.
- Heredar del análogo la DEMANDA BASE, pero el patrón semanal del AGREGADO de categoría (RELEX).
- **Promos**: nuestro `promo_qty` separado es la práctica correcta (descomposición base + uplift).
  Falta: EXCLUIR/sub-ponderar los días promo del fit del baseline. Librería de multiplicadores por
  tipo (10% dcto ≈ 1,3×; 2×1 ≈ 3×). Post-promo dip: NO aplicarlo por defecto — en consumo inmediato
  (café) suele no existir (evidencia Duke); medirlo primero.
- **Feriados con 1 observación**: agrupar feriados similares bajo un mismo efecto (de 1 obs → 8-10
  por grupo) + regularizar hacia 0 (patrón Prophet). **Quincena/día de pago**: dummy determinística,
  24 obs/año — estimable con 6 meses.

## 7. Benchmarking competencia (SaaS de inventario food service)

- **El hueco de mercado confirmado: casi nadie tiene forecast propio.** MarketMan NO tiene (usa
  terceros), Supy "coming soon", Crunchtime sí (el referente). Nuestro motor es un diferenciador
  legítimo SI se expone como "pedido sugerido en 1 clic".
- Features más citadas que NOS faltan: **reporte Actual vs Teórico** (varianza por ingrediente,
  "top 15 por $ perdido"; benchmark: <2% bien, 2-3% aceptable, >5% investigar — la métrica reina
  de control de merma/robo y ya tenemos recetas+mermas+conteos), OCR de facturas (xtraCHEF),
  waste log categorizado, **auto-86** (deshabilitar producto en POS cuando el ingrediente crítico
  llega al umbral — Toast), recetas delta por modificador (base + delta por variante).
- KPIs estándar: rotación alimentos 4-8×/mes; GMROI = margen% × turns; DSI por ítem.

## 8. Plan maestro por plazos (pendiente de aprobación)

### Corto plazo (días-2 semanas c/u, bajo esfuerzo, alto impacto)
| # | Qué | Ataca | Base ya desarrollada |
|---|---|---|---|
| C1 | **TSB + modified SBA** como algoritmos + fix selector SBC (SBA fuera de smooth) | Decay estacional de intermitentes | Matemática de referencia en statsforecast (Apache-2.0); ~50 líneas nativas en nuestro framework |
| C2 | **Modo Apertura v1** (contingencia local nuevo): plantilla por business_type (formas normalizadas cross-tenant) + campo onboarding "ventas esperadas" + extender escalera de priors | Local recién abierto sin forecast | La maquinaria de blend n/(n+κ) YA existe en category_prior |
| C3 | **Excluir días promo del fit** del baseline (sub-ponderar) | Baseline contaminado por promos | promo_qty ya se guarda separado |
| C4 | **Dummy de quincena** (día de pago) + **agrupar feriados por tipo** (efecto compartido) | Calendario con poca historia | Holiday model ya existe; quincena = 24 obs/año |

### Mediano plazo (3-6 semanas c/u)
| # | Qué | Ataca | Base ya desarrollada |
|---|---|---|---|
| M1 | **Pedido sugerido v2**: política (R,S) con R real por ciclo + cuantil newsvendor por producto (Cu/Co desde margen/perecibilidad) + spoilage-aware + explicación de cada cantidad + redondeo por pack visible | Mínimos de Mario; corazón del producto | Fórmulas verificadas (stockpyl MIT, Chopra, King); forecast + recetas + stock ya existen |
| M2 | **TD-FP familias de variantes**: forecast por familia + desagregación por proporciones pronosticadas | 13 capuccinos, syrups, sabores | hierarchicalforecast (Apache-2.0) como referencia; NO usar MinT (frágil con series cortas) |
| M3 | **Clima por bandas con anomalía** (pronóstico − normal ERA5), solo productos con sensibilidad detectada | Transición verano↔invierno | Open-Meteo (16 días forecast, histórico desde 1940); umbral helado ~15°C |
| M4 | **Reporte AvT** (actual vs teórico, top-N por $ de varianza) + **demanda censurada** (hora de última venta) | Merma/robo; brecha competitiva #1; quiebres invisibles | Recetas + mermas + conteos + timestamps ya existen |
| M5 | **ADIDA/buckets de reposición**: pronosticar en buckets R+L (3-7 días) para intermitentes | Alinear forecast con la decisión de compra | Paper ADIDA; IMAPA en statsforecast como referencia |
| M6 | **Pantalla de pedido estilo Tanpin Kanri**: contexto (clima, ventas recientes, cobertura) + hipótesis editable + feedback de acierto al día siguiente | Adopción/confianza del usuario; loop de aprendizaje | Caso 7-Eleven; el forecast y accuracy tracking ya existen |

### Largo plazo (2-3+ meses, decisiones de producto)
| # | Qué | Ataca |
|---|---|---|
| L1 | **Sistema de modificadores/variantes** (selector de sabores tipo Fudo) — brecha #1 vs Fudo; destraba helados, agregados, puntos de carne | POS + stock por variante |
| L2 | **Forecast probabilístico completo**: cuantiles calibrados P50/P90 por producto + pinball loss en el backtest + cuantiles empíricos para intermitentes | Toda la cadena forecast→compra |
| L3 | **Lotes con vencimiento (FEFO)**: fecha de vencimiento por recepción + stock utilizable + alerta "formato proveedor > venta en vida útil" + auto-86 + sugerencia de liquidación fin de día | Perecederos de verdad |
| L4 | **Cross-learning multi-tenant** (un modelo global tipo LightGBM sobre todos los tenants) — SOLO cuando Pulstock tenga decenas de locales; en M5 la ventaja a nivel SKU-tienda fue ~3% | Escala futura del SaaS |

### Contingencia local nuevo (Modo Apertura) — línea de tiempo del cliente
```
Día 0:        plantilla business_type × ventas esperadas del dueño (onboarding)
Semana 1-2:   nivel propio (aprende en días) × forma semanal de la plantilla
              w = n/(n+14): día 14 → datos propios pesan 50%
Semana 3-8:   category_prior propio (ya existe) toma el control
Semana 8+:    motor completo (backtest, selección por algoritmo, breaker)
UI:           rampa de confianza visible ("aprendiendo: día 9, confianza 39%")
```

Regla transversal: validar cada cambio contra KPIs de inventario (fill rate, merma, quiebres,
capital), no solo métricas de forecast. Protocolo: backup → local + tests → datos prod → go/revert.
