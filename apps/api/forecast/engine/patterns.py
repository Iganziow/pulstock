"""
Demand pattern classification (ADI-CV² framework).
"""


def classify_demand_pattern(daily_series):
    """
    Classify demand pattern using ADI-CV² framework.

    Returns:
        (pattern, adi, cv2) where pattern is one of:
        - "smooth": regular demand (ADI < 1.32)
        - "intermittent": infrequent but consistent sizes (ADI >= 1.32, CV² < 0.49)
        - "lumpy": infrequent with variable sizes (ADI >= 1.32, CV² >= 0.49)
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

    if adi >= 1.32:
        return ("lumpy" if cv2 >= 0.49 else "intermittent"), round(adi, 2), round(cv2, 3)
    return "smooth", round(adi, 2), round(cv2, 3)
