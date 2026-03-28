# Motor de Prediccion de Demanda — Pulstock

## Resumen Ejecutivo

Pulstock integra un motor de prediccion de demanda con inteligencia artificial que analiza el historial de ventas de cada producto, detecta patrones automaticamente y genera predicciones diarias para los proximos 21-60 dias. El sistema selecciona el mejor algoritmo entre 11 candidatos usando backtesting walk-forward, y se auto-corrige cada noche comparando sus predicciones con las ventas reales.

Este motor es el diferenciador principal de Pulstock frente a otros sistemas de inventario del mercado chileno. Ningun competidor directo ofrece prediccion de demanda multi-algoritmo con ajuste automatico por tipo de negocio, estacionalidad bimodal, y modelado de feriados chilenos con multiplicadores por rubro.

---

## Por que es Diferenciador

### 1. Multi-algoritmo con seleccion automatica

Los sistemas de inventario tradicionales usan una formula fija (promedio movil o reorder point estatico). Pulstock compite **11 algoritmos simultaneamente** y elige el que mejor predice para CADA producto individual. Un cafe con leche puede usar Holt-Winters (patron semanal fuerte), mientras que un postre especial usa Croston (demanda intermitente). El sistema decide solo.

### 2. Adaptacion por tipo de negocio

Cada rubro tiene parametros distintos calibrados para su realidad:
- **Cafeteria/Restaurant**: ventana 7 dias (ciclo semanal fuerte), horizonte 21 dias
- **Minimarket**: ventana 14 dias, horizonte 30 dias
- **Ferreteria**: ventana 30 dias (demanda lenta), horizonte 60 dias, estacionalidad de construccion
- **Farmacia**: horizonte 30 dias, stock minimo legal obligatorio
- **Distribuidora**: ventana 21 dias, horizonte 45 dias, lead times largos

### 3. Modelado de feriados chilenos

126 feriados y eventos comerciales pre-configurados (2025-2030) con multiplicadores diferenciados por rubro. El sistema entiende que Fiestas Patrias significa demanda -90% para una cafeteria (cerrada, irrenunciable) pero la semana anterior es +80% (compras anticipadas). Y para una farmacia de turno, la demanda baja -60% pero no a cero.

### 4. Retroalimentacion automatica

Cada noche el sistema compara lo que predijo con lo que realmente se vendio. Si detecta que subestima los lunes, corrige automaticamente. Si un feriado tuvo demanda distinta a la esperada, aprende el multiplicador real para el proximo ano.

### 5. Forecasting de ingredientes (BOM)

Para restaurants y cafeterias, si el modelo predice que manana se venden 20 cafes con leche, automaticamente calcula que se necesitan 6 litros de leche y 4 kg de cafe en grano. Ningun otro sistema en Chile hace esto.

---

## Arquitectura del Motor

### Flujo de Datos Completo

```
Ventas diarias (DailySales)
    |
    v
[1] Limpieza de datos (clean_series)
    - Interpola dias sin stock (stockout)
    - Amortigua outliers con IQR
    |
    v
[2] Clasificacion del patron de demanda (ADI-CV2)
    - Suave: vende casi todos los dias
    - Intermitente: vende ocasionalmente, tamano constante
    - Irregular: vende raro, tamanos variables
    |
    v
[3] Extraccion de features
    - Efecto dia de pago (payday Chile 25-30)
    - Estacionalidad mensual o bimodal (verano/invierno)
    - Tendencia lineal (crecimiento/decrecimiento)
    - Crecimiento ano-a-ano
    |
    v
[4] Competencia de 11 algoritmos (backtest walk-forward)
    - Cada uno entrena con 70% de datos, predice 30%
    - Gana el de menor error (MAPE o MAE segun patron)
    |
    v
[5] Post-procesamiento
    - Ajuste de tendencia
    - Correccion de sesgo (bias) desde errores recientes
    - Estacionalidad mensual
    - Ajuste de feriados (por tipo de negocio)
    |
    v
[6] Predicciones guardadas (Forecast)
    - Prediccion diaria con intervalo de confianza
    - Dias hasta quiebre de stock
    |
    v
[7] Sugerencias de compra
    - Que comprar, cuanto, con que urgencia
    - Considera lead time del proveedor y MOQ
    |
    v
[8] Retroalimentacion nocturna
    - Compara prediccion vs venta real
    - Calcula error y corrige modelos
```

