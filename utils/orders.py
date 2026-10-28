"""
utils/orders.py — Officer order requests and their approval.

Safety rules enforced here (never in the browser):
  * Prices always come from the product list; an officer cannot set a rate.
  * A request is NOT a bill: no bill number, no stock movement, no sales credit.
  * Only the superadmin can approve. Approving creates the real bill, deducts
    stock and credits the officer; rejecting keeps the request on record.
  * Requests are never deleted — only pending, cancelled, approved or rejected.
"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Bill, BillItem, Customer, OrderRequest, OrderRequestItem, Product
from utils.audit import log_action
from utils.bill_number import generate_bill_number
from utils.officer_stats import attributed
from utils.stock import apply_stock_change
from utils.timeutil import now_ist

PAYMENT_MODES = ("cash", "upi", "card", "credit")
MAX_PENDING = 10          # open requests per officer (stops spamming the inbox)
MAX_ITEMS = 40
MAX_QTY = Decimal("100000")


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _qty(value) -> Decimal:
    try:
        q = Decimal(str(value)).quantize(Decimal("0.001"), ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("Quantity must be a number.")
    return q


def digits10(value) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return digits[-10:]


def is_bag_qty(unit, qty) -> bool:
    """30 kg bags: whole multiples of 30 kg (taxed at 0%, same rule as the POS)."""
    return unit == "kg" and qty >= 30 and qty % Decimal("30") == 0


def next_request_number() -> str:
    prefix = f"OR-{now_ist().strftime('%Y%m%d')}-"
    last = (
        db.session.query(OrderRequest.request_number)
        .filter(OrderRequest.request_number.like(prefix + "%"))
        .order_by(OrderRequest.request_number.desc())
        .first()
    )
    n = int(last[0].rsplit("-", 1)[-1]) + 1 if last else 1
    return f"{prefix}{n:04d}"


def officer_has_shop(officer, customer_id) -> bool:
    return (
        db.session.query(Bill.id)
        .filter(attributed(officer), Bill.customer_id == customer_id)
        .first()
        is not None
    )


# ── Officer: submit / cancel ───────────────────────────────────────────────

def create_order_request(officer, data) -> OrderRequest:
    pending = OrderRequest.query.filter_by(officer_id=officer.id, status="pending").count()
    if pending >= MAX_PENDING:
        raise ValueError(f"You already have {MAX_PENDING} orders waiting for approval. Wait for them to be reviewed.")

    payment_mode = (data.get("payment_mode") or "cash").lower()
    if payment_mode not in PAYMENT_MODES:
        raise ValueError("Choose a valid payment mode.")

    # Shop: one of this officer's own shops, or a proposed new one
    customer = None
    new_shop = {}
    customer_id = data.get("customer_id")
    if customer_id:
        try:
            customer_id = int(customer_id)
        except (TypeError, ValueError):
            raise ValueError("Choose a valid shop.")
        customer = db.session.get(Customer, customer_id)
        if not customer or customer.deleted_at or not officer_has_shop(officer, customer_id):
            raise ValueError("Choose one of your shops, or add a new shop.")
    else:
        shop = data.get("new_customer") or {}
        name = (shop.get("name") or "").strip()
        phone = digits10(shop.get("phone"))
        if len(name) < 2:
            raise ValueError("Enter the shop name.")
        if len(phone) != 10:
            raise ValueError("Enter the shop's 10-digit phone number.")
        new_shop = {
            "new_customer_name": name[:200],
            "new_customer_phone": phone,
            "new_customer_address": (shop.get("address") or "").strip()[:500] or None,
            "new_customer_gstin": (shop.get("gstin") or "").strip().upper()[:20] or None,
        }

    # Items: price is taken from the product list, never from the request
    raw_items = data.get("items") or []
    if not raw_items:
        raise ValueError("Add at least one product.")
    if len(raw_items) > MAX_ITEMS:
        raise ValueError("Too many items in one order.")

    merged = {}
    for raw in raw_items:
        try:
            pid = int(raw.get("product_id"))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Invalid product.")
        qty = _qty(raw.get("qty"))
        if qty <= 0 or qty > MAX_QTY:
            raise ValueError("Enter a valid quantity.")
        merged[pid] = merged.get(pid, Decimal("0")) + qty

    lines, total = [], Decimal("0.00")
    for pid, qty in merged.items():
        product = db.session.get(Product, pid)
        if not product or not product.is_active or product.deleted_at:
            raise ValueError("A product in your order is no longer available.")
        line_total = _money(qty * product.price_per_unit)
        total += line_total
        lines.append(
            OrderRequestItem(
                product_id=product.id, product_name=product.name, unit=product.unit,
                qty=qty, unit_price=product.price_per_unit, line_total=line_total,
            )
        )

    for _ in range(5):
        order = OrderRequest(
            request_number=next_request_number(),
            officer_id=officer.id,
            customer_id=customer.id if customer else None,
            payment_mode=payment_mode,
            notes=(data.get("notes") or "").strip()[:500] or None,
            estimated_total=total,
            status="pending",
            **new_shop,
        )
        order.items = lines
        db.session.add(order)
        try:
            db.session.commit()
            return order
        except IntegrityError:  # request number collision: try the next number
            db.session.rollback()
            lines = [
                OrderRequestItem(
                    product_id=l.product_id, product_name=l.product_name, unit=l.unit,
                    qty=l.qty, unit_price=l.unit_price, line_total=l.line_total,
                )
                for l in lines
            ]
    raise ValueError("Could not save the order. Please try again.")


def cancel_order(order, officer) -> None:
    if order.officer_id != officer.id:
        raise ValueError("Order not found.")
    if order.status != "pending":
        raise ValueError("Only orders that are still waiting can be cancelled.")
    order.status = "cancelled"
    order.decided_at = now_ist()
    order.decision_reason = "Cancelled by officer"
    order.seen_by_officer = True
    db.session.commit()


# ── Superadmin: approve / reject ───────────────────────────────────────────

def duplicate_hints(order):
    """Other recent requests from the same officer for the same shop and amount."""
    since = order.created_at - timedelta(hours=2)
    q = OrderRequest.query.filter(
        OrderRequest.id != order.id,
        OrderRequest.officer_id == order.officer_id,
        OrderRequest.status.in_(("pending", "approved")),
        OrderRequest.created_at >= since,
        OrderRequest.estimated_total == order.estimated_total,
    )
    if order.customer_id:
        q = q.filter(OrderRequest.customer_id == order.customer_id)
    else:
        q = q.filter(OrderRequest.new_customer_phone == order.new_customer_phone)
    return q.all()


def _resolve_customer(order) -> Customer:
    if order.customer:
        return order.customer
    phone = order.new_customer_phone
    customer = None
    if phone:
        customer = Customer.query.filter(Customer.phone.like("%" + phone)).first()
    if customer is None and order.new_customer_gstin:
        customer = Customer.query.filter_by(gstin=order.new_customer_gstin, deleted_at=None).first()
    if customer is None:
        customer = Customer(
            name=order.new_customer_name, phone=phone,
            address=order.new_customer_address, gstin=order.new_customer_gstin,
        )
        db.session.add(customer)
    elif customer.deleted_at:
        customer.deleted_at = None
    return customer


def approve_order(order, admin, payment_mode, edits=None) -> Bill:
    """Turn a pending request into a confirmed bill. Raises ValueError on any problem."""
    from billing.routes import get_all_settings, upsert_daily_summary  # avoid import cycle

    if order.status != "pending":
        raise ValueError("This order has already been reviewed.")
    if payment_mode not in PAYMENT_MODES:
        raise ValueError("Choose a valid payment mode.")
    edits = edits or {}

    settings = get_all_settings()
    gst_enabled = settings.get("gst_enabled", "true").lower() == "true"

    try:
        customer = _resolve_customer(order)

        lines, changes = [], []
        subtotal = gst_total = Decimal("0.00")
        for item in order.items:
            edit = edits.get(item.id, {})
            qty = edit.get("qty", item.qty)
            rate = edit.get("rate", item.unit_price)
            qty, rate = _qty(qty), _money(rate)
            if qty == 0:
                changes.append({"item": item.product_name, "removed": True})
                continue
            if qty < 0 or qty > MAX_QTY or rate <= 0:
                raise ValueError(f"Check the quantity and rate for {item.product_name}.")
            if qty != item.qty or rate != item.unit_price:
                changes.append({"item": item.product_name, "qty": [float(item.qty), float(qty)],
                                "rate": [float(item.unit_price), float(rate)]})

            product = db.session.get(Product, item.product_id)
            if not product or not product.is_active or product.deleted_at:
                raise ValueError(f"{item.product_name} is no longer available.")

            gst_rate = Decimal("0.00") if is_bag_qty(product.unit, qty) else (product.gst_rate or Decimal("0"))
            line_total = _money(qty * rate)
            line_gst = _money(line_total * gst_rate / 100)
            subtotal += line_total
            gst_total += line_gst
            lines.append((product, qty, rate, gst_rate, line_total))

        if not lines:
            raise ValueError("An order needs at least one item.")
        if not gst_enabled:
            gst_total = Decimal("0.00")
        grand_total = subtotal + gst_total
        if grand_total <= 0:
            raise ValueError("Grand total must be greater than 0.")

        bill_number = None
        for _ in range(10):
            candidate = generate_bill_number(
                prefix=settings.get("bill_prefix", "IG"),
                reset_policy=settings.get("bill_counter_reset", "daily"),
            )
            if not Bill.query.filter_by(bill_number=candidate).first():
                bill_number = candidate
                break
        if not bill_number:
            raise ValueError("Could not generate a bill number. Try again.")

        officer = order.officer
        note = f"Order {order.request_number} (officer: {officer.name})"
        if order.notes:
            note += f" — {order.notes}"

        bill = Bill(
            bill_number=bill_number, customer=customer, operator_id=admin.id,
            subtotal=subtotal, discount_amount=Decimal("0.00"), discount_type="flat",
            taxable_amount=subtotal, gst_amount=gst_total, grand_total=grand_total,
            payment_mode=payment_mode, amount_paid=grand_total, change_returned=Decimal("0.00"),
            notes=note, status="confirmed",
            marketing_officer_name=officer.name, marketing_officer_phone=officer.phone or None,
            marketing_officer_id=officer.id,
        )
        db.session.add(bill)
        db.session.flush()

        for product, qty, rate, gst_rate, line_total in lines:
            db.session.add(BillItem(
                bill_id=bill.id, product_id=product.id, product_name=product.name,
                unit_price=rate, qty=qty, unit=product.unit, gst_rate=gst_rate,
                hsn_code=product.hsn_code, line_total=line_total,
            ))
            apply_stock_change(
                product=product, delta_qty=-qty, actor_id=admin.id, reason="sale",
                reference_type="bill", reference_id=bill.id, note=f"Bill {bill.bill_number}",
            )

        order.status = "approved"
        order.payment_mode = payment_mode
        order.customer_id = customer.id if customer.id else None
        order.bill_id = bill.id
        order.decided_by = admin.id
        order.decided_at = now_ist()
        order.seen_by_officer = False
        db.session.flush()
        order.customer = customer

        upsert_daily_summary(bill.bill_date.date() if hasattr(bill.bill_date, "date") else now_ist().date())
        log_action(
            actor_id=admin.id, action="APPROVE", entity="order_request", entity_id=order.id,
            new_val={"request": order.request_number, "bill": bill_number,
                     "total": float(grand_total), "changes": changes},
        )
        db.session.commit()
        return bill
    except Exception:
        db.session.rollback()
        raise


def reject_order(order, admin, reason) -> None:
    reason = (reason or "").strip()
    if order.status != "pending":
        raise ValueError("This order has already been reviewed.")
    if len(reason) < 3:
        raise ValueError("Write a short reason so the officer knows why.")
    order.status = "rejected"
    order.decision_reason = reason[:500]
    order.decided_by = admin.id
    order.decided_at = now_ist()
    order.seen_by_officer = False
    log_action(actor_id=admin.id, action="REJECT", entity="order_request", entity_id=order.id,
               new_val={"request": order.request_number, "reason": reason[:500]})
    db.session.commit()
