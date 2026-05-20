"""
utils/num_to_words.py — Convert numbers to Indian-English words for invoices.

Examples:
    4490.00  → "FOUR THOUSAND FOUR HUNDRED AND NINETY RUPEES ONLY"
    684.90   → "SIX HUNDRED AND EIGHTY-FOUR RUPEES AND NINETY PAISA ONLY"
    1250.50  → "ONE THOUSAND TWO HUNDRED AND FIFTY RUPEES AND FIFTY PAISA ONLY"
"""

from decimal import Decimal, ROUND_HALF_UP


_ONES = [
    "", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE",
    "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN",
    "SEVENTEEN", "EIGHTEEN", "NINETEEN",
]

_TENS = [
    "", "", "TWENTY", "THIRTY", "FORTY", "FIFTY",
    "SIXTY", "SEVENTY", "EIGHTY", "NINETY",
]


def _two_digits(n: int) -> str:
    """Convert a number 0-99 to words."""
    if n == 0:
        return ""
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    if ones:
        return f"{_TENS[tens]}-{_ONES[ones]}"
    return _TENS[tens]


def _three_digits(n: int) -> str:
    """Convert a number 0-999 to words."""
    if n == 0:
        return ""
    hundreds, remainder = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_ONES[hundreds]} HUNDRED")
    if remainder:
        if hundreds:
            parts.append("AND")
        parts.append(_two_digits(remainder))
    return " ".join(parts)


def _int_to_words_indian(n: int) -> str:
    """
    Convert an integer to Indian-English words.
    Indian system: ones/tens/hundreds, then thousands (2 digits), lakhs (2 digits), crores...
    """
    if n == 0:
        return "ZERO"

    parts = []

    # Crores (everything above 99,99,999)
    if n >= 10_000_000:
        crores = n // 10_000_000
        n %= 10_000_000
        parts.append(f"{_int_to_words_indian(crores)} CRORE")

    # Lakhs (2 digits: 00,00,000 to 99,00,000)
    if n >= 100_000:
        lakhs = n // 100_000
        n %= 100_000
        parts.append(f"{_two_digits(lakhs)} LAKH")

    # Thousands (2 digits: 0,000 to 99,000)
    if n >= 1_000:
        thousands = n // 1_000
        n %= 1_000
        parts.append(f"{_two_digits(thousands)} THOUSAND")

    # Hundreds, tens, ones
    if n > 0:
        remainder_words = _three_digits(n)
        # Add "AND" connector if there were higher groups and remainder < 100
        if parts and n < 100:
            parts.append(f"AND {remainder_words}")
        else:
            parts.append(remainder_words)

    return " ".join(parts)


def num_to_words(amount) -> str:
    """
    Convert a monetary amount to Indian-English words for invoices.

    Args:
        amount: Number (int, float, Decimal, or string)

    Returns:
        String like "ONE THOUSAND TWO HUNDRED AND FIFTY RUPEES AND FIFTY PAISA ONLY"
    """
    dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if dec < 0:
        dec = abs(dec)

    rupees = int(dec)
    paise = int((dec - rupees) * 100)

    parts = []

    if rupees > 0:
        parts.append(f"{_int_to_words_indian(rupees)} RUPEES")
    elif paise == 0:
        return "ZERO RUPEES ONLY"

    if paise > 0:
        if parts:
            parts.append("AND")
        parts.append(f"{_two_digits(paise)} PAISA")

    parts.append("ONLY")
    return " ".join(parts)