---

## Los 11 Algoritmos en Detalle

### 1. Media Movil Ponderada (Moving Average)

**Que hace:** Promedia las ventas recientes dando mas peso a los dias mas cercanos. Incluye factores por dia de la semana (lunes vende distinto que sabado).

**Cuando se usa:** Productos con 14+ dias de datos y demanda relativamente estable.

**Como funciona:**
- Toma las ultimas N ventas (ventana configurable por rubro)
- Aplica pesos exponenciales: dato de hoy pesa 10x mas que dato de hace 21 dias
- Calcula factor por dia de semana: si los viernes vende 1.5x el promedio, aplica ese factor
- Decay = 0.9 (cada dia anterior pierde 10% de relevancia)

**Por que lo usamos:** Es el caballo de batalla — rapido, robusto, funciona bien para la mayoria de productos de rotacion media. Es el fallback cuando algoritmos mas complejos fallan.

### 2. Media Movil Adaptativa (Adaptive MA)

**Que hace:** Igual que la media movil pero auto-optimiza sus parametros. Prueba multiples combinaciones de decay y ventana, elige la que mejor predice.

**Cuando se usa:** Productos con 21+ dias de datos. Reemplaza automaticamente a la media movil simple cuando hay suficientes datos.

**Como funciona:**
- Grid search: prueba decay en [0.85, 0.9, 0.93, 0.95, 0.97] y ventana en [14, 21, 28]
- Para cada combinacion, hace backtest
- Elige la que minimiza el error
- Incluye factores de dia del mes (efecto payday)

**Por que lo usamos:** Elimina la necesidad de configuracion manual. Un minimarket necesita ventana corta (14 dias), una ferreteria necesita larga (28 dias). Adaptive MA lo descubre solo.

### 3. Metodo Theta

**Que hace:** Descompone la demanda en tendencia lineal + nivel local, y combina ambas predicciones. Ganador de la competencia M3 de forecasting.

**Cuando se usa:** Productos con 14+ dias y patron suave. Especialmente bueno para detectar tendencias.

**Como funciona:**
- Calcula regresion lineal (OLS) para la tendencia
- Calcula suavizamiento exponencial simple (SES) para el nivel
- Prueba alpha en [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]
- Forecast = promedio de linea de tendencia + linea SES
- Intervalos basados en error historico (sqrt(MSE) x 1.28)

**Por que lo usamos:** Captura tendencias de crecimiento/decrecimiento mejor que moving average. Si un producto esta ganando popularidad (+5% semanal), Theta lo detecta y proyecta.

### 4. Holt-Winters (Triple Exponential Smoothing)

**Que hace:** Modela tres componentes: nivel (cuanto se vende), tendencia (subiendo o bajando), y estacionalidad semanal (lunes vs sabado).

**Cuando se usa:** Productos con 28+ dias y patron semanal claro (restaurants, cafeterias).

**Como funciona:**
- Seasonal periods = 7 (ciclo semanal)
- Tres parametros de suavizamiento: alpha (nivel), beta (tendencia), gamma (estacionalidad)
- Optimizados automaticamente por statsmodels (Maximum Likelihood)
- Forecast combina los 3 componentes

**Por que lo usamos:** Es el algoritmo mas sofisticado para demanda con patron semanal. Un cafe que vende 30 el viernes y 10 el martes necesita HW para predecir correctamente.

### 5. Holt-Winters Amortiguado (HW Damped)

**Que hace:** Igual que HW pero con la tendencia "frenada" — no asume que el crecimiento continua indefinidamente.

**Cuando se usa:** Productos con 28+ dias donde la tendencia puede ser temporal.

**Por que lo usamos:** Previene predicciones absurdas. Si un producto crece 10% semanal durante 1 mes, HW normal predice que seguira creciendo infinitamente. HW Damped asume que el crecimiento se frena, lo cual es mas realista.

### 6. ETS (Error-Trend-Season)

**Que hace:** Framework de espacio-estado que auto-selecciona si necesita error aditivo/multiplicativo, tendencia aditiva/multiplicativa/ninguna, y estacionalidad aditiva/multiplicativa/ninguna.

**Cuando se usa:** Productos con 28+ dias. Complementa a HW con mas flexibilidad.

