"""
billing/routes.py — POS billing screen and invoice routes.

Routes:
  GET  /                      POS billing screen
  POST /bill/create           Save confirmed bill → redirect to print
  GET  /bill/<id>/print       Professional tax invoice HTML
  GET  /bill/<id>/pdf         WeasyPrint PDF download
  POST /bill/<id>/cancel      Cancel bill with reason
  POST /bill/draft            Save draft cart (JSON)
  GET  /bill/draft            Load current draft cart (JSON)
"""

import json
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

from flask import (
    render_template, redirect, url_for, flash, request,
    jsonify, make_response, session, abort,
)
from flask_login import login_required, current_user

from billing import billing_bp
from extensions import db
from models import (
    Product, Category, Customer, Bill, BillItem,
    DailySummary, BusinessSettings,
)
from forms import BillCancelForm
from utils.bill_number import generate_bill_number
from utils.audit import log_action
from utils.num_to_words import num_to_words
from utils.stock import apply_stock_change


# ── Helpers ────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    """Fetch a single business setting value."""
    row = BusinessSettings.query.filter_by(key=key).first()
    return row.value if row else default


def get_all_settings() -> dict:
    """Return all business settings as a dict."""
    rows = BusinessSettings.query.all()
    return {r.key: r.value for r in rows}


def upsert_daily_summary(bill_date: date) -> None:
    """
    Recompute and upsert DailySummary for the given date.
    Called after every confirmed bill save.
    """
    from sqlalchemy import func

    results = (
        db.session.query(
            func.count(Bill.id).label("total_bills"),
            func.coalesce(func.sum(Bill.grand_total), 0).label("total_revenue"),
            func.coalesce(func.sum(Bill.gst_amount), 0).label("total_gst"),
            func.coalesce(func.sum(Bill.discount_amount), 0).label("total_discount"),
            func.coalesce(
                func.sum(
                    db.case((Bill.payment_mode == "cash", Bill.grand_total), else_=0)
                ),
                0,
            ).label("cash_total"),
            func.coalesce(
                func.sum(
                    db.case((Bill.payment_mode == "upi", Bill.grand_total), else_=0)
                ),
                0,
            ).label("upi_total"),
            func.coalesce(
                func.sum(
                    db.case((Bill.payment_mode == "card", Bill.grand_total), else_=0)
                ),
                0,
            ).label("card_total"),
        )
        .filter(
            db.func.date(Bill.bill_date) == bill_date,
            Bill.status == "confirmed",
        )
        .first()
    )

    summary = DailySummary.query.filter_by(summary_date=bill_date).first()
    if not summary:
        summary = DailySummary(summary_date=bill_date)
        db.session.add(summary)

    summary.total_bills = results.total_bills or 0
    summary.total_revenue = results.total_revenue or 0
    summary.total_gst = results.total_gst or 0
    summary.total_discount = results.total_discount or 0
    summary.cash_total = results.cash_total or 0
    summary.upi_total = results.upi_total or 0
    summary.card_total = results.card_total or 0
    summary.computed_at = datetime.utcnow()


