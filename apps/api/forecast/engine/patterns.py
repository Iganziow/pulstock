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


def classify_demand_pattern(daily_series):
    """
    Classify demand pattern using ADI-CV² framework + density check.

    Returns:
        (pattern, adi, cv2) where pattern is one of:
        - "smooth": regular demand (ADI < 1.32 AND density >= 30%)
        - "intermittent": infrequent but consistent sizes
                          (ADI >= 1.32 OR density < 30%, CV² < 0.49)
        - "lumpy": infrequent with variable sizes
                   (ADI >= 1.32 OR density < 30%, CV² >= 0.49)
        - "insufficient": not enough non-zero observations
    """
    non_zero = [(d, float(q)) for d, q, *_ in daily_series if float(q) > 0]
    if len(non_zero) < 3:
        return "insufficient", 0, 0

    intervals = []
    for i in range(1, len(non_zero)):
        intervals.append((non_zero[i][0] - non_zero[i - 1][0]).days)
    adi = sum(intervals) / len(intervals) if intervals else 1.0

    sizes = [q for _, q in non_zero]
    mean_size = sum(sizes) / len(sizes)
    if mean_size <= 0:
        return "insufficient", adi, 0

    variance = sum((s - mean_size) ** 2 for s in sizes) / len(sizes)
    cv2 = variance / (mean_size ** 2)

    # ── Density check ──────────────────────────────────────────────
    # Calculamos el porcentaje de días TOTALES (no solo los con consumo)
    # que tuvieron venta. Solo aplica si tenemos suficientes días de data
    # para que el ratio sea significativo.
    total_days = len(daily_series)
    density = len(non_zero) / total_days if total_days > 0 else 0
    is_sparse_by_density = (
        total_days >= MIN_DAYS_FOR_DENSITY_CHECK
        and density < INTERMITTENT_DENSITY_THRESHOLD
    )

    # Intermitente si CUALQUIERA de las condiciones se cumple:
    #   - ADI clásico >= 1.32 (intervalos largos entre consumos)
    #   - Densidad baja (pocos días con consumo respecto al total)
    is_intermittent = adi >= 1.32 or is_sparse_by_density

    if is_intermittent:
        return ("lumpy" if cv2 >= 0.49 else "intermittent"), round(adi, 2), round(cv2, 3)
    return "smooth", round(adi, 2), round(cv2, 3)
