# Pulstock — Motor Predictivo de Demanda
### Guía completa para entrevista técnica · IA / Análisis Predictivo

---

## 1. Resumen ejecutivo (para abrir la conversación)

Pulstock es un SaaS de inventario multi-tenant para el mercado chileno. Su módulo más complejo técnicamente es el **motor de forecast de demanda**: predice cuánto se va a vender cada producto los próximos N días, por sucursal, para generar sugerencias de compra automáticas y alertas de quiebre de stock.

**Arquitectura en una frase**: pipeline nocturno (cron 03:00 AM) que agrega ventas → clasifica el patrón de demanda de cada producto → entrena en paralelo ~10 algoritmos candidatos → los valida con walk-forward cross-validation → elige el mejor por MAPE/MAE → aplica capas de enriquecimiento (feriados, estacionalidad, quiebres) → guarda predicciones día-a-día en DB.

**Números clave del diseño**:
- **~11 algoritmos** registrados en un `ALGORITHM_REGISTRY`
- **Walk-forward CV con 3 folds** para backtesting
- **Ensemble softmax-weighted** cuando ≥2 candidatos son viables
- **Horizonte configurable** (7 a 90 días según tipo de negocio)
- **Tracking diario de accuracy**: cada día compara predicción anterior vs real

---

## 2. Pipeline completo (nightly batch)

```
03:00  aggregate_daily_sales       → materializa ventas del día anterior en DailySales
03:05  compute_category_profiles   → priors por categoría (para productos nuevos)
03:10  train_forecast_models       → ENTRENA todos los modelos
03:20  track_forecast_accuracy     → compara predicciones de ayer vs real
03:30  generate_purchase_suggestions → convierte forecast en sugerencias de compra
```

Todo corre como **management commands de Django** invocados por **cron** (`/etc/cron.d/pulstock`). No usamos Celery worker en producción — elegimos cron + comandos sincronos porque: (a) no hay cola de tareas urgentes, (b) un único job por noche es más simple de debuggear, (c) no agrega dependencias de broker.

---

## 3. Clasificación del patrón de demanda (ADI-CV²)

Antes de entrenar, clasifico cada producto con el **framework ADI-CV²** (Syntetos & Boylan, 2005):

- **ADI** (Average Demand Interval) = promedio de días entre ventas no-cero
- **CV²** (squared Coefficient of Variation) = varianza de los tamaños de venta / media²

Reglas:
| Patrón | ADI | CV² | Ejemplo |
|--------|-----|-----|---------|
| **Smooth** | < 1.32 | cualquiera | Pan, leche (alta rotación) |
| **Intermittent** | ≥ 1.32 | < 0.49 | Producto de nicho, pero cuando se vende, se venden ~constantes |
| **Lumpy** | ≥ 1.32 | ≥ 0.49 | Repuesto de ferretería: raro + cantidades muy variables |
| **Insufficient** | < 3 observaciones no-cero | — | No se entrena, se usa prior de categoría |

**Por qué importa**: los algoritmos clásicos (Holt-Winters, Theta, regresión) asumen demanda smooth. Para lumpy/intermittent, MAPE explota porque los actuals son 0; hay que usar **MAE** y algoritmos específicos como **Croston**.

*Código*: `apps/api/forecast/engine/patterns.py`

---

## 4. Catálogo de algoritmos

### 4.1 `simple_avg` (baseline)
Promedio aritmético de los últimos N días. **Baseline obligatorio**: si un modelo sofisticado no le gana a esto, hay overfitting o bug.

### 4.2 `moving_avg` / `adaptive_ma` — Media Móvil Ponderada
- **WMA con decay exponencial 0.9**: cada día reciente pesa 0.9× más que el anterior. Los últimos 21 días.
- **Factores de día de la semana**: calculo `dow_factor[d] = avg_ventas_en_ese_dow / avg_global`. Un restaurant tiene lunes ≈ 0.6 y sábado ≈ 1.8 del promedio.
- **Adaptive MA**: grid search sobre `decay ∈ {0.85…0.97}` × `window ∈ {14,21,28}` + backtest rápido. Elige la combinación con menor MAE en los últimos 7 días.
- **Pros**: rápido, interpretable, robusto con poca data (min 14 días).
- **Contras**: no captura tendencia ni estacionalidad anual.