def compute_hsn_breakup(bill_items):
    """
    Group bill items by HSN code and compute per-HSN GST breakup.
    Returns a list of dicts: [{hsn_code, taxable, gst_rate, cgst, sgst, total_tax}, ...]
    """
    groups = defaultdict(lambda: {"taxable": Decimal("0"), "gst_rate": Decimal("0")})

    for item in bill_items:
        hsn = item.hsn_code or "-"
        groups[hsn]["taxable"] += item.line_total
        # Take the GST rate from the first item in this HSN group
        if groups[hsn]["gst_rate"] == 0 and item.gst_rate:
            groups[hsn]["gst_rate"] = item.gst_rate

    result = []
    for hsn, data in groups.items():
        taxable = data["taxable"]
        gst_rate = data["gst_rate"]
        total_tax = (taxable * gst_rate / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        result.append({
            "hsn_code": hsn,
            "taxable": float(taxable),
            "gst_rate": float(gst_rate),
            "cgst": float(total_tax / 2),
            "sgst": float(total_tax / 2),
            "total_tax": float(total_tax),
        })

    return result


# ── POS Screen ─────────────────────────────────────────────────────────────

@billing_bp.route("/")
@login_required
def pos():
    """Main POS billing screen."""
    categories = Category.query.order_by(Category.sort_order, Category.name).all()
    products = (
        Product.query.filter(
            Product.is_active == True, Product.deleted_at == None
        )
        .order_by(Product.name)
        .all()
    )
    settings = get_all_settings()
    return render_template(
        "index.html",
        categories=categories,
        products=products,
        settings=settings,
    )


# ── Create Bill ────────────────────────────────────────────────────────────

@billing_bp.route("/bill/create", methods=["POST"])
@login_required
def create_bill():
    """
    Save a confirmed bill.
    Expects JSON body from billing.js cart.
    """
    data = request.get_json(silent=True)
    if not data:
        flash("No bill data received.", "danger")
        return redirect(url_for("billing.pos"))

    # ── Validation ────────────────────────────────────────────────────────
    items_data = data.get("items", [])
    if not items_data:
        return jsonify({"error": "Cart is empty."}), 400

    payment_mode = data.get("payment_mode", "cash")
    if payment_mode not in ("cash", "upi", "card", "credit"):
        return jsonify({"error": "Invalid payment mode."}), 400

    # ── Resolve customer (optional) ───────────────────────────────────────
    customer = None
    customer_id = data.get("customer_id")
    customer_name = (data.get("customer_name") or "").strip()
    customer_phone = (data.get("customer_phone") or "").strip()
    customer_address = (data.get("customer_address") or "").strip()
    customer_gstin = (data.get("customer_gstin") or "").strip()

    if customer_id:
        customer = Customer.query.get(int(customer_id))

    if not customer and (customer_phone or customer_gstin):
        lookup = Customer.query.filter(Customer.deleted_at == None)
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
        # Allow custom rate from POS cart; fall back to product default
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
        line_gst = (
            (line_total * gst_rate / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        )
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
        return jsonify({"error": "No valid products in cart."}), 400

    # ── Discount ──────────────────────────────────────────────────────────
    discount_type = data.get("discount_type", "flat")
    raw_discount = Decimal(str(data.get("discount_amount", 0)))

    if discount_type == "percent":
        discount_amount = (subtotal * raw_discount / 100).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )
    else:
        discount_amount = raw_discount.quantize(Decimal("0.01"), ROUND_HALF_UP)

    discount_amount = min(discount_amount, subtotal)
    taxable_amount = subtotal - discount_amount

    settings = get_all_settings()
    gst_enabled = settings.get("gst_enabled", "true").lower() == "true"

    # Override GST: if customer requests overall 18% GST, use that instead of per-product
    apply_overall_gst = data.get("apply_overall_gst", False)
    if apply_overall_gst and gst_enabled:
        overall_gst_rate = Decimal(str(data.get("overall_gst_rate", 5)))
        gst_amount = (taxable_amount * overall_gst_rate / 100).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )
    elif not gst_enabled:
        gst_amount = Decimal("0.00")

    grand_total = taxable_amount + gst_amount
    if grand_total <= 0:
        return jsonify({"error": "Grand total must be greater than 0."}), 400

    amount_paid = Decimal(str(data.get("amount_paid", grand_total)))
    change_returned = max(amount_paid - grand_total, Decimal("0.00"))

    # ── Bill number (with retry) ──────────────────────────────────────────
    prefix = settings.get("bill_prefix", "IG")
    reset_policy = settings.get("bill_counter_reset", "daily")

    bill_number = None
    for _ in range(10):
        candidate = generate_bill_number(prefix=prefix, reset_policy=reset_policy)
        exists = Bill.query.filter_by(bill_number=candidate).first()
        if not exists:
            bill_number = candidate
            break

    if not bill_number:
        return jsonify({"error": "Could not generate a unique bill number."}), 500

    # ── Build and save bill ───────────────────────────────────────────────
    status = data.get("status", "confirmed")
    bill = Bill(
        bill_number=bill_number,
        customer=customer,
        operator_id=current_user.id,
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
                    actor_id=current_user.id,
                    reason="sale",
                    reference_type="bill",
                    reference_id=bill.id,
                    note=f"Bill {bill.bill_number}",
                )
            upsert_daily_summary(bill.bill_date.date() if hasattr(bill.bill_date, 'date') else date.today())

        log_action(
            actor_id=current_user.id,
            action="CREATE",
            entity="bill",
            entity_id=bill.id,
            new_val={"bill_number": bill_number, "grand_total": float(grand_total)},
            ip_address=request.remote_addr,
        )

        db.session.commit()

    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Database error: {exc}"}), 500

    return jsonify({"bill_id": bill.id, "bill_number": bill_number, "status": status})


# ── Print Invoice ──────────────────────────────────────────────────────────

