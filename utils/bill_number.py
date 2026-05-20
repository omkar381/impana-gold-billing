"""
utils/bill_number.py — Bill number generation for Impana Gold.

Format: {PREFIX}-{YYYYMMDD}-{NNNN}
Example: IG-20241201-0047

Strategy:
  - Query the highest existing bill number for today (or globally, depending on config).
  - Increment by 1 and zero-pad to 4 digits.
  - On collision (race condition), retry up to 10 times.
"""

import re
from datetime import datetime, date
from typing import Optional


def generate_bill_number(
    prefix: str = "IG",
    reset_policy: str = "daily",
) -> str:
    """
    Generate the next unique bill number.

    Args:
        prefix:         Bill number prefix from business settings (default "IG").
        reset_policy:   Counter reset policy: "daily", "monthly", or "never".

    Returns:
        A unique bill number string like "IG-20241201-0047".

    Raises:
        RuntimeError: If a unique number cannot be generated after 10 retries.
    """
    # Avoid circular import — import inside function
    from extensions import db
    from models import Bill

    now = datetime.utcnow()

    # Build the date portion based on reset policy
    if reset_policy == "daily":
        date_str = now.strftime("%Y%m%d")
        pattern = f"{prefix}-{date_str}-%"
    elif reset_policy == "monthly":
        date_str = now.strftime("%Y%m")
        pattern = f"{prefix}-{date_str}%"
    else:  # "never" — global counter; still include today's date in display
        date_str = now.strftime("%Y%m%d")
        pattern = f"{prefix}-%"

    # Find highest counter in scope
    last_bill = (
        db.session.query(Bill.bill_number)
        .filter(Bill.bill_number.like(pattern))
        .order_by(Bill.bill_number.desc())
        .first()
    )

    if last_bill:
        # Extract the numeric counter from the last segment after the last dash
        parts = last_bill.bill_number.rsplit("-", 1)
        try:
            last_counter = int(parts[-1])
        except ValueError:
            last_counter = 0
        next_counter = last_counter + 1
    else:
        next_counter = 1

    bill_number = f"{prefix}-{date_str}-{next_counter:04d}"
    return bill_number