### 4.3 `theta` — Método Theta
Ganador de la **competencia M3** (Assimakopoulos & Nikolopoulos, 2000). Descomposición elegante:
1. Ajusta una **regresión lineal OLS** a la serie (captura tendencia)
2. Ajusta **SES (Simple Exp Smoothing)** con búsqueda de α óptimo ∈ {0.05…0.5}
3. Forecast = promedio de las dos líneas

Super simple, rinde cerca de redes neuronales en series con tendencia pero sin estacionalidad fuerte. **Min 14 días**.

### 4.4 `holt_winters` / `hw_damped` — Triple Exponential Smoothing
Usa `statsmodels.tsa.holtwinters.ExponentialSmoothing` con 3 componentes:
- **Level** (suavizado α)
- **Trend** (suavizado β)
- **Seasonality** (suavizado γ, con período **semanal = 7 días**)

Las tres smoothing rates las optimiza `statsmodels` internamente por MLE. La variante `damped` aplica un factor φ que amortigua la proyección de tendencia para no extrapolar de más. **Min 28 días** (4 semanas para aprender la estacionalidad).

### 4.5 `ets` — Exponential Smoothing State Space
Generalización de Holt-Winters con selección automática de componentes Error/Trend/Seasonality (Additive/Multiplicative/None).

### 4.6 `croston` / `croston_sba` — Demanda intermitente
**Exclusivos para patrones intermittent/lumpy**. Croston (1972) descompone:
- `z_hat` = tamaño promedio suavizado de las ventas no-cero
- `p_hat` = intervalo promedio suavizado entre ventas
- Forecast diario = `z_hat / p_hat`

**SBA** (Syntetos-Boylan Adjustment, 2005) corrige el sesgo positivo de Croston multiplicando por `(1 - α/2)`. Grid search de α ∈ {0.05, 0.10, 0.15, 0.20, 0.30}.

**Intervalos de confianza**: se calculan via **bootstrap** de los tamaños históricos (`croston_bootstrap_intervals`).

### 4.7 `category_prior` — Prior bayesiano
Para productos con <14 días de historia (recién creados), uso el **perfil promedio de su categoría** como predicción. Aplico **shrinkage**: el peso del prior baja linealmente según días de data propia (`shrinkage_k=14`).

### 4.8 `ensemble` — Combinación ponderada
Cuando ≥2 candidatos quedan viables (MAPE < 100), combino con **pesos softmax**:

```python
w_i = exp(-metric_i / T) / Σ exp(-metric_j / T)
```

donde T = media de las métricas (actúa como temperatura). El resultado es una mezcla robusta que reduce varianza (análogo a bagging).

---

## 5. Selección automática del mejor modelo

`forecast/engine/selection.py` → función `select_best_model()`:

```python
for algo in ALGORITHM_REGISTRY:
    if not algo.is_eligible(n_days, demand_pattern):
        continue
    metrics = algo.backtest(series, test_days=7, n_folds=3)
    if metrics["mae"] >= 998: continue   # falló
    result = algo.forecast(series, horizon=14)
    candidates.append(result)

# Criterio de selección depende del patrón
if pattern in ("intermittent", "lumpy"):
    best = min(candidates, key=lambda c: c["metrics"]["mae"])
else:
    best = min(candidates, key=lambda c: c["metrics"]["mape"])
```

**Diseño clave**: MAPE no se usa para intermittent/lumpy porque explota cuando actual=0 (`|pred-0|/0 = ∞`). Para esos patrones uso MAE en su lugar.

---

## 6. Validación — Walk-Forward Cross-Validation

**Este es el concepto clave que diferencia CV para series temporales.** No se puede usar k-fold normal (shuffled) porque viola causalidad — predeciría el pasado con el futuro.

Mi implementación:

```
Serie completa: [día 1, día 2, ..., día 90]

Fold 0:  train=[1..83]         test=[84..90]
Fold 1:  train=[1..76]         test=[77..83]
Fold 2:  train=[1..69]         test=[70..76]

métrica_final = promedio de los 3 folds
```

