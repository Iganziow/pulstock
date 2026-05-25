"""
Demand pattern classification (ADI-CV² framework + density check).
"""

# Si menos de este % de días tuvo consumo > 0, el producto es intermitente
# por densidad (independiente del ADI, que puede ser engañoso con poca data).
# Detectado el 13/05/26: con 14 días de historia, productos como "Vasos
# chicos" (que se usan 1-2 veces/semana) quedaban como "smooth" porque
# el ADI sobre los pocos días con consumo era < 1.32. Agregar el check
# de densidad mueve esos productos a Croston.
INTERMITTENT_DENSITY_THRESHOLD = 0.30  # 30%
MIN_DAYS_FOR_DENSITY_CHECK = 7  # con menos de 7 días no hay confianza

# Parametros para detectar dias-de-la-semana sistematicamente cerrados.
CLOSED_DOW_MIN_OCCURRENCES = 4
CLOSED_DOW_SALE_THRESHOLD = 0.10


def detect_closed_weekdays(daily_series,
                            min_occurrences=CLOSED_DOW_MIN_OCCURRENCES,
                            sale_threshold=CLOSED_DOW_SALE_THRESHOLD):
    """Devuelve el set de DOWs (0=lunes..6=domingo) sistematicamente cerrados.

    Un DOW se considera "cerrado" si aparece >= min_occurrences veces en la
    serie y en menos del sale_threshold (10%) de esas veces hubo venta.

    Ejemplos:
    - Marbrava cierra los lunes → {0}
    - Restaurante cierra dom + lun → {0, 6}

    Esto se usa para:
    - Clasificar correctamente productos que venden todos los dias-abiertos
      como smooth (no intermittent por culpa de los gaps de dias cerrados).
    - Permitir a Holt-Winters auto-descartarse cuando hay dias cerrados
      (ver `_has_closed_weekday` en algorithms/holt_winters.py).
    """
    by_dow = {}  # dow -> [n_ocurrencias, n_con_venta]
    for item in daily_series:
        d, qty = item[0], item[1]
        if not hasattr(d, "weekday"):
            continue
        dow = d.weekday()
        cell = by_dow.setdefault(dow, [0, 0])
        cell[0] += 1
        if float(qty) > 0:
            cell[1] += 1
    closed = set()
    for dow, (n, sold) in by_dow.items():
        if n >= min_occurrences and (sold / n) < sale_threshold:
            closed.add(dow)
    return closed


def classify_demand_pattern(daily_series, closed_weekdays=None):
    """
    Classify demand pattern using ADI-CV² framework + density check.

    Args:
        daily_series: list of (date, qty[, weight]) tuples
        closed_weekdays: opcional set de DOWs cerrados (lun=0..dom=6). Si se
            pasa, esos dias se EXCLUYEN del calculo de ADI/density — para
            negocios que cierran X dias de la semana, no contamos esos
            gaps como "huecos de demanda". Auto-detectable con
            `detect_closed_weekdays(daily_series)`.

    Returns:
        (pattern, adi, cv2) where pattern is one of:
        - "smooth": regular demand (ADI < 1.32 AND density >= 30%)
        - "intermittent": infrequent but consistent sizes
                          (ADI >= 1.32 OR density < 30%, CV² < 0.49)
        - "lumpy": infrequent with variable sizes
                   (ADI >= 1.32 OR density < 30%, CV² >= 0.49)
        - "insufficient": not enough non-zero observations

    BUGFIX FASE 4 (25/05/26)
    ========================
    Productos como Capuccino, Latte, Cortado en Marbrava (que cierra lunes)
    quedaban como "intermittent/lumpy" porque el ADI se calculaba en calendar
    days. Con 1 dia cerrado por semana, el gap promedio entre ventas era ~1.5
    calendar days (=14 dias venta / 7 dias real entre vts) — ADI sobre 1.32 →
    Croston_SBA → WAPE 100-450%.

    Fix: pasar closed_weekdays al classifier para que filtre esos dias del
    business calendar antes de calcular ADI y density. Sin parametro,
    comportamiento idéntico al anterior (back-compat).
    """
    closed_weekdays = closed_weekdays or set()

    # Business calendar: serie sin dias cerrados sistematicamente.
    if closed_weekdays:
        business_series = [
            item for item in daily_series
            if hasattr(item[0], "weekday") and item[0].weekday() not in closed_weekdays
        ]
    else:
        business_series = list(daily_series)

    # Indices (en business days) de las observaciones con venta > 0.
    non_zero_idx = [i for i, item in enumerate(business_series) if float(item[1]) > 0]
    if len(non_zero_idx) < 3:
        return "insufficient", 0, 0

    # ADI: intervalos entre ventas en BUSINESS days (no calendar days).
    # Asi, lunes cerrado entre dos ventas consecutivas NO infla el ADI.
    intervals = [non_zero_idx[i] - non_zero_idx[i - 1] for i in range(1, len(non_zero_idx))]
    adi = sum(intervals) / len(intervals) if intervals else 1.0

    sizes = [float(business_series[i][1]) for i in non_zero_idx]
    mean_size = sum(sizes) / len(sizes)
    if mean_size <= 0:
        return "insufficient", adi, 0

    variance = sum((s - mean_size) ** 2 for s in sizes) / len(sizes)
    cv2 = variance / (mean_size ** 2)

    # ── Density check ──────────────────────────────────────────────
    # Sobre BUSINESS days (no calendar days). Si Marbrava abre 6/7 dias,
    # un producto que vende 4 de esos 6 dias tiene density 4/6 = 67%
    # (antes el calculo sobre 7 dias daba 4/7 = 57% — practicamente
    # igual, pero con mas dias cerrados la diferencia importa mas).
    business_days = len(business_series)
    density = len(non_zero_idx) / business_days if business_days > 0 else 0
    is_sparse_by_density = (
        business_days >= MIN_DAYS_FOR_DENSITY_CHECK
        and density < INTERMITTENT_DENSITY_THRESHOLD
    )

    # Intermitente si CUALQUIERA de las condiciones se cumple:
    #   - ADI clásico >= 1.32 (intervalos largos entre consumos)
    #   - Densidad baja (pocos días con consumo respecto al total)
    is_intermittent = adi >= 1.32 or is_sparse_by_density

    if is_intermittent:
        return ("lumpy" if cv2 >= 0.49 else "intermittent"), round(adi, 2), round(cv2, 3)
    return "smooth", round(adi, 2), round(cv2, 3)
