"""Parse PRONOTE numeric strings without replacing their original values."""

from decimal import Decimal, InvalidOperation
import math


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(Decimal(str(value).strip().replace("\u00a0", "").replace(",", ".")))
    except (InvalidOperation, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def grade_values(grade, out_of, coefficient=None):
    value, maximum = number(grade), number(out_of)
    return {"grade_numeric": value, "out_of_numeric": maximum,
            "coefficient_numeric": number(coefficient),
            "grade_on_20": round(value * 20 / maximum, 6) if value is not None and maximum is not None and maximum > 0 else None}
