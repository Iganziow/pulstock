# Revisión completa del forecast — 2 de septiembre de 2026

Revisión de punta a punta del módulo `apps/api/forecast/` y de la capa que lo
muestra al usuario. Se hizo con cinco lecturas paralelas (motor de selección,
algoritmos, `services.py`, pipeline nocturno, API y UI), verificando después
los hallazgos de mayor peso contra producción (solo lectura) o ejecutando el
código localmente.

Cada hallazgo indica su nivel de evidencia:

- **[E]** ejecutado o medido con datos reales de producción.
- **[L]** confirmado leyendo el código, sin ejecutar.
- **[?]** plausible, no confirmado.

Contexto de escala (tenant 1, Marbrava, ventana de 30 días): 4 productos son el
90% de la venta; 188 productos aportan el 10% y se llevan el 98% de las
mediciones. El WAPE del núcleo es 43% (sesgo +13%); el global, 63% (+23%).

---

## 1. Lo que se corrigió en esta revisión (ya commiteado, sin desplegar)

| commit | qué |
|---|---|
| `049ab15` | TSB estaba fuera de la familia protegida de `choose_best`: tenía que ganarle a Croston por 15% aun siendo el mejor. Medido sobre 79 series reales: TSB pasa de 5 a 25 ganadores; `adaptive_ma` baja de 6 a 2. |
| `b1d351e` | `calidad_por_peso()`: la calidad se reporta separando núcleo (Pareto 90%) y cola. El comando nocturno la imprime antes de la alarma. |
| `1be7dd9` | `best_beta` no se propagaba del backtest al pronóstico final: TSB usaba siempre 0,10. |

---

## 2. Confirmado con ejecución o datos [E]

### 2.1 `adaptive_ma` calcula su nivel sin la última semana
`engine/algorithms/adaptive_moving_average.py:32-33, 81, 87`. El grid interno
entrena sobre `daily_series[:-7]` y guarda ese promedio; el pronóstico final
usa ese mismo promedio. Ejecutado: 21 días a 10/día seguidos de 7 días a
**cero** → sigue pronosticando 10,000. 28 días a 10 seguidos de 7 días a 30 →
sigue en 10. El algoritmo va siempre una semana atrasado. Es el algoritmo con
más modelos activos (78) y el de peor sesgo real en la cola (+198%).

### 2.2 `simple_avg` pronostica una venta única como demanda diaria
`engine/algorithms/simple_average.py:18, 40-44`. Es el único candidato cuando
hay entre 7 y 13 días de datos, no tiene tope de valores atípicos y su
backtest devuelve `mae=0`. En producción: Helado piña colada (una venta de 510
el 21-08) pronostica 44/día; Helado chocolate y banana split (170 una vez)
pronostican 14,7/día. En 30 días: 706 unidades predichas contra 0 vendidas.
Esto alimenta las sugerencias de compra.

### 2.3 No existe purga ni política de retención
15.665 filas de `ForecastModel` (196 activas), 25.323 de `Forecast` de las que
19.438 son del pasado y 15.792 pertenecen a modelos inactivos. 139 productos
tienen más de 50 modelos históricos; un ingrediente con derivado genera **dos**
filas por noche (`services.py:1695-1719` y `:2783-2867`, una vive segundos).
El comentario de `coverage.py` que dice "las filas de Forecast se purgan" es
falso: `save_forecasts` borra solo `forecast_date > today`. Cualquier limpieza
futura de modelos debe tener en cuenta que `Forecast.model` es `CASCADE`.

### 2.4 La cobertura de Leche deslactosada era el bug de los mudos
Leche deslactosada (20,7% de la venta), Syrup vainilla y Pan blanco están
medidos exactamente el 31-08 y el 01-09: las dos noches desde el despliegue del
arreglo de los mudos. Los tres son `ingredient_derived`. La cobertura sube sola
noche a noche; no hay nada que investigar. Productos medidos por día: 180 →
181 → 189 → 190.

### 2.5 La recalibración de confianza ignora los días con venta cero
`management/commands/recalibrate_confidence.py:99-105` filtra
`qty_actual__gt=0`. Un modelo que predice 20/día y vende 0 cuatro días a la
semana obtiene "high" si acierta los otros tres. En la cola, el 89% de las
mediciones son contra cero. Discrepa con `calidad_por_peso` y con el `wape_real`
que usa el breaker.

