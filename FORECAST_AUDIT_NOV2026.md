# Revisión completa del forecast — 8 de noviembre de 2026

Pedido: revisar el modelo y todos los algoritmos, buscar técnicas afuera, verificar que los
modelos trabajen bien, buscar bugs en los flujos y atacar el porqué de las métricas.
Todo lo de abajo está **medido sobre la copia de producción del 8-nov** (volcado 04:20 UTC,
base local `ej_1108`), salvo donde dice "lectura de código". Los hallazgos de código los
levantó un agente revisor de solo lectura (cazador #3); los cuatro de mayor impacto los
verifiqué leyendo las líneas citadas.

## 1. Dónde está el error, en números

Ventana 11-oct a 7-nov, lo publicado la víspera (h=1) contra la demanda efectiva, sin
días de quiebre.

### 1.1 Por algoritmo (quién publica qué)

| algoritmo × patrón | productos | % del volumen | WAPE | sesgo |
|---|---|---|---|---|
| ingredient_derived · smooth | 12 | 47,4 | 68 | −12 |
| seasonal_naive · smooth | 2 (Leche entera, Café) | 41,0 | 78 | +12 |
| adaptive_ma · smooth | 2 | 3,4 | 50 | +21 |
| theta · intermittent | 10 | 2,1 | 196 | +107 |
| theta · smooth | 3 | 2,0 | 98 | −12 |
| tsb · intermittent | 21 | 1,3 | 121 | −10 |
| resto (croston, ets, category_prior, …) | ~150 | <1 c/u | 120–4.000 | — |

Dos algoritmos llevan el 88% del volumen: el derivado de receta y `seasonal_naive`.

### 1.2 El núcleo no tiene forma semanal

Para los 8 productos grandes (jul–nov, días abiertos): correlación de un día con el mismo
día de la semana anterior entre −0,14 y +0,23; test F entre días de semana (8 semanas)
entre 0,1 y 1,8 (sin estructura). La demanda del núcleo es **ruido alrededor de un
nivel**. Cualquier modelo que intente "forma" (copiar el martes pasado, factores por día)
pierde contra el nivel:

| regla h=1 (núcleo 8) | WAPE | sesgo |
|---|---|---|
| publicado por el motor | 74 | +2 |
| mismo día semana anterior (= seasonal_naive) | 81 | +4 |
| promedio 7 días | 59 | +3 |
| promedio 28 días | 56 | +7 |
| mediana 28 días | 50 | −10 |
| nivel 28 × índice por día de semana | 61 | +15 |

Misma conclusión que el 21-sep ([punteria-vs-promedio]) y que la sombra: la **mezcla con
el nivel de 28 días** (brazo 2) da en bloques de 7 días **17,0 % contra 42,8 %** de
producción en el núcleo (2 bloques, 31-oct a 7-nov). Es la palanca grande y ya existe.

### 1.3 Un solo día raro cuesta 14 puntos al producto más grande

El martes 27-oct el local operó al 23 % de su mediana (5 boletas) y no vendió leche.
`seasonal_naive` lo tomó como día pleno: puntuó "predije 1.690, real 0" y el martes 3-nov
**publicó 0** (copió ese cero) contra 1.490 reales. Esos dos días son 13,9 de los 67,5
puntos de WAPE de la Leche entera en 30 días. Con la mezcla el agujero sería del 25 %
en vez del 100 %, pero sigue ahí.

### 1.4 La cola es 6 productos y una vara equivocada

208 productos de cola, 8 % del volumen, 84 % de sus mediciones diarias son "real = 0".
Medida por **semanas** (lo que importa para comprar) el error cae de 114 % a 62 %
(promedio de 28 días: 59 %). El 50 % del error semanal lo hacen 6 productos:

| producto | algoritmo | real 4 sem | publicado | causa |
|---|---|---|---|---|
| Salsa chocolate | derivado | 435 | 623 | padres con media histórica (B3) |
| Jamón granel | derivado | 540 | 571 | forma; con mezcla baja |
| Helado mango | category_prior → croston | 1 | 199 | prior inflado (B2) + sin apagado |
| Cacao | derivado | 290 | 410 | padres adaptive_ma (B3) |
| Preparado chai | tsb | 150 | 157 | ráfagas |
| Syrup vainilla | tsb | 220 | 225 | ráfagas |

Un "techo de cordura" (no publicar más de 3× el nivel de 28 días) casi no mueve la cola
(113,6 → 110,4): el problema no es el tamaño de la publicación sino publicar algo distinto
de cero para productos muertos, y medir ráfagas día a día.

## 2. Bugs (el código no hace lo que dice) — verificados

**B1. La vara que gobierna el kept-path ignora los días con venta cero.**
`recalibrate_confidence.py:124-134` filtra `qty_actual__gt=0` al sumar |error|. Un día
"predije 3, vendí 0" no existe para la medición. Resultado medido (30 días): theta 137 % →
58 %, croston_sba 179 % → 81 %, tsb 129 % → 71 %, adaptive_ma 65 % → 44 %. Ese número
recortado es `_wape_vigente`, la vara con que el kept-path decide si el fresco gana al
titular (`services.py:1794-1809`), la del swap directo/derivado y la de la etiqueta de
confianza. Un titular intermitente que sobre-predice queda protegido. **Alta.**

**B2. El prior de categoría promedia por día con fila, no por día del período.**
`compute_category_profiles.py:150-156` (`total/day_count`, y solo existen filas con
actividad) y `category_prior.py:29-32`. Helados: perfil 2,0/día contra 0,10 real; Syrup
21,4 contra 2,5; además mezcla gramos, unidades y ml en la misma categoría. Helado mango
(3 filas de 1 g) recibió `avg_daily = 0,3·1 + 0,7·43,5 = 30,75` y publicó 29–67 g/día.
category_prior en 30 días: 662 predichas contra 8 reales. **Media.**

**B3. `adaptive_ma` publica la media histórica por día de semana; decay y ventana no
hacen nada.** `adaptive_moving_average.py:15-57`: `dow_factor = media_histórica(día)/avg`
y la predicción es `avg × factor`: el `avg` se cancela. El grid decay×ventana compara
números idénticos. El nivel solo apaga (si la ventana suma 0) o enciende. Helado pistacho
publica 346 g / 16 viernes = 24,5 g cada viernes desde julio, con 2 g vendidos en 2
semanas y 10,8 kg en stock; `demand_stopped` no actúa porque cualquier venta > 0 corta la
racha, sin mirar la magnitud. Importa más por los **padres de los derivados**: 63 % de la
Leche deslactosada, 57 % del Cacao y 23 % del Café tolva se arman con padres adaptive_ma.
Ojo: "arreglar el nivel" ya se midió y empeora (19-oct); lo que hay que medir es acotar la
ventana de la media por día (N semanas) y un `demand_stopped` por magnitud. **Media-alta.**

**B4. Vender la última unidad marca quiebre.** `aggregate_daily_sales.py:406-409`:
`closing <= 0 and (opening > 0 or received > 0)`. Leche entera 2-nov: 990 ml vendidos,
cierre 0, marcado quiebre → fuera de medición, sesgo y calibración. 60 días: 14 días, 11
productos, 1,4 % del volumen. **Baja.**

**B5.** `generate_suggestions` lee SaleLine sin filtrar VOID ni consumo interno
(`services.py:2761-2769`). Solo sugerencias. **Baja.**

## 3. Defectos de diseño (hace lo que dice y eso hunde la métrica)

**D1. `seasonal_naive` tiene memoria de una observación y lleva el 41 % del volumen.**
`_ultimo_mismo_dia` devuelve el valor si la fecha está en la serie, y la serie viene
rellena con ceros: un día abierto sin venta de ese producto se copia tal cual (§1.3).
Promediar las últimas 4 ocurrencias del mismo día baja la Leche entera de 68 a 48 (el
nivel plano da 46). **Alta.**

**D2. Un día semi-operado cuenta como día pleno.** `_fechas_operadas` = "vendió algo".
En 120 días: 5 sábados al 4–38 % de la mediana y el martes 27-oct al 23 %. Entran como
ceros a casi todas las series y se puntúan contra la predicción completa. **Media.**

**D3. El backtest es el doble de optimista que la realidad y el kept-path compara ambos
como si fueran la misma vara.** Backtest: 8 pliegues × 7 días sobre la serie limpia.
`wape_real`: h=1 sobre demanda cruda. Medido: adaptive_ma 45 vs 87, seasonal_naive 40 vs
91, theta 39 vs 88; en tsb/croston al revés (142 vs 78). La decisión kept/fresh mide qué
vara le tocó a cada lado, no calidad. 86 de 207 modelos activos tienen más de 30 días.
**Media.**

**D4. Piso 0,5 del factor de sesgo.** 72 modelos con factor, **35 en el piso** con razón
de totales ≈ 0 (productos que no vendieron nada en 28 días y se publican a la mitad de un
nivel fósil). El brazo 3 (sesgo compuesto, piso 0,3) ataca la composición; falta el
apagado por magnitud. **Media.**

**D5. Con un día cerrado, de los 11 algoritmos solo 2 tienen forma semanal**
(Holt-Winters devuelve None, ETS sin estacionalidad). Pero §1.2 dice que la forma no
existe en el núcleo, así que esto importa menos de lo que parece. **Baja.**

Dudas abiertas (sin veredicto): doble imputación en `_fill_gaps` de ETS; `_collapse_guard`
incluye el cero de hoy; el factor de sesgo no filtra por algoritmo al cambiar el titular;
`month_factors` se calcula y nunca se publica; `stats["improved"]` cuenta re-selecciones
aunque gane el mismo algoritmo; `save_forecasts` y `recalibrate_confidence` corren dos
veces por noche.

## 4. Lo que dice la literatura (y qué aplica acá)

- **Métodos simples compiten a nivel SKU.** En la M5, el 92,5 % de los equipos no le ganó
  al benchmark simple, y Kolassa insiste en comparar contra benchmarks baratos antes que
  en ML. Coincide con §1.2: el nivel de 28 días le gana al motor.
- **Combinar con pesos fijos es robusto** ("forecast combination puzzle": el promedio
  simple le gana a los pesos optimizados). La mezcla 25/75 es exactamente eso; no conviene
  aprender el peso por producto.
- **TSB es el método recomendado cuando la demanda puede apagarse** (obsolescencia): es el
  caso de los helados fuera de temporada. Hoy los lleva adaptive_ma con media histórica.
- **Agregación temporal (ADIDA, Nikolopoulos; iMAPA, Kourentzes)** para intermitentes:
  pronosticar por semanas y repartir. §1.4 lo confirma: la cola medida por semanas pasa
  de 114 % a 62 %.
- **Newsvendor / cuantiles para perecibles** (Huber et al. 2019, panadería alemana;
  estudio turco con regresión cuantil −6 a −8 % de costo): la compra es un cuantil, no un
  punto. Ya lo medimos en local (−64 a −75 % de costo en perecibles).
- **Chronos-2**: sin evidencia publicada en demanda intermitente; nuestro backtest dice
  que solo ayuda en el tramo medio al 50 %.
- **Detección de cambio de nivel** (Killick/PELT, SES adaptativo): la debilidad vista el
  4 y 5-nov (la mezcla tarda en bajar cuando el local cae) tiene literatura; es la
  siguiente pregunta después de desplegar la mezcla.

Fuentes: Kolassa (IJF 2022), Makridakis et al. M5, Qian et al. "On the forecast
combination puzzle" (Econometrics 2019), Nikolopoulos et al. ADIDA (JORS 2011),
Petropoulos/Kourentzes/Nikolopoulos (IJPE 2016), Huber et al. (EJOR 2019), Nixtla
statsforecast (ADIDA/IMAPA/TSB/CrostonOptimized), tsintermittent (R), Chronos-2 (arXiv
2510.15821).

## 5. Qué hacer, en orden

Hay dos lugares en la sombra. La secuencia:

1. **Brazo 3 (sesgo compuesto) reemplaza al brazo 1** esta semana: el sábado incierto ya
   está respondido (gana poco, siempre) y sigue medido dentro del brazo 2.
2. **14-nov: decidir la mezcla.** Si los bloques del núcleo siguen bajo 25 %, se despliega.
   Es la mayor ganancia disponible (42,8 → 17,0) y reduce 4× el daño de D1 y B3.
3. **Brazo "medición honesta" (B1 + D3 + B4 + D2):** quitar `qty_actual__gt=0`, que el
   kept-path compare la misma vara en los dos lados (backtest h=1 sobre serie cruda, o
   wape_real para ambos), quiebre solo si la venta fue claramente baja, y "operó" = al
   menos 30 % de la mediana del local. Cambia qué modelo gana cada noche: obligatorio en
   sombra, 14 noches.
4. **Brazo "ruido": `seasonal_naive` con mediana de las últimas 4 ocurrencias (D1),
   ventana acotada para la media por día de `adaptive_ma` (B3), `demand_stopped` por
   magnitud, prior de categoría por día del período y por familia de unidad (B2).**
5. **Producto, no modelo:** medir y mostrar la cola por semanas; la sugerencia de compra
   como cuantil (newsvendor) con el dato "perecible" por producto; Chronos-2 al 50 % en el
   tramo medio cuando haya un lugar libre.
6. **Higiene sin sombra:** B5, `month_factors` muerto, `improved` del log, las dos
   corridas dobles por noche.

Lo que NO conviene repetir (ya medido): tocar ventanas del nivel, nivel × día de semana,
familia × participación, forma semanal del local, "arreglar" el nivel de adaptive_ma,
techo de antigüedad, feriados por configuración, techo de cordura 2–3× el nivel.