- `test_days=7` → cada fold predice 7 días adelante
- `n_folds=3` → promediamos 3 ventanas distintas
- `min_train` depende del algoritmo (ej. Holt-Winters necesita 28 días mínimo)

**Ventajas sobre hold-out simple**:
1. Evalúa estabilidad (si el modelo sirve sólo en una ventana específica, los 3 folds lo delatan)
2. Evita lucky-split
3. Respeta la dirección del tiempo

---

## 7. Métricas — qué calculo y por qué

Para cada fold y cada algoritmo computo en `forecast/engine/utils.py::_compute_metrics()`:

| Métrica | Fórmula | Cuándo la uso |
|---------|---------|---------------|
| **MAE** | `mean(|y - ŷ|)` | Demanda intermitente/lumpy (robusta a ceros) |
| **MAPE** | `mean(|y - ŷ| / y) × 100` para y>0 | Demanda smooth — interpretable como % |
| **RMSE** | `sqrt(mean((y - ŷ)²))` | Penaliza errores grandes — lo reporto para diagnostico |
| **Bias** | `mean(ŷ - y)` | Detecta sesgo sistemático. Si es +5, el modelo sobre-predice en 5 unidades promedio |

MAPE tiene dos problemas conocidos:
1. **Explota cuando y→0** → por eso para intermittent uso MAE
2. **Asimétrica**: sobre-predecir 100 vs 50 (200%) vs sub-predecir 50 vs 100 (50%). Para reporting uso MAPE pero sé sus limitaciones.

Alternativas que consideré y descarté (por complejidad vs beneficio):
- **sMAPE** (symmetric MAPE) — más justa pero menos intuitiva
- **MASE** (Mean Absolute Scaled Error) — compara vs naïve forecast, excelente pero no me aporta para elegir entre candidatos

---

## 8. Capas de enriquecimiento (post-processing)

Tras elegir el modelo base, aplico **enhancements** que corrigen por factores que los modelos estadísticos no capturan bien:

### 8.1 Día del mes — "efecto sueldo"
En Chile el sueldo se paga entre el **25–30**. Segmento los días en 5 buckets (early/mid_early/mid/mid_late/late) y calculo el factor medio de cada bucket. Si la demanda varía ≥15% entre ellos, el factor se aplica.

### 8.2 Estacionalidad mensual (mes del año)
Con ≥180 días de data, calculo el `month_factor[m] = avg_demanda_en_mes_m / avg_global`. Con **shrinkage** si un mes tiene <15 observaciones.

### 8.3 Estacionalidad bimodal (invierno/verano)
Detecto diferencia ≥2× entre warm-months (Oct–Mar en Chile) vs cold-months (Abr–Sep). Típico para farmacia: antigripales ↑ en invierno, protectores solares ↑ en verano.

### 8.4 Crecimiento YoY
Con ≥365 días de data, comparo últimos 90 días vs mismo período año anterior. Aplico factor **damped** (×0.5) para no extrapolar crecimiento de forma agresiva.

### 8.5 Tendencia lineal (OLS sobre agregado semanal)
Regresión lineal sobre promedios semanales. Sólo aplico si `R² ≥ 0.3` Y slope relativo ≥ 0.5% del promedio. Clampeo el factor multiplicativo entre 0.5 y 2.0.

### 8.6 Feriados con multiplier aprendido
Cada feriado tiene:
- `demand_multiplier` configurado (ej. Navidad = 2.0 para retail)
- `learned_multiplier` que se re-calcula cada año con `compute_holiday_learned_multiplier`: compara la demanda del día del feriado pasado vs baseline ±7 días

Combinación final: `mult = 0.6 × learned + 0.4 × configured` (aprendizaje supervisado ligero).

También maneja **pre-days** (ej. día antes de Año Nuevo +30%), **post-days**, **ramp linear** o **instant**, y **duration** para feriados multi-día (fiestas patrias).

### 8.7 Corrección de sesgo (bias correction)
Al tracking diario se guarda el error por día → si en los últimos 14 días el modelo sobre-predice sistemáticamente los lunes, aplico `correction_lunes = -0.5 × mean(errores_lunes)` a los próximos forecasts de lunes. Esto es **online learning liviano**.

