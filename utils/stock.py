"""
utils/stock.py - Inventory stock adjustment helpers.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from extensions import db
from models import InventoryTransaction


def apply_stock_change(
    product,
    delta_qty,
    actor_id: int,
    reason: str,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    note: Optional[str] = None,
) -> Tuple[Decimal, Decimal]:
    """
    Apply a stock change and log an inventory transaction.

    Args:
        product: Product instance
        delta_qty: Positive for restock, negative for deduction
        actor_id: AdminUser id
        reason: sale, restock, adjust, cancel
        reference_type: bill, warehouse, etc.
        reference_id: id of reference entity
        note: Optional note

    Returns:
        (before_qty, after_qty)
    """
    before = Decimal(str(product.stock_qty or 0)).quantize(Decimal("0.001"))
    delta = Decimal(str(delta_qty)).quantize(Decimal("0.001"), ROUND_HALF_UP)
    after = (before + delta).quantize(Decimal("0.001"), ROUND_HALF_UP)

    if after < 0:
        raise ValueError(f"Insufficient stock for {product.name}.")

    product.stock_qty = after

    txn = InventoryTransaction(
        product_id=product.id,
        actor_id=actor_id,
        change_qty=delta,
        before_qty=before,
        after_qty=after,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )
    db.session.add(txn)

    return before, after
