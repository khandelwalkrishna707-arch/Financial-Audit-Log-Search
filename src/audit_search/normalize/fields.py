"""Clean the non-date fields: text, action types and money amounts."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Removed before parsing: spaces, thousands commas and currency symbols. "₹ 1,234.50" -> "1234.50"
_NOISE = re.compile(r"[\s,$€£₹¥]")
_CENT = Decimal("0.01")
# SQLite's INTEGER holds at most 2**63 - 1, so larger amounts are rejected instead of crashing.
_MAX_AMOUNT = Decimal(2**63 - 1).scaleb(-2)


def clean_text(value: object) -> str | None:
    """Trim whitespace. Empty values become None. Numbers (from JSON) become text."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_action(value: object) -> str:
    """'deposit', ' Deposit ', 'loan-repayment' -> 'DEPOSIT', 'DEPOSIT', 'LOAN_REPAYMENT'.

    Fineract sometimes sends the type as an object like {"value": "Deposit"}; we take its value.
    Unknown/missing action becomes "" because the column is part of the duplicate key.
    """
    if isinstance(value, dict):
        value = value.get("value") or value.get("code")
    text = clean_text(value)
    if text is None:
        return ""
    return re.sub(r"[\s\-]+", "_", text).upper()


def parse_amount_cents(value: object) -> int | None:
    """Convert an amount to whole cents: "1,234.50" -> 123450. Missing amount -> None.

    Uses Decimal, never float, so 0.10 + 0.20 stays exactly 0.30.
    Raises ValueError for text that is not a number, that has more than 2 decimal
    places (rejecting is safer than silently rounding someone's money), or that is too
    large to store.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"not a number: {value!r}")

    if isinstance(value, (int, Decimal)):
        number = Decimal(value)
    elif isinstance(value, float):
        number = Decimal(repr(value))
    else:
        text = str(value).strip()
        if not text:
            return None
        negative = text.startswith("(") and text.endswith(")")  # accounting style: (12.50)
        if negative:
            text = text[1:-1]
        text = _NOISE.sub("", text)
        try:
            number = Decimal(text)
        except InvalidOperation:
            raise ValueError(f"not a number: {value!r}") from None
        if negative:
            number = -number

    if not number.is_finite():
        raise ValueError(f"not a finite number: {value!r}")
    if number.copy_abs() > _MAX_AMOUNT:
        raise ValueError(f"amount is too large: {value!r}")
    # quantize() keeps exactly 2 decimals; if that changed the value, it had more than 2.
    # (Comparing is exact, unlike `number * 100`, which rounds after 28 digits.)
    two_decimals = number.quantize(_CENT)
    if two_decimals != number:
        raise ValueError(f"more than 2 decimal places: {value!r}")
    return int(two_decimals.scaleb(2))  # 12.50 -> 1250


def cents_to_str(cents: int | None) -> str:
    """123450 -> "1234.50"; None -> "". Use this when displaying or exporting amounts."""
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole}.{frac:02d}"
