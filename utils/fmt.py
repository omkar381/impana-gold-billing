"""utils/fmt.py — number formatting shared by the web app and WhatsApp messages."""

from decimal import Decimal


def inr(value, decimals: int = 0) -> str:
    """12345678 -> '1,23,45,678' (Indian digit grouping)."""
    n = Decimal(str(value or 0))
    text = f"{abs(n):.{decimals}f}"
    whole, _, frac = text.partition(".")
    if len(whole) > 3:
        head, tail, groups = whole[:-3], whole[-3:], []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if n < 0 else "") + whole + ("." + frac if frac else "")
