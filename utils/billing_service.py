"""
utils/billing_service.py — the one place a counter bill is calculated and saved.

Both the desktop billing screen (/bill/create) and the owner's phone app
(/b/api/bills) call save_bill(), so GST, stock, bill numbers and the audit
trail can never drift between the two.

save_bill() raises BillError for anything the caller should show to the user
(bad cart, no stock, ...). The route decides how to present it.
"""

from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from models import Bill, BillItem, Customer, MarketingOfficer, Product
from utils.audit import log_action
from utils.bill_number import generate_bill_number
from utils.stock import apply_stock_change
from utils.timeutil import today_ist

PAYMENT_MODES = ("cash", "upi", "card", "credit")


class BillError(ValueError):
    """A problem with the bill the user can read and fix. `status` is the HTTP code."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def save_bill(data: dict, operator_id: int, ip_address: str = None) -> Bill:
    """Validate the cart in `data`, calculate totals, and save the bill.

    `data` has the same shape the desktop screen has always sent:
      items[{product_id, qty, unit_price, is_loose}], payment_mode, discount_type,
      discount_amount, amount_paid, notes, customer_id / customer_name /
      customer_phone / customer_address / customer_gstin, marketing_officer_id,
      apply_overall_gst, overall_gst_rate, status.
    """
    # Imported here because billing.routes imports this module.
    from billing.routes import get_all_settings, upsert_daily_summary

    try:
        return _save_bill(data, operator_id, ip_address, get_all_settings, upsert_daily_summary)
    except BillError:
        db.session.rollback()
        raise


def _save_bill(data, operator_id, ip_address, get_all_settings, upsert_daily_summary) -> Bill:
    # ── Validation ────────────────────────────────────────────────────────
    items_data = data.get("items", [])
    if not items_data:
        raise BillError("Cart is empty.")

    payment_mode = data.get("payment_mode", "cash")
    if payment_mode not in PAYMENT_MODES:
        raise BillError("Invalid payment mode.")

    # ── Resolve customer (optional) ───────────────────────────────────────
    customer = None
    customer_id = data.get("customer_id")
    customer_name = (data.get("customer_name") or "").strip()
    customer_phone = (data.get("customer_phone") or "").strip()
    customer_address = (data.get("customer_address") or "").strip()
    customer_gstin = (data.get("customer_gstin") or "").strip()

    if customer_id:
        customer = db.session.get(Customer, int(customer_id))

    if not customer and (customer_phone or customer_gstin):
        lookup = Customer.query.filter(Customer.deleted_at == None)  # noqa: E711
        if customer_phone:
            customer = lookup.filter(Customer.phone == customer_phone).first()
        if not customer and customer_gstin:
            customer = lookup.filter(Customer.gstin == customer_gstin).first()

    if not customer and customer_name:
        customer = Customer(
            name=customer_name,
            phone=customer_phone or None,
            address=customer_address or None,
            gstin=customer_gstin or None,
        )
        db.session.add(customer)

    if customer:
        if customer_name:
            customer.name = customer_name
        if customer_phone:
            customer.phone = customer_phone
        if customer_address:
            customer.address = customer_address
        if customer_gstin:
            customer.gstin = customer_gstin

    # ── Marketing officer (optional) — snapshot name/phone onto the bill ──
    officer = None
    try:
        officer_id = int(data.get("marketing_officer_id") or 0)
    except (TypeError, ValueError):
        officer_id = 0
    if officer_id:
        officer = db.session.get(MarketingOfficer, officer_id)

    # ── Calculate totals ──────────────────────────────────────────────────
    subtotal = Decimal("0.00")
    gst_amount = Decimal("0.00")
    bill_items = []
    stock_items = []

    for item in items_data:
        product = db.session.get(Product, int(item["product_id"]))
        if not product or not product.is_active or product.deleted_at:
            continue

        qty = Decimal(str(item["qty"])).quantize(Decimal("0.001"), ROUND_HALF_UP)
        # Allow custom rate from the cart; fall back to the product default
        custom_price = item.get("unit_price")
        if custom_price is not None and float(custom_price) > 0:
            unit_price = Decimal(str(custom_price)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            unit_price = product.price_per_unit
        is_loose = item.get("is_loose") in (True, "true", "1", 1)
        gst_rate = product.gst_rate
        if not is_loose and product.unit == "kg" and qty >= 30 and qty % Decimal("30") == 0:
            gst_rate = Decimal("0.00")
        line_total = (qty * unit_price).quantize(Decimal("0.01"), ROUND_HALF_UP)
        line_gst = (line_total * gst_rate / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        product_name = product.name + (" (Loose)" if is_loose else "")

        subtotal += line_total
        gst_amount += line_gst

        bill_items.append(
            BillItem(
                product_id=product.id,
                product_name=product_name,           # snapshot
                unit_price=unit_price,               # snapshot
                qty=qty,
                unit=product.unit,                   # snapshot
                gst_rate=gst_rate,                   # snapshot
                hsn_code=product.hsn_code,           # snapshot
                line_total=line_total,
            )
        )
        stock_items.append((product, qty))

    if not bill_items:
        raise BillError("No valid products in cart.")

    # ── Discount ──────────────────────────────────────────────────────────
    discount_type = data.get("discount_type", "flat")
    raw_discount = Decimal(str(data.get("discount_amount", 0)))

    if discount_type == "percent":
        discount_amount = (subtotal * raw_discount / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
    else:
        discount_amount = raw_discount.quantize(Decimal("0.01"), ROUND_HALF_UP)

    discount_amount = min(discount_amount, subtotal)
    taxable_amount = subtotal - discount_amount

    settings = get_all_settings()
    gst_enabled = settings.get("gst_enabled", "true").lower() == "true"

    # Override GST: if the customer asks for one overall rate, use that instead of per-product
    apply_overall_gst = data.get("apply_overall_gst", False)
    if apply_overall_gst and gst_enabled:
        overall_gst_rate = Decimal(str(data.get("overall_gst_rate", 5)))
        gst_amount = (taxable_amount * overall_gst_rate / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
    elif not gst_enabled:
        gst_amount = Decimal("0.00")

    grand_total = taxable_amount + gst_amount
    if grand_total <= 0:
        raise BillError("Grand total must be greater than 0.")

    amount_paid = Decimal(str(data.get("amount_paid", grand_total)))
    change_returned = max(amount_paid - grand_total, Decimal("0.00"))

    # ── Bill number (with retry) ──────────────────────────────────────────
    prefix = settings.get("bill_prefix", "IG")
    reset_policy = settings.get("bill_counter_reset", "daily")

    bill_number = None
    for _ in range(10):
        candidate = generate_bill_number(prefix=prefix, reset_policy=reset_policy)
        if not Bill.query.filter_by(bill_number=candidate).first():
            bill_number = candidate
            break

    if not bill_number:
        raise BillError("Could not generate a unique bill number.", 500)

    # ── Build and save bill ───────────────────────────────────────────────
    status = data.get("status", "confirmed")
    bill = Bill(
        bill_number=bill_number,
        customer=customer,
        operator_id=operator_id,
        subtotal=subtotal,
        discount_amount=discount_amount,
        discount_type=discount_type,
        taxable_amount=taxable_amount,
        gst_amount=gst_amount,
        grand_total=grand_total,
        payment_mode=payment_mode,
        amount_paid=amount_paid,
        change_returned=change_returned,
        notes=data.get("notes", ""),
        status=status,
        marketing_officer_name=officer.name if officer else None,
        marketing_officer_phone=(officer.phone or None) if officer else None,
        marketing_officer_id=officer.id if officer else None,
    )

    try:
        db.session.add(bill)
        db.session.flush()  # get bill.id

        for item in bill_items:
            item.bill_id = bill.id
            db.session.add(item)

        if status == "confirmed":
            for product, qty in stock_items:
                apply_stock_change(
                    product=product,
                    delta_qty=-qty,
                    actor_id=operator_id,
                    reason="sale",
                    reference_type="bill",
                    reference_id=bill.id,
                    note=f"Bill {bill.bill_number}",
                )
            upsert_daily_summary(bill.bill_date.date() if hasattr(bill.bill_date, "date") else today_ist())

        log_action(
            actor_id=operator_id,
            action="CREATE",
            entity="bill",
            entity_id=bill.id,
            new_val={"bill_number": bill_number, "grand_total": float(grand_total)},
            ip_address=ip_address,
        )

        db.session.commit()

    except ValueError as exc:
        db.session.rollback()
        raise BillError(str(exc)) from exc
    except Exception as exc:
        db.session.rollback()
        raise BillError(f"Database error: {exc}", 500) from exc

    return bill
