"""
utils/bill_link.py — the private link that is sent to a buyer on WhatsApp.

The link carries the bill id signed with the app's SECRET_KEY, so nobody can
guess or count up to another buyer's bill. No database column is needed, and
changing SECRET_KEY invalidates every link ever sent.
"""

import hashlib
import re
from urllib.parse import quote

from flask import current_app, url_for
from itsdangerous import BadSignature, URLSafeSerializer

from utils.fmt import inr


# Name given to a buyer saved with just a mobile number. Never used as a greeting.
UNNAMED_BUYER = "Customer"


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(
        current_app.secret_key, salt="impana-bill-link",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def bill_token(bill_id: int) -> str:
    return _serializer().dumps(int(bill_id))


def bill_id_from_token(token: str):
    try:
        value = _serializer().loads(token)
    except BadSignature:
        return None
    return value if isinstance(value, int) else None


def bill_url(bill) -> str:
    """Absolute link to the buyer's copy of the bill."""
    return url_for("billing.shared_bill", token=bill_token(bill.id), _external=True)


def phone10(value) -> str:
    """Last ten digits of whatever was typed: '+91 98765-43210' -> '9876543210'."""
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return digits[-10:]


def is_mobile(value) -> bool:
    return bool(re.fullmatch(r"[6-9]\d{9}", phone10(value))) and len(
        "".join(ch for ch in (value or "") if ch.isdigit())
    ) in (10, 11, 12)


def whatsapp_url(bill, shop_name: str = "Impana Gold", phone=None) -> str:
    """wa.me link that opens the buyer's chat with the message already typed.

    Without a usable number it opens WhatsApp's contact picker instead.
    """
    name = (bill.customer.name.strip() if bill.customer and bill.customer.name else "")
    if name == UNNAMED_BUYER:
        name = ""
    greeting = f"Hello {name}," if name else "Hello,"
    text = (
        f"{greeting}\n"
        f"Thank you for shopping at {shop_name}.\n"
        f"Your bill {bill.bill_number} for ₹{inr(bill.grand_total, 2)} is ready:\n"
        f"{bill_url(bill)}"
    )
    number = phone10(phone if phone is not None else (bill.customer.phone if bill.customer else ""))
    target = f"91{number}" if is_mobile(number) else ""
    return f"https://wa.me/{target}?text={quote(text, safe='')}"