### 8.8 Decay de confianza
Un modelo entrenado hace X días pierde confianza. Exponencial con half-life 14 días:
```
confianza_hoy = base × 0.5^(días_desde_trained / 14)
```
con piso del 20% para no bajar a 0.

---

## 9. Limpieza de datos (data cleaning)

`forecast/engine/utils.py::clean_series()` hace 3 cosas antes de entrenar:

### 9.1 Interpolación de stockouts
Si un día tiene qty=0 pero es por quiebre de stock (detectado con `is_stockout=True` en DailySales), reemplazo por el promedio de los últimos 3 mismos-días-de-semana. Peso 0.5 para que ese día influya menos en el entrenamiento.

### 9.2 Amortización de outliers
Calculo Q1/Q3/IQR. Límite = `max(Q3 + 2×IQR, percentil 97.5)`. Si un valor supera el límite, lo clipeo ahí. Peso 0.7. Evita que una venta anómala (ej. pedido B2B de un cliente) entrene al modelo mal.

### 9.3 Promociones
Los días de promoción (los hay con descuento ≥X%) los marco con peso 0.6 para que no inflen el baseline de demanda normal.

**Este es mi análogo a regularización**: en vez de aprender sesgado por datos atípicos, les bajo el peso en la loss function.

---

## 10. Tracking de accuracy post-hoc

Cada día a las 03:20 corre `track_forecast_accuracy`. Toma las predicciones que se hicieron **para ayer** (hechas el día anterior o antes) y las compara contra las ventas reales (`DailySales`).

Guarda en `ForecastAccuracy`:
- `qty_predicted`, `qty_actual`, `error`, `abs_pct_error`
- `algorithm` que la generó
- `was_stockout` (si hubo quiebre, el error no es "culpa" del modelo)

Esto alimenta:
- Dashboard de precisión por algoritmo
- Bias correction (sección 8.7)
- Re-aprendizaje de feriados
- Detección de model drift

---

## 11. Perfiles por tipo de negocio

Los hiperparámetros se ajustan según `tenant.business_type`:

| Negocio | window | horizon | seasonal_prior |
|---------|--------|---------|----------------|
| **retail** | 14d | 30d | — |
| **restaurant** | 7d | 21d | Ene/Feb ↑ (turismo verano Chile) |
| **hardware** | 30d | 60d | Sep–Mar ↑ (construcción) |
| **pharmacy** | 14d | 30d | May–Ago ↑ (gripal invierno) |
| **wholesale** | 21d | 45d | — |
| **other** | 21d | 30d | — |

Un restaurant tiene ventana corta (la semana pasada predice mejor que hace 1 mes); ferretería al revés, los proyectos se dibujan en meses.

---

## 12. Overfitting — cómo lo manejo

Aunque no uso redes neuronales (no tiene sentido para series de <2 años, pocos samples, sin features ricas), los conceptos aplican análogamente:

### 12.1 Validación por walk-forward (sección 6)
Es la defensa principal. Si un modelo con muchos parámetros memoriza la serie, los 3 folds lo delatan.

### 12.2 Grid search con k-fold temporal, no en producción directa
Adaptive MA y Croston hacen grid search sobre hiperparámetros, pero **usando backtest** — no se selecciona por in-sample fit, siempre por CV. Esto es equivalente al train/val split de deep learning.

### 12.3 Shrinkage (análogo a regularización L2)
Los factores mensuales, de feriados y de categoría se "encogen" hacia 1.0 (o hacia el prior) cuando hay pocas observaciones:
```python
if n_obs < 15:
    shrink = n_obs / 15.0
    factor = 1.0 + (factor - 1.0) * shrink
```
Esto es **shrinkage bayesiano** — equivalente conceptual al término λ||w||² de Ridge Regression.

### 12.4 Damping
El factor `phi` de `hw_damped` y la corrección YoY con damping 0.5 previenen que el modelo extrapole tendencias explosivamente.

### 12.5 Clamping (hard limits)
Todos los factores multiplicativos están clampeados:
- Factor de tendencia: `[0.5, 2.0]`
- Factor de feriado aprendido: `[0.2, 5.0]`
- Factor de YoY: `[0.5, 2.0]`

