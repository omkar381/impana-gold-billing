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
from utils.timeutil import now_ist, today_ist
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
    DailySummary, BusinessSettings, MarketingOfficer,
)
from forms import BillCancelForm
from utils.bill_number import generate_bill_number
from utils.audit import log_action
from utils.num_to_words import num_to_words
from utils.stock import apply_stock_change
from utils.billing_service import BillError, save_bill


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
    summary.computed_at = now_ist()


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
    officers = (
        MarketingOfficer.query.filter(MarketingOfficer.is_active == True)
        .order_by(MarketingOfficer.is_default.desc(), MarketingOfficer.name)
        .all()
    )
    return render_template(
        "index.html",
        categories=categories,
        products=products,
        settings=settings,
        officers=officers,
    )


# ── Create Bill ────────────────────────────────────────────────────────────

@billing_bp.route("/bill/create", methods=["POST"])
@login_required
def create_bill():
    """
    Save a confirmed bill.
    Expects JSON body from billing.js cart. The calculation lives in
    utils/billing_service.save_bill so the phone app saves bills identically.
    """
    data = request.get_json(silent=True)
    if not data:
        flash("No bill data received.", "danger")
        return redirect(url_for("billing.pos"))

    try:
        bill = save_bill(data, current_user.id, request.remote_addr)
    except BillError as exc:
        return jsonify({"error": str(exc)}), exc.status

    return jsonify({"bill_id": bill.id, "bill_number": bill.bill_number, "status": bill.status})


# ── Print Invoice ──────────────────────────────────────────────────────────

def render_invoice_html(bill, auto_print=False, copies=None, public=False):
    """Render the tax invoice / bill of supply HTML.

    `copies` limits which copies are drawn (e.g. ["ORIGINAL"] for the bill sent
    to a buyer); the default is the usual ORIGINAL + DUPLICATE print sheet.
    `public` is the buyer's phone view: fits a phone screen, no staff buttons.
    """
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
        auto_print=auto_print,
        copies=copies,
        public=public,
    )


@billing_bp.route("/bill/<int:bill_id>/print")
@login_required
def print_bill(bill_id):
    """Render professional tax invoice HTML."""
    bill = db.session.get(Bill, bill_id)
    if not bill:
        abort(404)
    return render_invoice_html(bill, auto_print=True)


@billing_bp.route("/r/<token>")
def shared_bill(token):
    """The buyer's copy, opened from the WhatsApp link. No login: the signed token is the key."""
    from utils.bill_link import bill_id_from_token

    bill_id = bill_id_from_token(token)
    bill = db.session.get(Bill, bill_id) if bill_id else None
    if not bill or bill.status == "draft":
        abort(404)
    if bill.status == "cancelled":
        resp = make_response(render_template("bill_cancelled.html", bill=bill), 410)
    else:
        resp = make_response(render_invoice_html(bill, copies=["ORIGINAL"], public=True))
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


# ── PDF Download ───────────────────────────────────────────────────────────

@billing_bp.route("/bill/<int:bill_id>/pdf")
@login_required
def download_pdf(bill_id):
    """Generate and stream PDF of the invoice."""
    bill = db.session.get(Bill, bill_id)
    if not bill:
        abort(404)

    html_string = render_invoice_html(bill, auto_print=False)

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
        bill.cancelled_at = now_ist()
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