**Por que lo usamos:** A veces la estacionalidad es multiplicativa (sabados vende 2x, no +20 unidades). ETS detecta esto automaticamente. HW asume estacionalidad aditiva, lo cual puede ser incorrecto.

### 7. Croston (Demanda Intermitente)

**Que hace:** Modela dos cosas por separado: el tamano de la venta cuando ocurre, y el intervalo entre ventas. Calcula la tasa diaria como tamano / intervalo.

**Cuando se usa:** Solo para productos con demanda intermitente o irregular (ADI >= 1.32). Ejemplos: postres especiales, productos de temporada, repuestos.

**Como funciona:**
- Extrae solo observaciones no-cero
- Suaviza tamano (z_hat) e intervalo (p_hat) con exponential smoothing
- Alpha auto-tuneado via grid search [0.05, 0.10, 0.15, 0.20, 0.30]
- Daily rate = z_hat / p_hat
- SBA adjustment opcional: multiplica por (1 - alpha/2) para debiasing
- Respeta weights de clean_series: datos interpolados influyen menos

**Por que lo usamos:** Los algoritmos clasicos (MA, HW) fallan para productos que venden 0 la mayoria de los dias. Croston esta disenado especificamente para esto. Una farmacia que vende un medicamento raro 2 veces al mes necesita Croston, no moving average.

### 8. Croston SBA (Syntetos-Boylan Adjustment)

**Que hace:** Version corregida de Croston que reduce el sesgo sistematico de sobre-estimacion.

**Cuando se usa:** Mismos criterios que Croston. Ambos compiten y gana el de menor MAE.

**Por que lo usamos:** Croston clasico tiende a sobre-estimar. SBA corrige esto multiplicando por (1 - alpha/2), lo cual da predicciones mas conservadoras y precisas para demanda irregular.

### 9. Prior de Categoria (Category Prior)

**Que hace:** Cuando un producto tiene pocos datos (< min_days), usa el promedio de su categoria como base y lo mezcla con los pocos datos propios via shrinkage Bayesiano.

**Cuando se usa:** Productos nuevos o con ventas esporadicas (< 10-21 dias segun rubro).

**Como funciona:**
- Busca el CategoryDemandProfile (promedio de la categoria)
- Bayesian shrinkage: blended = (n/(n+k)) x product_avg + (k/(n+k)) x category_avg
- k = shrinkage_k (7 para restaurant, 14 para retail, 21 para ferreteria)
- Con mas datos propios (n grande), mas peso al producto; con pocos datos, mas peso a la categoria
- MAPE real calculado con holdout 70/30

**Por que lo usamos:** Un producto nuevo en una cafeteria no tiene historial, pero si la categoria "Cafes" vende en promedio 15/dia, es razonable asumir que este producto vende algo similar. El shrinkage Bayesiano es la forma matematicamente correcta de combinar esta informacion a priori con los pocos datos que tenemos.

### 10. Derivado de Receta (Ingredient Derived)

**Que hace:** Para ingredientes que se consumen a traves de recetas, calcula la demanda sumando los forecasts de los productos padre multiplicados por la cantidad de receta.

**Cuando se usa:** Solo para restaurants/cafeterias. Ingredientes que son parte de recetas (cafe en grano, leche, azucar).

**Como funciona:**
- Busca todas las RecipeLines donde este producto es ingrediente
- Para cada producto padre: obtiene su forecast activo
- Multiplica: forecast_padre x qty_por_unidad_receta
- Suma todas las recetas: demanda_total_ingrediente
- Genera forecast dia por dia respetando estacionalidad del padre

**Ejemplo:**
- Cafe Latte (padre): forecast = 20 unidades/dia
- Receta: 0.3 kg cafe, 0.2 lt leche por unidad
- Forecast cafe en grano: 20 x 0.3 = 6 kg/dia
- Forecast leche: 20 x 0.2 = 4 lt/dia

**Por que lo usamos:** Sin esto, un restaurant tendria que estimar manualmente cuanto cafe comprar basandose en las ventas de cada tipo de cafe. Con BOM forecasting, el sistema lo calcula automaticamente.

### 11. Ensemble (Combinacion Ponderada)

**Que hace:** Combina las predicciones de 2 o mas modelos viables usando pesos proporcionales a su precision.

**Cuando se usa:** Productos con 28+ dias de datos y al menos 2 algoritmos candidatos con MAPE < 100%.