### 2.7 Ocho modelos activos apuntan a productos desactivados
8 de 196 modelos activos (Jugo Natural, Alfajor, Muffin, Twinings, entre
otros) pertenecen a productos con `is_active=False`, invisibles para el
manager por defecto. Se siguen entrenando cada noche.

### 2.8 Las sugerencias de compra piden productos que Mario desactivó
La sugerencia pendiente #177 (03-09, 10 líneas, todas CRITICAL) incluye
Muffin (comprar 3) y Caja galletas/chocolates (comprar 1): ambos con
`is_active=False`, sin receta que los use, última venta a mediados de junio y
stock 0. **60 de las últimas 60 sugerencias incluyeron productos
desactivados** (100 líneas). El razonamiento que ve Mario dice "vendes
alrededor de 1 unidades al día" para una demanda de 0,14.

La cadena, con líneas:
- `train_forecast_models.py:209-223`: elegible = vendió alguna vez en Pulstock
  (sin ventana de tiempo) o es ingrediente. `is_active` del producto no se
  mira, aunque el comentario diga que se desactivan los descontinuados. Un
  producto desactivado que vendió una unidad en junio sigue en el pool.
- `services.py:2085+` (`generate_suggestions`): parte de los modelos activos,
  no de los productos activos. `Product.objects` (manager que oculta
  inactivos) solo se usa para leer `min_stock`.
- `services.py:2384`: el guardián de zombis exime a los "lentos"
  (`avg_daily_raw <= 0.2`). Muffin tiene 0,142 y Caja 0,081: pasan por ahí.
- `services.py:2395-2402`: el tope de 4× el consumo real se salta cuando el
  consumo de 30 días es cero (`if cap_basis > 0`), y luego se fuerza mínimo
  1. Cero consumo, que debería ser la razón más fuerte para no sugerir, es
  justo el caso sin red.

Arreglo propuesto (dos filtros, sin migración): excluir de la elegibilidad
y de las sugerencias a los productos `is_active=False` que no sean
ingredientes de una receta activa. Twinings (73 en stock, última venta en
mayo) y Alfajor caen también.

### 2.9 Stock cero es "crítico" aunque nadie compre el producto
`engine/utils.py:401-402`: `calculate_days_to_stockout` devuelve 0 en cuanto
`current_stock <= 0`, antes de mirar la demanda. Medido el 03-09: de los 14
"críticos" que cuenta el KPI, **8 no vendieron nada en 30 días** (Muffin,
Caja galletas, dos cafés de grano, bombones, Gretel, promo alfajor, "helado
ingrediente"); 4 venden entre 1 y 5 al mes; solo Té (60/mes, stock 0 tras una
entrada el 02-09) y Empanada (18/mes) son quiebres reales. Mario ve "14
críticos" en rojo cada día por 2 que importan: fatiga de alerta. Antes de la
exclusión de recetas, la lista de 63 "críticos" representaba el 0,7% de la
venta. Arreglo de una condición: con stock 0 y pronóstico total ≈ 0 en el
horizonte, devolver `None` (sin demanda no hay quiebre).