@billing_bp.route("/bill/<int:bill_id>/print")
@login_required
def print_bill(bill_id):
    """Render professional tax invoice HTML."""
    bill = db.session.get(Bill, bill_id)
    if not bill:
        abort(404)

    settings = get_all_settings()
    gst_enabled = settings.get("gst_enabled", "true").lower() == "true"

    # Compute HSN-wise GST breakup
    hsn_breakup = compute_hsn_breakup(bill.items) if gst_enabled else []

    # Amount in words
    amount_in_words = num_to_words(bill.grand_total)

    # Tax amount in words
    gst_amount = float(bill.gst_amount or 0)
    tax_in_words = num_to_words(gst_amount) if gst_amount > 0 else ""

    return render_template(
        "bill_print.html",
        bill=bill,
        settings=settings,
        gst_enabled=gst_enabled,
        hsn_breakup=hsn_breakup,
        amount_in_words=amount_in_words,
        tax_in_words=tax_in_words,
        auto_print=True,
    )


# ── PDF Download ───────────────────────────────────────────────────────────

@billing_bp.route("/bill/<int:bill_id>/pdf")
@login_required
def download_pdf(bill_id):
    """Generate and stream PDF of the invoice via WeasyPrint."""
    bill = db.session.get(Bill, bill_id)
    if not bill:
        abort(404)

    settings = get_all_settings()
    gst_enabled = settings.get("gst_enabled", "true").lower() == "true"

    # Compute HSN-wise GST breakup
    hsn_breakup = compute_hsn_breakup(bill.items) if gst_enabled else []

    # Amount in words
    amount_in_words = num_to_words(bill.grand_total)

    # Tax amount in words
    gst_amount = float(bill.gst_amount or 0)
    tax_in_words = num_to_words(gst_amount) if gst_amount > 0 else ""

    html_string = render_template(
        "bill_print.html",
        bill=bill,
        settings=settings,
        gst_enabled=gst_enabled,
        hsn_breakup=hsn_breakup,
        amount_in_words=amount_in_words,
        tax_in_words=tax_in_words,
        auto_print=False,
    )

    try:
        from utils.pdf import html_to_pdf
        pdf_bytes = html_to_pdf(html_string, base_url=request.host_url)
    except Exception as exc:
        flash(f"PDF generation failed: {exc}", "danger")
        return redirect(url_for("billing.print_bill", bill_id=bill_id))

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{bill.bill_number}.pdf"'
    )
    return response


# ── Cancel Bill ────────────────────────────────────────────────────────────

@billing_bp.route("/bill/<int:bill_id>/cancel", methods=["POST"])
@login_required
def cancel_bill(bill_id):
    """Cancel a bill (no hard delete — preserves audit integrity)."""
    bill = db.session.get(Bill, bill_id)
    if not bill:
        abort(404)

    if bill.status == "cancelled":
        flash("Bill is already cancelled.", "warning")
        return redirect(request.referrer or url_for("admin.bills"))

    form = BillCancelForm()
    if form.validate_on_submit():
        old_status = bill.status
        bill.status = "cancelled"
        bill.cancelled_at = datetime.utcnow()
        bill.cancel_reason = form.cancel_reason.data

        try:
            if old_status == "confirmed":
                for item in bill.items:
                    if item.product:
                        apply_stock_change(
                            product=item.product,
                            delta_qty=item.qty,
                            actor_id=current_user.id,
                            reason="cancel",
                            reference_type="bill",
                            reference_id=bill.id,
                            note=f"Cancel bill {bill.bill_number}",
                        )

            log_action(
                actor_id=current_user.id,
                action="CANCEL",
                entity="bill",
                entity_id=bill.id,
                old_val={"status": old_status},
                new_val={"status": "cancelled", "reason": form.cancel_reason.data},
                ip_address=request.remote_addr,
            )
            db.session.commit()
            flash(f"Bill {bill.bill_number} has been cancelled.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except Exception as exc:
            db.session.rollback()
            flash(f"Failed to cancel bill: {exc}", "danger")

    return redirect(request.referrer or url_for("admin.bills"))


# ── Draft Cart ─────────────────────────────────────────────────────────────

@billing_bp.route("/bill/draft", methods=["POST"])
@login_required
def save_draft():
    """Save cart as draft bill (or update existing draft for this operator)."""
    data = request.get_json(silent=True)
    if not data or not data.get("items"):
        return jsonify({"error": "Empty cart"}), 400

    # Soft approach: store in user session (simple, no extra table)
    session["draft_cart"] = data
    return jsonify({"message": "Draft saved."})


@billing_bp.route("/bill/draft", methods=["GET"])
@login_required
def load_draft():
    """Load the saved draft cart for this session."""
    draft = session.get("draft_cart")
    if not draft:
        return jsonify(None)
    return jsonify(draft)