**Como funciona:**
- Weighting con softmax suavizado: weight = exp(-metric/temperature)
- temperature = mediana de las metricas (suaviza distribucion de pesos)
- Prediccion = suma ponderada de predicciones individuales
- Intervalo: lower = min(todos los lower), upper = max(todos los upper)
- Metricas del ensemble = promedio ponderado de metricas componentes

**Por que lo usamos:** La teoria de forecasting demuestra que combinar multiples modelos casi siempre supera al mejor modelo individual. El ensemble reduce el riesgo de que un solo modelo tenga un dia malo.

---

## Clasificacion de Demanda

El motor clasifica cada producto usando el framework ADI-CV2:

| Patron | Condicion | Ejemplo | Algoritmo preferido |
|--------|-----------|---------|---------------------|
| **Suave** | ADI < 1.32 | Cafe americano (vende todos los dias) | HW, Theta, Moving Avg |
| **Intermitente** | ADI >= 1.32, CV2 < 0.49 | Medicamento (vende cada 3 dias, cantidad estable) | Croston |
| **Irregular** | ADI >= 1.32, CV2 >= 0.49 | Torta especial (vende raro, cantidades variables) | Croston SBA |
| **Insuficiente** | < 3 ventas | Producto recien agregado | Category Prior |

- **ADI** (Average Demand Interval): dias promedio entre ventas. Si es 1.0, vende todos los dias. Si es 5.0, vende cada 5 dias.
- **CV2** (Coefficient of Variation squared): variabilidad del tamano de venta. Si es bajo, las ventas son consistentes. Si es alto, a veces vende 1 y a veces 50.

---

## Efecto Payday (Dia de Pago Chile)

El motor detecta automaticamente el efecto del dia de pago en Chile (25-30 de cada mes) y ajusta las predicciones:

| Periodo del mes | Factor tipico | Explicacion |
|-----------------|--------------|-------------|
| 1-5 (post-sueldo) | 0.85x | Gasto fuerte, empiezan a cuidar |
| 6-12 | 0.92x | Gasto moderado |
| 13-19 | 1.05x | Normalizado |
| 20-25 (pre-sueldo) | 1.20x | Anticipacion salarial |
| 26-31 (sueldo) | 1.38x | Pico de gasto post-sueldo |

El sistema detecta si el pico real no cae en 25-30 (algunos negocios tienen clientes con pago quincenal) y ajusta los buckets automaticamente.

---

## Estacionalidad

### Estacionalidad Mensual (6+ meses de datos)

Calcula factores por mes del ano. Ejemplo para una heladeria:
- Enero (verano): factor 2.0 (doble de demanda)
- Julio (invierno): factor 0.5 (mitad de demanda)

Solo se activa si la variacion max/min es >= 20%.

### Estacionalidad Bimodal (4+ meses de datos)

Para productos con patron extremo verano/invierno (ratio >= 2x):
- Agrupa meses en calidos (Oct-Mar) y frios (Abr-Sep) para Chile
- Permite factores extremos de 0.1 a 4.0
- Helados: verano 2.5x, invierno 0.3x
- Calefactores: invierno 3.0x, verano 0.2x

### Estacionalidad por Tipo de Negocio (Ferreteria)

Para ferreterias sin suficiente historial, usa un prior de construccion en Chile:
- Septiembre-Marzo (primavera/verano): factor 1.0 - 1.4 (temporada de construccion)
- Abril-Agosto (otono/invierno): factor 0.6 - 0.8 (baja actividad)

---

## Feriados Chilenos y Eventos Comerciales

126 eventos pre-configurados (2025-2030) con modelado avanzado:

### Feriados Irrenunciables

Los feriados irrenunciables (1 ene, 1 may, 18-19 sept, 25 dic, Viernes Santo) tienen multiplicador del dia < 1.0 (la mayoria de los negocios cierra), pero multiplicador pre-evento alto (la gente compra antes):

| Feriado | Dia mismo | Pre-evento | Post-evento |
|---------|-----------|-----------|-------------|
| Fiestas Patrias (18 sept) | 0.30x (3 dias) | 1.80x (7 dias antes, rampa gradual) | 1.30x (3 dias) |
| Navidad (25 dic) | 0.15x | 1.80x (14 dias antes, rampa gradual) | 0.70x (3 dias) |
| Ano Nuevo (1 ene) | 0.20x | 1.50x (3 dias antes) | 1.20x (2 dias) |
| Viernes Santo | 0.25x | 1.20x (2 dias antes) | 0.85x (1 dia) |