### 2.10 Con confianza baja, el quiebre se calcula con un techo absurdo
Chocolate Premium (#5 del negocio, theta, `confidence_label=low`): 560 en
stock, predicción 31/día (18 días de cobertura), pero la alerta dice **5
días**. Con confianza baja `calculate_days_to_stockout(conservative=True)`
descuenta `upper_bound`, que para este modelo es **201,9/día, 6,5 veces la
predicción** (`utils.py:405`). El intervalo empírico de theta sobre una serie
errática (WAPE 112%) produce techos sin relación con la demanda. Efecto: el
producto #5 aparece "en riesgo" con más de dos semanas de stock. Arreglo
propuesto: acotar el techo usado para el quiebre (por ejemplo, a 2× la
predicción) o usar el cuantil del backtest real.

### 2.6 Servidor en UTC
`timedatectl`: `Etc/UTC`. El cron de las 04:30 corre a las 00:30 de Santiago,
así que `date.today()` y `timezone.localdate()` coinciden en la corrida
nocturna. El riesgo es solo al reprocesar a mano entre las 21:00 y las 23:59
de Chile ("ayer" apunta al día equivocado). El pipeline nunca abortó en las 9
corridas con log.

---

## 3. Alta probabilidad por lectura [L]. Cada uno se verifica con una consulta

### 3.1 Todas las series terminan con un cero falso: "hoy" [E]
`services.py:1428-1436` rellena hasta `span_end = today`, pero
`aggregate_daily_sales` solo escribe **ayer** y el pipeline corre de madrugada.
Resultado: `serie[-1] == (hoy, 0)` para todos los productos, todas las noches.
Efectos: la media móvil ponderada le da al último punto el mayor peso (19% con
ventana 7, 11% con 21) → sesgo a la baja sistemático; TSB decae un día extra;
`detect_trend` ve un cero en la última semana ISO y con pocas semanas declara
tendencia a la baja (factor 0,71 a 14 días sobre demanda plana,
`engine/enhancements.py:260-271, 313-326`); `_collapse_guard` lo suma.
Dos lecturas independientes llegaron a lo mismo, y se confirmó con datos el
03-09: `date.today()` del servidor = 2026-09-03, última fecha con `DailySales`
= 2026-09-02, cero filas para el 03. El relleno llega hasta el 03 → cada serie
termina en (2026-09-03, 0). **Pasa a [E].**

### 3.2 Los post-procesos no llegan a la tabla `Forecast` [E]
`services.py:1742-1747`: el fresh path llama `_regen_from_existing` **después**
de `save_forecasts`; el regen re-ejecuta el algoritmo crudo y vuelve a guardar,
pisando lo anterior. Factores mensuales, tendencia, corrección de sesgo,
estacionalidad anual, YoY y elasticidad quedan solo en `model_params`, que
`explain.py:126` le muestra al usuario como aplicados. **Confirmado con datos el
03-09** (Syrup avellana, Croston, `avg_daily` 0,264): las filas son planas en
0,294 de lunes a sábado, iguales en septiembre y en octubre, aunque
`model_params` guarda estacionalidad sep 0,53 / oct 1,44 y sesgo por día de
la semana de ±0,13. Lo único que las mueve es `save_forecasts`: domingos en
0, Fiestas Patrias en 0,029 y una rampa previa. Pasa en fresh y en kept: el
regen corre después de `save_forecasts` en ambos. Consecuencia práctica
descubierta de paso: el regen tampoco pasaba `best_beta`, así que `1be7dd9`
no cambiaba ninguna fila; corregido en el commit siguiente.

Consecuencia de diseño: seis multiplicadores encadenados sin tope global
(mes × tendencia ≤2 × mensual sin tope × YoY ≤1,5 × precio ≤1,5 × feriado ≤5)
que hoy son letra muerta. Hay que decidir si se aplican de verdad (y entonces
pasan por backtest) o se eliminan.

### 3.3 Rama sparse: filas de WMA bajo la etiqueta `category_prior`
`services.py:1755-1758, 1860-1863, 1888-1912`. La serie va **sin relleno de
ceros**; `category_prior` está excluido del re-exec y cae a la media móvil
sobre los últimos 21 registros con venta: un producto con 5 ventas de 1 unidad
en 30 días queda con `avg_daily ≈ 1`, no 0,17. Además `category_prior` fecha
desde la última venta + 1, así que el primer guardado puede reescribir filas
pasadas ya puntuadas y reasignar su dueño.

### 3.4 El centinela `mae >= 998` descarta candidatos legítimos
`engine/selection.py:83` y `:229`, `engine/utils.py:278`. Un ingrediente en
ml o gramos con 2.400/día y 42% de error tiene MAE 1.008 → el candidato se
descarta como si no hubiera corrido. Con 5.000 g/día y 20% de error se
descartan todos → `algorithm="none"`. Afecta a ingredientes de alto volumen
sin modelo derivado.

### 3.5 La corrección de sesgo usa los errores del algoritmo anterior
`services.py:1533-1541` no filtra `ForecastAccuracy` por `algorithm`. Al pasar
de `adaptive_ma` (+198%) a TSB, los errores positivos del primero se le restan
al segundo hasta 0,5 × `avg_daily` por 14 días → oscilación.

### 3.6 Tendencia y sesgo nunca actúan sobre theta, ETS y Holt-Winters
Solo `adaptive_ma`, `moving_avg`, `croston`, `tsb`, `simple_avg` y
`category_prior` escriben `params["avg_daily"]`; `services.py:1528, 1540` lo
leen con default "0" y los ajustes retornan sin hacer nada.

### 3.7 El centinela 900 de `wape_total` excluye folds y premia al que sobre-predice
`engine/utils.py:259, 283`. En un fold con reales `[0,0,1,0,0,0,0]` el modelo
que predice 1,5/día da 950 → fold excluido de su promedio; el que predice 0,3
da 110 → incluido. Se comparan sobre conjuntos de folds distintos.

### 3.8 Estacionalidad mensual sin tope
`engine/enhancements.py:87-94`. Un mes de evento a 200/día contra 11 meses a
10/día deja los otros 11 meses con factor 0,39. La bimodal sí clampa a
[0,1, 4,0]; la mensual no.

### 3.9 El ensemble gana en smooth por un hueco en las métricas
`engine/selection.py:143-154`: `_err` penaliza `tracking_signal`, que el
ensemble no trae (`algorithms/ensemble.py:74-79`) → penalización 0 mientras
sus miembros pagan hasta +15 pp. Gana justo cuando los miembros comparten el
signo del sesgo, que es lo que un promedio no corrige.

### 3.10 Bandas que no contienen la predicción [?] (no observado)
`weighted_moving_average.py:167-176` (intervalo empírico de un solo holdout) y
`croston_bootstrap.py:30-50` (bootstrap sin suavizado ni factor SBA) pueden
dar `lower_bound > qty_predicted`. Afecta `days_to_stockout` conservador.
Medido el 03-09: **0 de 5.689 filas futuras** tienen ese defecto. Posible en
teoría, no ocurre con los datos actuales.

### 3.11 Multiplicadores de feriado: cross-tenant y con contaminación de VOID
`train_forecast_models.py:415` filtra `Holiday` solo por fecha; con dos
tenants el último sobrescribe. `services.py:2143-2151` suma `SaleLine` sin
filtrar anuladas para el tope de seguridad y el gate de `category_prior`.

---

## 4. Lo que ve el usuario [L]

### 4.1 El KPI "Necesitan reposición" cuenta dos veces los críticos [E]
`services.py:234-240`: `at_risk_7d` (≤7 días) incluye a `imminent_3d`
(≤3 días); `app/(dashboard)/dashboard/forecast/page.tsx:217` los suma.
**Medido el 03-09 con datos reales, aplicando la misma exclusión de productos
con receta que hace el backend:** 18 productos con quiebre a 7 días, 14 de
ellos a 3 días (subconjunto confirmado). La pantalla muestra **32**; los
productos distintos son **18**. El subtítulo "14 críticos · 18 en riesgo"
refuerza la suma. El home (`dashboard/views.py:136-137`) usa la semántica
exclusiva y mostraría 18, así que las dos pantallas discrepan. (Una primera
medición sin la exclusión dio 131 contra 68; esas cifras eran incorrectas.)
Arreglo: mostrar `at_risk_7d` y en el subtítulo `at_risk_7d - imminent_3d`
como "en riesgo".

### 4.2 La única "confianza" visible es un contador de días
`page.tsx:150-165` promete "predicciones confiables (día 30)" según días desde
la primera venta. El backend manda `confidence_label`, `confidence_reason`,
`display_wape` y `explanation` (`services.py:739-751`) y nadie los pinta
(`components/forecast/types.ts:37` ni los declara). Tres umbrales distintos en
pantalla: 7, 14 y 30 días.

### 4.3 Sugerencias
Tope duro de 50 sin paginación y N+1 (`services.py:865-870`): con más de 50
históricas, las pendientes antiguas desaparecen. Unidades hardcodeadas
("unidades" para leche en ml, `services.py:2018-2033`). La "sugerencia
estimada" del panel de detalle no aplica cap 4×, zombie, MOQ ni lead time del
generador real → panel y tarjeta pueden dar cantidades distintas.

### 4.4 Matriz de permisos vs API
`core/role_permissions.py:29,38` permite habilitar forecast para cajero e
inventario y el sidebar muestra el enlace; `billing/permissions.py:50-56`
responde 403 a cualquiera bajo manager.

### 4.5 Landing
"Precisión 87%" en la maqueta del dashboard y "40% menos quiebres / 25% menos
sobrestock, basado en implementación real". El sistema no calcula "precisión";
lo más cercano es 1 − WAPE, entre 37% y 57%.

### 4.6 Estados vacío y error a la vez; 46 emojis en la UI de forecast
`page.tsx:254` muestra "necesitamos 2 semanas" sin mirar `err`; dos fetch con
`.catch(() => {})`. Emojis en `page.tsx`, `suggestions/page.tsx`,
`costos/page.tsx`, `DetailPanel`, `Insights`, `SuggestionCard`.

---

## 5. Latente: aparece con 2+ tenants o 2+ locales [L]

- **Un tenant roto deja sin sugerencias a todos.** `train_forecast_models.py:176`
  levanta `CommandError` plano; el pipeline solo continúa ante `FallaParcial`
  (`run_nightly_pipeline.py:116-134`). `FallaParcial` hereda de `CommandError`,
  así que cambiarlo no rompe el test que lo fija.
- **Si `aggregate_daily_sales` falla un día, ese día queda "no operó" para
  siempre** (`track_forecast_accuracy.py:126-130`, `services.py:1104-1106`), sin
  error y sin que `check_forecast_coverage` lo vea.
- **Proceso matado a mitad queda en `running`** y `/health/deep/` lo ve verde
  hasta 26-30 h (`core/heartbeat.py:204-211`, `core/urls.py:133-135`).
- **Sugerencias no acotadas a la tienda activa**; aprobar crea una compra con
  bodega de otra tienda sin validar (`views.py:188-192`).
- **`business_operated_on` es por tenant, no por bodega**: un local cerrado
  suma "predijo X, real 0" para todo su catálogo.
- **`get_ingredient_forecast_boost` recarga todas las recetas por cada producto
  sparse**; `save_forecasts` corre dos veces por producto en fresh y sparse.

---

## 6. Orden recomendado

Nada de esto corresponde hacerlo antes de la entrega salvo lo ya commiteado.
Después:

**Sprint 1, una tarde, sin migraciones, riesgo bajo.** El cero falso de "hoy"
(rellenar hasta ayer). `adaptive_ma` calculando el nivel sobre la serie
completa. `simple_avg` con tope de atípicos o exigiendo al menos dos ventas.
El KPI que suma dos veces. `train_forecast_models` levantando `FallaParcial`.
Cada uno con backtest sobre las 79 series reales ya extraídas
(`scratchpad/series.json` de esta sesión; volver a extraer si se perdió).

**Sprint 2, una semana.** Decidir el destino de los post-procesos: o llegan a
la tabla y pasan por backtest, o se eliminan junto con lo que `explain.py`
muestra. Corrección de sesgo filtrada por algoritmo. Centinela de MAE relativo
al nivel de la serie. Recalibración de confianza incluyendo los ceros. Rama
sparse con relleno de ceros y sin reescribir el pasado.

**Sprint 3.** Retención (con `CASCADE` presente: `SET_NULL` en `Forecast.model`
o borrar solo lo más antiguo que N días y ya puntuado). Multi-tenant y
multi-local (sección 5). Pintar la confianza medida en la UI y retirar las
promesas por calendario. Barrido de emojis.

---

## 7. Qué NO salió mal

**Fiestas Patrias 2026, verificado el 03-09.** El pronóstico del 18 y 19 de
septiembre va a ~0 (×0,11) y coincide con la historia: en 2025 Marbrava
vendió 0 esos dos días. El 20-09-2026 es domingo (cerrado) y va en 0, bien.
El único matiz es la víspera: en 2025 el 17 vendió 141% del promedio de
septiembre y el pronóstico 2026 sube solo 17% los días 16 y 17
(`Holiday.pre_multiplier`, `learned_multiplier=None`: nunca se aprendió del
año anterior porque esa historia está importada como `forecast_only`). Riesgo
acotado de comprar de menos para la víspera.



Aislamiento por tenant en la API: sin hallazgos (`_require` en todas las
vistas, `test_aislamiento_modulos_nuevos.py` lo fija). Idempotencia de
`DailySales`, `ForecastAccuracy` y `Forecast` (upsert). Todos los algoritmos
indexan las tuplas y convierten Decimal correctamente. `patterns.py` clasifica
bien. El pipeline no reporta éxito cuando aborta. Ningún algoritmo registrado
carece de test, aunque ninguno cubre los disparadores de 2.1, 2.2, 3.1 ni 3.2.