Esto es equivalente a **gradient clipping** en redes neuronales.

### 12.6 Ensemble
Combinar modelos reduce varianza (teorema clásico del sesgo-varianza). Softmax weighting prioriza los mejores pero no descarta completamente los otros — similar a **model averaging** en Bayesian ML.

### 12.7 Diversity en la lista de candidatos
Tengo modelos de familias muy distintas (exp smoothing, regresión, bayesiano, intermittent-specific). Si estoy overfitteando con un family, los otros me dan sanity check via ensemble.

---

## 13. Si preguntan por regresión lineal específicamente

La uso en **3 lugares**:

1. **Theta method** (`algorithms/theta.py`): OLS sobre (t, ventas) para sacar slope+intercept.
2. **Trend detection** (`enhancements.py::detect_trend`): OLS sobre agregados semanales. Reporto R² y slope/mean_daily. Sólo aplico si R² ≥ 0.3 (umbral arbitrario pero sensato — si la variabilidad explicada es menor al 30%, el slope es ruido).
3. **Category profile** (implícito): promedio con shrinkage = equivalente a MLE con prior Gaussian.

**Formulación que puedo escribir en pizarra**:
```
ŷ = β₀ + β₁·t

β₁ = Σ(xᵢ - x̄)(yᵢ - ȳ) / Σ(xᵢ - x̄)²
β₀ = ȳ - β₁·x̄

R² = 1 - SS_res/SS_tot
```

**Supuestos** (Gauss-Markov):
1. Linealidad en parámetros
2. Residuos media 0
3. Homoscedasticidad (varianza constante)
4. No autocorrelación
5. No multicolinealidad (si hay múltiples features)