### Multiplicadores por Tipo de Negocio

Cada feriado tiene multiplicadores diferenciados porque el impacto varia por rubro:

| Feriado | Retail | Restaurant | Ferreteria | Farmacia |
|---------|--------|-----------|-----------|----------|
| Fiestas Patrias (dia) | 0.20x | 0.10x | 0.05x | 0.40x |
| Black Friday | 2.20x | 1.20x | 2.00x | 1.30x |
| San Valentin | 1.40x | 2.00x | 1.00x | 1.10x |
| Dia de la Madre | 1.60x | 1.80x | 1.00x | 1.20x |

### Eventos Comerciales

Ademas de feriados legales, el motor modela eventos comerciales:
- **Black Friday / CyberMonday**: 4 dias de duracion, 7 dias pre-evento, 7 dias post-dip
- **Dia de la Madre**: 7 dias pre-evento (compras anticipadas de regalos)
- **San Valentin**: 5 dias pre-evento, restaurantes +100%
- **Vuelta a Clases**: 7 dias plateau (demanda sostenida la primera semana de marzo)

### Aprendizaje Automatico de Feriados

El primer ano el sistema usa los multiplicadores configurados. Cuando ocurre un feriado, `track_forecast_accuracy` compara la prediccion con la venta real y calcula un `learned_multiplier`. Para el proximo ano, el sistema usa un blend 60% aprendido + 40% configurado, acercandose cada vez mas a la realidad de cada negocio.

---

## Sugerencias de Compra Inteligentes

El motor no solo predice demanda — genera sugerencias concretas de que comprar, cuanto y cuando:

### Calculo de Cantidad Sugerida

```
suggested_qty = demanda_target_days + demanda_lead_time + safety_stock - stock_actual
```

Donde:
- **demanda_target_days**: suma de forecast para el horizonte de cobertura
- **demanda_lead_time**: demanda durante los dias que tarda el proveedor en entregar
- **safety_stock**: buffer de seguridad proporcional a la confianza del modelo
- **stock_actual**: lo que hay en bodega ahora

### Safety Stock por Confianza

Modelos menos confiables agregan mas buffer para evitar quiebres:

| Confianza | Buffer |
|-----------|--------|
| Muy alta | +5% |
| Alta | +8% |
| Media | +15% |
| Baja | +25% |
| Muy baja | +35% |

### Lead Time por Tipo de Negocio

| Rubro | Lead time default |
|-------|------------------|
| Restaurant | 2 dias |
| Minimarket | 3 dias |
| Farmacia | 5 dias |
| Ferreteria | 30 dias |
| Distribuidora | 45 dias |

Si el proveedor tiene `lead_time_days` configurado, usa ese valor en vez del default.

### MOQ (Cantidad Minima de Pedido)

Si el proveedor tiene un minimo de pedido (MOQ) y la cantidad sugerida es menor, el sistema redondea hacia arriba al MOQ automaticamente.

### Prioridad de Compra

| Prioridad | Condicion |
|-----------|-----------|
| CRITICA | Quiebre en < 3 dias |
| ALTA | Quiebre en 3-7 dias |
| MEDIA | Quiebre en 7-14 dias |
| BAJA | Quiebre en > 14 dias |

Para modelos de baja confianza, los umbrales son mas conservadores (CRITICA < 5 dias, ALTA < 10 dias).

---

## Ciclo de Retroalimentacion

El motor se auto-mejora mediante un ciclo nocturno automatico:

### Programacion (Cron)

| Hora | Comando | Funcion |
|------|---------|---------|
| 01:30 | track_forecast_accuracy | Compara prediccion vs venta real de ayer |
| 02:00 | generate_purchase_suggestions | Genera sugerencias de compra |
| 03:00 (domingos) | compute_category_profiles + train_forecast_models | Re-entrena todos los modelos |

### Como Funciona la Correccion de Sesgo

