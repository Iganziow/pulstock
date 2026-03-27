# catalog/services.py — agregar función:
def validate_ean13(code: str) -> bool:
    """Valida checksum EAN-13."""
    if not code.isdigit() or len(code) != 13:
        return False
    digits = [int(d) for d in code]
    total = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
    check = (10 - (total % 10)) % 10
    return check == digits[12]