**Violaciones típicas y cómo las detecto**:
- **Heteroscedasticidad**: plot de residuos vs ŷ en forma de cono → uso transformación log o WLS
- **Autocorrelación de residuos** (Durbin-Watson ≠ 2): problema típico en series temporales → por eso uso Holt-Winters en vez de OLS simple
- **Outliers** (leverage/Cook's distance): mi clean_series los amortigua con IQR

---

## 14. Si preguntan por redes neuronales y dropout

Aunque no las uso hoy en Pulstock (overkill para el volumen actual), entiendo los conceptos:

### Dropout
Técnica de regularización propuesta por Hinton et al. (2014). Durante **entrenamiento**, cada neurona se "apaga" con probabilidad `p` (típicamente 0.2–0.5). En **inferencia** todas las neuronas están activas pero sus outputs se multiplican por `(1-p)` para compensar la escala.

**Por qué funciona**:
- Evita que una neurona dependa demasiado de otra específica (co-adaptación)
- Equivalente a entrenar un ensemble exponencial de sub-redes y promediarlas
- Es una forma de **data augmentation implícita** en el espacio de activaciones

**Reglas prácticas**:
- No uses dropout en la capa de salida
- Más dropout en capas con más parámetros
- Con BatchNorm, el orden importa: típicamente Conv → BN → ReLU → Dropout

### Otras técnicas de regularización que manejo
| Técnica | Efecto |
|---------|--------|
| **L1 (Lasso)** | Esparsidad — features irrelevantes → peso 0 |
| **L2 (Ridge)** | Reduce magnitud de pesos (sin llegar a 0) |
| **Early stopping** | Paras cuando val loss deja de mejorar |
| **Data augmentation** | Más datos sintéticos |
| **Batch normalization** | Reduce covariate shift interno |
| **Weight decay** | Equivalente a L2 pero en el optimizer |

### Análogos que aplico en Pulstock (series temporales, sin NN)
- **Shrinkage** ≈ L2
- **Clamping** ≈ gradient clipping
- **Walk-forward CV** ≈ train/val split con early stopping conceptual
- **Data cleaning** (outlier damping) ≈ robust loss (Huber loss equivalente)
- **Ensemble** ≈ dropout-at-inference (cada modelo es un "thinned network")

### Si la pregunta es "cómo manejarías overfitting en un modelo predictivo"
Respuesta estructurada:
1. **Diagnóstico primero**: comparar train vs validation loss. Si train << val, es overfit. Si ambos son malos, es underfit.
2. **Datos**: más datos, data augmentation, o feature engineering mejor.
3. **Modelo**: reducir capacidad (menos parámetros), early stopping.
4. **Regularización**: L1/L2, dropout, batch norm.
5. **Validación robusta**: k-fold (o walk-forward si es temporal), nunca elegir modelo por train loss.
6. **Ensemble**: bagging/boosting/stacking reducen varianza.

---

## 15. Preguntas que probablemente te hagan

### Q: "¿Por qué no usas un LSTM o Transformer para el forecast?"

R: Tres razones:
1. **Volumen de datos**: un producto típico tiene 90–365 días de observaciones. LSTM necesita miles. Con 90 puntos, Holt-Winters rinde igual o mejor.
2. **Interpretabilidad**: para sugerencias de compra, Mario (el cliente) necesita entender por qué. "Es Holt-Winters con seasonality 7, tendencia al alza" es explicable. "La caja negra dice 42" no.
3. **Costo computacional**: entrenar 10 modelos para 1000 productos es manejable con Theta/HW. Con LSTM, 4 horas vs 4 minutos.

Cuando **escalaría a redes** sería si tuviera data cross-product (aprender de productos similares vía embeddings) — tipo **DeepAR** de Amazon o **N-BEATS**. Pero eso requiere >100 productos con historia larga.

### Q: "¿Cómo validas que tu modelo sirve en producción?"

R: Tracking diario automatizado (`track_forecast_accuracy`). Cada día veo:
- MAPE medio por algoritmo
- Distribución de errores por producto
- Si `bias` se aleja sistemáticamente de 0 → el modelo está sesgado
- `mape_delta` vs versión anterior → veo si re-entrenos están mejorando o empeorando

Si MAPE promedio sube 2 noches seguidas, salta un alerta interno.

### Q: "¿Cómo manejas cold start (producto nuevo)?"

R: Tres niveles:
1. **<14 días pero es ingrediente de receta**: deriva forecast del plato padre (BOM-based).
2. **<14 días sin receta**: `category_prior` con shrinkage (sec 4.7). El prior viene de `CategoryDemandProfile` computado nightly.
3. **0 data, 0 categoría**: no entrenamos, mostramos "datos insuficientes" en UI.

### Q: "¿Qué feature haría más impactante si tuvieras más tiempo?"

R: **Modelo jerárquico cross-tenant**: aprender un prior global (todos los restaurants) + específico por tenant. Hoy cada tenant entrena en silo. Con 50 restaurants podríamos aprender "los lunes se vende menos café" como ley universal y transferir a restaurants nuevos.

Técnicamente: **Bayesian hierarchical model** o **transfer learning con fine-tuning**.

### Q: "¿Y sesgo? ¿Tu modelo discrimina?"

R: No trabajo con datos personales, sólo series de ventas. Pero sí hay **sesgo de sobrevivencia**: los productos discontinuados salen del dataset, sesgando hacia los exitosos. Lo mitigo manteniendo `forecast_only=True` para importaciones históricas, pero es un gap real.

### Q: "Si tuvieras que explicárselo a un ejecutivo..."

R: "Predecimos cuánto va a vender cada producto los próximos 30 días, con un margen de error de ~15% en productos estables. Eso nos permite sugerir órdenes de compra automáticas 7 días antes de quebrar stock, ahorrándole al dueño del local hasta 40% de inventario muerto. El modelo aprende solo de la historia de ventas del local y se actualiza cada noche."

---

## 16. Demo en vivo (comandos útiles)

```bash
# Ver cuántos modelos activos hay
python manage.py shell -c "from forecast.models import ForecastModel; print(ForecastModel.objects.filter(is_active=True).count())"

# Ver distribución de algoritmos ganadores
python manage.py shell -c "
from forecast.models import ForecastModel
from collections import Counter
active = ForecastModel.objects.filter(is_active=True)
print(Counter(m.algorithm for m in active))
"

# Entrenar un producto específico (con verbose logging)
python manage.py train_forecast_models --product 42 --tenant 1

# Backfill de accuracy tracking (últimos 7 días)
python manage.py track_forecast_accuracy --days 7

# Ver MAPE promedio del último training
python manage.py shell -c "
from forecast.models import ForecastTrainingLog
log = ForecastTrainingLog.objects.latest('finished_at')
print(f'MAPE promedio: {log.avg_mape}, modelos: {log.models_trained}')
"
```

---

## 17. Stack técnico que menciono si preguntan

- **Lenguaje**: Python 3.12
- **Framework backend**: Django 5.1 + DRF
- **Storage**: PostgreSQL 16 (DB principal)
- **Librerías ML**:
  - `statsmodels` (Holt-Winters, ETS)
  - `pandas` para agregaciones (aggregate_daily_sales)
  - Algoritmos custom en Python puro (sin sklearn — intencional, para portabilidad)
- **Orchestración**: cron de Linux + Django management commands
- **Testing**: pytest con 995 tests, 12 específicos de forecast (algoritmos + integración)

---

## 18. Cheat sheet para último minuto

### Fórmulas rápidas
- OLS: `β̂ = (XᵀX)⁻¹Xᵀy`
- MAE: `(1/n) Σ|y - ŷ|`
- RMSE: `√((1/n) Σ(y - ŷ)²)`
- MAPE: `(100/n) Σ|y - ŷ|/y` (sólo para y>0)
- R²: `1 - SS_res/SS_tot`
- Sigmoid: `σ(x) = 1/(1 + e^-x)`
- ReLU: `max(0, x)`, derivada = 1 si x>0, 0 si no
- Cross-entropy: `-Σ yᵢ log(ŷᵢ)`

### Conceptos a tener frescos
- **Bias-variance tradeoff**: más complejidad ↓ bias pero ↑ variance
- **Curse of dimensionality**: features crecen linealmente, data necesaria exponencialmente
- **No free lunch theorem**: no hay un algoritmo mejor para todo
- **Central limit theorem**: suma de variables aleatorias tiende a normal
- **Bayes**: P(H|D) = P(D|H)·P(H)/P(D)

### Librerías que debería mencionar conocer
- `numpy`, `pandas`, `scikit-learn`
- `statsmodels` (lo uso)
- `tensorflow`/`keras` o `pytorch`
- `prophet` (Facebook's forecast — alternativa a Theta/HW)
- `xgboost`/`lightgbm` (gradient boosting, MUY usado en tabular)
- `matplotlib`/`seaborn` para plots

### Algoritmos que debería poder enumerar sin pensar
**Supervised**:
- Regresión: OLS, Ridge, Lasso, Elastic Net
- Clasificación: Logistic regression, SVM, Decision trees, Random Forest, XGBoost, KNN, Naive Bayes, Redes neuronales

**Unsupervised**:
- Clustering: K-means, DBSCAN, Hierarchical
- Dim reduction: PCA, t-SNE, UMAP

**Series temporales**:
- ARIMA, SARIMA, Exponential Smoothing (ETS/Holt-Winters), Theta, Prophet, LSTM, Transformer (Time-series Transformer/TFT)

**Deep learning**:
- Feedforward (MLP), CNN, RNN/LSTM/GRU, Transformer, GAN, Autoencoder, VAE

---

## 19. Checklist antes de la entrevista

- [ ] Repasar esta guía 1 vez hoy y 1 vez mañana temprano
- [ ] Tener el laptop con el código abierto en `apps/api/forecast/`
- [ ] Poder mostrar `select_best_model()` y explicar el flujo en vivo
- [ ] Tener el archivo `ForecastTrainingLog` más reciente a mano (número concreto de modelos entrenados)
- [ ] Mockup mental del diagrama: **cron → aggregate → classify → train candidatos → backtest → elegir → enhance → guardar → track al día siguiente**
- [ ] Si preguntan algo que no sé: "No lo he implementado pero conceptualmente X"; o "Lo consultaría en la documentación — conozco los fundamentos pero no los detalles exactos"
- [ ] Cierre posible: *"Me interesa particularmente esta posición porque Pulstock me llevó a resolver problemas reales de series temporales con data limitada — y me falta formalizar más ese conocimiento en un entorno con mentoring."*