1. **Dia T**: El modelo predice "manana se venden 15 cafes"
2. **Dia T+1**: Se vendieron 18 cafes. Error = -3 (subestimo)
3. **Track accuracy**: Guarda el error en ForecastAccuracy
4. **Dia T+7 (domingo)**: Re-entrenamiento lee los errores de la semana
5. **Bias correction**: Detecta que subestima los lunes en promedio -2.5 unidades
6. **Proximo lunes**: Agrega +2.5 a la prediccion del lunes

### Comparacion de Modelos

Al re-entrenar, el sistema compara el nuevo modelo con el existente:
- Si el nuevo MAPE > viejo MAPE x 1.1 (10% peor): **mantiene el viejo**
- Si el nuevo es mejor: **reemplaza y registra la mejora**
- Tracking: prev_mape, mape_delta, prev_algorithm — para auditar que los cambios sean positivos

---

## Monitoreo y Observabilidad

### ForecastTrainingLog

Cada ejecucion del entrenamiento queda registrada en la base de datos:
- Status: exitoso, parcial (algunos tenants fallaron), fallido
- Duracion en segundos
- Modelos entrenados, mejorados, mantenidos, fallidos
- MAPE promedio post-entrenamiento
- Distribucion de algoritmos

### Panel Superadmin

El superadmin en `/superadmin/forecast/` muestra:
- MAPE promedio global y por tenant
- Distribucion de algoritmos, confianza y patrones de demanda
- Tendencia de error ultimos 30 dias
- Historial de ejecuciones del entrenamiento con status y errores

---

## Perfiles de Negocio

Cada tipo de negocio tiene parametros optimizados:

| Parametro | Retail | Restaurant | Ferreteria | Distribuidora | Farmacia |
|-----------|--------|-----------|-----------|---------------|----------|
| Ventana MA | 14 dias | 7 dias | 30 dias | 21 dias | 14 dias |
| Datos minimos | 14 dias | 10 dias | 21 dias | 14 dias | 14 dias |
| Horizonte | 30 dias | 21 dias | 60 dias | 45 dias | 30 dias |
| Shrinkage k | 14 | 7 | 21 | 14 | 14 |
| Lead time default | 3 dias | 2 dias | 30 dias | 45 dias | 5 dias |

### Por que estos valores

- **Restaurant ventana=7**: El patron semanal es el mas importante (viernes vs lunes). Una ventana de 14 dias mezclaria 2 semanas y perderia precision dia-a-dia.
- **Ferreteria ventana=30**: Los proyectos de construccion generan demanda en ciclos mensuales. Una ventana corta perderia el patron de proyecto.
- **Restaurant shrinkage_k=7**: Los productos de cafeteria cambian rapido (menu rotativo). Con k=7, los datos propios ganan peso mas rapido.
- **Ferreteria shrinkage_k=21**: Los items de ferreteria son mas estables. Se necesita mas evidencia antes de divergir del promedio de categoria.

---

## Metricas del Motor

### MAPE (Mean Absolute Percentage Error)

```
MAPE = promedio( |prediccion - real| / real x 100 )
```

Interpretacion:
- < 15%: Excelente — prediccion muy precisa
- 15-30%: Bueno — aceptable para retail
- 30-50%: Aceptable — funciona para sugerencias
- > 50%: Requiere revision

### Confianza del Modelo

| Nivel | Datos requeridos | MAPE requerido |
|-------|-----------------|---------------|
| Muy alta | 180+ dias | < 20% |
| Alta | 60+ dias | < 35% |
| Media | 21+ dias | < 55% |
| Baja | 7+ dias o MAPE < 80% | — |
| Muy baja | Resto | — |

Productos con demanda intermitente/irregular tienen confianza maxima "Alta" (MAPE es poco confiable con ceros).

Alta variabilidad (CV2 > 1.0) penaliza la confianza: el MAPE se infla en hasta 30% para el calculo de confianza.

---

## Resumen Tecnico

- **11 algoritmos** compitiendo por producto
- **126 feriados** pre-configurados con multiplicadores por rubro
- **6 perfiles de negocio** con parametros optimizados
- **Backtesting walk-forward** con 3 folds
- **Auto-correccion** nocturna via bias correction
- **BOM forecasting** para restaurants (ingredientes derivados de recetas)
- **Safety stock dinamico** proporcional a confianza del modelo
- **Lead time y MOQ** integrados en sugerencias de compra
- **Estacionalidad bimodal** para productos extremos (helados, calefactores)
- **Monitoreo completo** con ForecastTrainingLog y panel superadmin
