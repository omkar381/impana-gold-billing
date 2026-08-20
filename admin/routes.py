"""
admin/routes.py - Admin panel routes for Impana Gold Billing System.

All /admin/* routes require authenticated, active users.
Certain routes are restricted to superadmin only.
"""

from __future__ import annotations

import csv
import io
import os
import secrets
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal

import bcrypt
from flask import (
    render_template, redirect, url_for, flash, request, abort,
    current_app, make_response,
)
from flask_login import current_user
from sqlalchemy import func, or_, and_

from admin import admin_bp
from auth.decorators import admin_required, superadmin_required
from extensions import db
from forms import (
    ProductForm, CustomerForm, BusinessSettingsForm,
    StaffAddForm, StaffPasswordResetForm, BillCancelForm, StockAdjustForm,
)
from models import (
    AdminUser, BusinessSettings, Category, Product, Customer,
    Bill, BillItem, DailySummary, AuditLog, InventoryTransaction,
)
from utils.audit import log_action
from utils.stock import apply_stock_change


# -- Helpers --

SETTINGS_KEYS = [
    "shop_name",
    "tagline",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "state_code",
    "pincode",
    "phone",
    "phone2",
    "email",
    "website",
    "gstin",
    "fssai",
    "iso_certification",
    "logo_path",
    "fssai_logo_path",
    "iso_logo_path",
    "other_cert_logo_path",
    "bill_prefix",
    "gst_enabled",
    "bill_counter_reset",
    "bank_name",
    "bank_branch",
    "bank_account",
    "bank_ifsc",
    "upi_id",
    "terms_conditions",
    "declaration",
    "signature_name",
]

# File upload field names → settings key mapping
LOGO_FIELDS = {
    "logo": "logo_path",
    "fssai_logo": "fssai_logo_path",
    "iso_logo": "iso_logo_path",
    "other_cert_logo": "other_cert_logo_path",
}


def get_all_settings() -> dict:
    rows = BusinessSettings.query.all()
    return {r.key: r.value for r in rows}


def parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in current_app.config.get("ALLOWED_EXTENSIONS", set())


def save_product_image(file) -> str | None:
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        raise ValueError("Invalid image file type")

    ext = os.path.splitext(file.filename)[1].lower()
    product_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "products")
    os.makedirs(product_dir, exist_ok=True)

    filename = f"product_{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(product_dir, filename)
    file.save(save_path)

    return f"uploads/products/{filename}"


def upsert_daily_summary(bill_date: date) -> None:
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


# -- Dashboard --

@admin_bp.route("/")
@admin_required
def dashboard():
    today = date.today()

    metrics = (
        db.session.query(
            func.coalesce(func.sum(Bill.grand_total), 0).label("revenue"),
            func.count(Bill.id).label("bill_count"),
            func.coalesce(func.sum(Bill.gst_amount), 0).label("gst_total"),
        )
        .filter(
            db.func.date(Bill.bill_date) == today,
            Bill.status == "confirmed",
        )
        .first()
    )

    bill_count = metrics.bill_count or 0
    revenue = metrics.revenue or 0
    avg_bill = (revenue / bill_count) if bill_count else 0

    # Weekly revenue (last 7 days)
    start_day = today - timedelta(days=6)
    weekly_rows = (
        db.session.query(
            db.func.date(Bill.bill_date).label("day"),
            func.coalesce(func.sum(Bill.grand_total), 0).label("total"),
        )
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(start_day, datetime.min.time()),
        )
        .group_by(db.func.date(Bill.bill_date))
        .all()
    )
    weekly_map = {r.day: float(r.total) for r in weekly_rows}
    weekly_data = []
    for i in range(7):
        day = start_day + timedelta(days=i)
        weekly_data.append({
            "date": day,
            "total": weekly_map.get(day, 0),
        })

    # Top 5 products by quantity sold this month
    month_start = today.replace(day=1)
    top_products = (
        db.session.query(
            BillItem.product_name,
            func.coalesce(func.sum(BillItem.qty), 0).label("qty_sold"),
        )
        .join(Bill, BillItem.bill_id == Bill.id)
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(month_start, datetime.min.time()),
        )
        .group_by(BillItem.product_name)
        .order_by(func.sum(BillItem.qty).desc())
        .limit(5)
        .all()
    )

    # Payment breakdown (today)
    pay_rows = (
        db.session.query(
            Bill.payment_mode,
            func.coalesce(func.sum(Bill.grand_total), 0).label("total"),
        )
        .filter(
            db.func.date(Bill.bill_date) == today,
            Bill.status == "confirmed",
        )
        .group_by(Bill.payment_mode)
        .all()
    )
    pay_map = {r.payment_mode: float(r.total) for r in pay_rows}
    pay_total = sum(pay_map.values()) or 1
    payment_breakdown = []
    for mode in ("cash", "upi", "card"):
        amount = pay_map.get(mode, 0)
        payment_breakdown.append({
            "mode": mode,
            "amount": amount,
            "percent": round((amount / pay_total) * 100, 1),
        })

    return render_template(
        "admin/dashboard.html",
        revenue=revenue,
        bill_count=bill_count,
        avg_bill=avg_bill,
        gst_total=metrics.gst_total or 0,
        weekly_data=weekly_data,
        top_products=top_products,
        payment_breakdown=payment_breakdown,
    )


# -- Products --

@admin_bp.route("/products")
@admin_required
def products():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", "").strip()

    query = Product.query.filter(Product.deleted_at == None)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.barcode.ilike(like),
            )
        )
    if category_id.isdigit():
        query = query.filter(Product.category_id == int(category_id))

    products_list = query.order_by(Product.name).all()
    categories = Category.query.order_by(Category.sort_order, Category.name).all()

    form = ProductForm()
    form.category_id.choices = [(0, "Uncategorized")] + [
        (c.id, c.name) for c in categories
    ]

    return render_template(
        "admin/products.html",
        products=products_list,
        categories=categories,
        form=form,
        q=q,
        selected_category=category_id,
    )


@admin_bp.route("/products/export")
@admin_required
def export_products():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", "").strip()

    query = Product.query.filter(Product.deleted_at == None)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.barcode.ilike(like),
            )
        )
    if category_id.isdigit():
        query = query.filter(Product.category_id == int(category_id))

    products_list = query.order_by(Product.name).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name",
        "SKU",
        "Category",
        "Price per Unit",
        "Unit",
        "Stock Qty",
        "GST Rate",
        "Barcode",
        "Active",
    ])

    for p in products_list:
        category_name = p.category.name if p.category else "Uncategorized"
        writer.writerow([
            p.name,
            p.sku,
            category_name,
            f"{p.price_per_unit:.2f}",
            p.unit,
            f"{p.stock_qty:.3f}",
            f"{p.gst_rate}%",
            p.barcode or "",
            "Yes" if p.is_active else "No",
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = "attachment; filename=products_export.csv"
    return response


@admin_bp.route("/products/add", methods=["POST"])
@admin_required
def add_product():
    form = ProductForm()
    categories = Category.query.order_by(Category.sort_order, Category.name).all()
    form.category_id.choices = [(0, "Uncategorized")] + [
        (c.id, c.name) for c in categories
    ]

    if not form.validate_on_submit():
        flash("Please correct the errors in the product form.", "danger")
        return redirect(url_for("admin.products"))

    sku = form.sku.data.strip()
    if Product.query.filter_by(sku=sku).first():
        flash("SKU already exists.", "danger")
        return redirect(url_for("admin.products"))

    category_val = form.category_id.data or 0
    category_id = None if category_val == 0 else category_val

    image_path = None
    if form.image.data and form.image.data.filename:
        try:
            image_path = save_product_image(form.image.data)
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("admin.products"))

    initial_stock = form.initial_stock.data
    if initial_stock is None:
        initial_stock = Decimal("0.000")

    product = Product(
        name=form.name.data.strip(),
        sku=sku,
        category_id=category_id,
        price_per_unit=form.price_per_unit.data,
        unit=form.unit.data,
        weight_grams=form.weight_grams.data or None,
        hsn_code=(form.hsn_code.data or "").strip() or None,
        gst_rate=Decimal(form.gst_rate.data or "0"),
        barcode=(form.barcode.data or "").strip() or None,
        image_path=image_path,
        stock_qty=initial_stock,
        is_active=bool(form.is_active.data),
    )

    try:
        db.session.add(product)
        db.session.flush()
        log_action(
            actor_id=current_user.id,
            action="CREATE",
            entity="product",
            entity_id=product.id,
            new_val={"sku": product.sku, "name": product.name},
            ip_address=request.remote_addr,
        )
        db.session.commit()
        flash("Product added successfully.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to add product: {exc}", "danger")

    return redirect(url_for("admin.products"))


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_product(product_id: int):
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)

    form = ProductForm(obj=product)
    categories = Category.query.order_by(Category.sort_order, Category.name).all()
    form.category_id.choices = [(0, "Uncategorized")] + [
        (c.id, c.name) for c in categories
    ]

    if request.method == "GET":
        form.category_id.data = product.category_id or 0
        form.gst_rate.data = str(product.gst_rate or "0")

    if form.validate_on_submit():
        sku = form.sku.data.strip()
        existing = Product.query.filter(
            Product.sku == sku,
            Product.id != product.id,
        ).first()
        if existing:
            flash("SKU already exists.", "danger")
            return redirect(url_for("admin.edit_product", product_id=product.id))

        old_val = {
            "name": product.name,
            "price_per_unit": float(product.price_per_unit),
            "gst_rate": float(product.gst_rate or 0),
            "is_active": product.is_active,
        }

        category_val = form.category_id.data or 0
        product.name = form.name.data.strip()
        product.sku = sku
        product.category_id = None if category_val == 0 else category_val
        product.price_per_unit = form.price_per_unit.data
        product.unit = form.unit.data
        product.weight_grams = form.weight_grams.data or None
        product.hsn_code = (form.hsn_code.data or "").strip() or None
        product.gst_rate = Decimal(form.gst_rate.data or "0")
        product.barcode = (form.barcode.data or "").strip() or None
        product.is_active = bool(form.is_active.data)

        if form.image.data and form.image.data.filename:
            try:
                product.image_path = save_product_image(form.image.data)
            except ValueError as exc:
                flash(str(exc), "danger")
                return redirect(url_for("admin.edit_product", product_id=product.id))

        try:
            log_action(
                actor_id=current_user.id,
                action="UPDATE",
                entity="product",
                entity_id=product.id,
                old_val=old_val,
                new_val={"name": product.name, "price_per_unit": float(product.price_per_unit)},
                ip_address=request.remote_addr,
            )
            db.session.commit()
            flash("Product updated successfully.", "success")
        except Exception as exc:
            db.session.rollback()
            flash(f"Failed to update product: {exc}", "danger")

        return redirect(url_for("admin.products"))

    return render_template(
        "admin/products.html",
        edit_product=product,
        form=form,
        products=Product.query.filter(Product.deleted_at == None).order_by(Product.name).all(),
        categories=categories,
    )


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete_product(product_id: int):
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)

    if product.deleted_at:
        flash("Product already deleted.", "warning")
        return redirect(url_for("admin.products"))

    product.deleted_at = datetime.utcnow()
    product.is_active = False

    try:
        log_action(
            actor_id=current_user.id,
            action="DELETE",
            entity="product",
            entity_id=product.id,
            old_val={"name": product.name, "sku": product.sku},
            new_val={"deleted_at": product.deleted_at.isoformat()},
            ip_address=request.remote_addr,
        )
        db.session.commit()
        flash("Product deleted (soft).", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to delete product: {exc}", "danger")

    return redirect(url_for("admin.products"))


@admin_bp.route("/products/<int:product_id>/toggle", methods=["POST"])
@admin_required
def toggle_product(product_id: int):
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)
    if product.deleted_at:
        flash("Cannot toggle a deleted product.", "warning")
        return redirect(url_for("admin.products"))

    product.is_active = not product.is_active

    try:
        log_action(
            actor_id=current_user.id,
            action="UPDATE",
            entity="product",
            entity_id=product.id,
            old_val={"is_active": not product.is_active},
            new_val={"is_active": product.is_active},
            ip_address=request.remote_addr,
        )
        db.session.commit()
        flash("Product status updated.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to update product status: {exc}", "danger")

    return redirect(url_for("admin.products"))


# -- Warehouse --

@admin_bp.route("/warehouse")
@admin_required
def warehouse():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", "").strip()

    query = Product.query.filter(Product.deleted_at == None)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.barcode.ilike(like),
            )
        )
    if category_id.isdigit():
        query = query.filter(Product.category_id == int(category_id))

    products_list = query.order_by(Product.name).all()
    categories = Category.query.order_by(Category.sort_order, Category.name).all()

    form = StockAdjustForm()

    return render_template(
        "admin/warehouse.html",
        products=products_list,
        categories=categories,
        form=form,
        q=q,
        selected_category=category_id,
    )


@admin_bp.route("/warehouse/<int:product_id>/adjust", methods=["POST"])
@admin_required
def adjust_stock(product_id: int):
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)

    form = StockAdjustForm()
    if not form.validate_on_submit():
        flash("Please provide a valid quantity and note.", "danger")
        return redirect(url_for("admin.warehouse"))

    action = form.action.data
    qty = form.qty.data
    note = form.note.data.strip()

    if action == "deduct" and current_user.role != "superadmin":
        abort(403)

    delta = qty if action == "restock" else -qty

    try:
        before, after = apply_stock_change(
            product=product,
            delta_qty=delta,
            actor_id=current_user.id,
            reason=action,
            reference_type="warehouse",
            reference_id=None,
            note=note,
        )

        log_action(
            actor_id=current_user.id,
            action=f"STOCK_{action.upper()}",
            entity="inventory",
            entity_id=product.id,
            old_val={"stock_qty": float(before)},
            new_val={"stock_qty": float(after), "delta": float(delta), "note": note},
            ip_address=request.remote_addr,
        )

        db.session.commit()
        flash("Stock updated successfully.", "success")

    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to update stock: {exc}", "danger")

    return redirect(url_for("admin.warehouse"))


# -- Audit Panel --

@admin_bp.route("/audit")
@superadmin_required
def audit_panel():
    user_id = request.args.get("user_id", type=int)

    audit_query = AuditLog.query
    if user_id:
        audit_query = audit_query.filter(AuditLog.actor_id == user_id)
    audit_logs = audit_query.order_by(AuditLog.created_at.desc()).limit(200).all()

    stock_query = InventoryTransaction.query
    if user_id:
        stock_query = stock_query.filter(InventoryTransaction.actor_id == user_id)
    stock_logs = stock_query.order_by(InventoryTransaction.created_at.desc()).limit(200).all()

    users = AdminUser.query.order_by(AdminUser.username).all()

    return render_template(
        "admin/audit.html",
        audit_logs=audit_logs,
        stock_logs=stock_logs,
        users=users,
        selected_user_id=user_id,
    )


# -- Bills --


def _bill_query_from_args(args):
    query = Bill.query

    status = args.get("status", "").strip()
    payment = args.get("payment", "").strip()
    q = args.get("q", "").strip()
    start_date = parse_date(args.get("start_date"))
    end_date = parse_date(args.get("end_date"))

    if status in ("draft", "confirmed", "cancelled"):
        query = query.filter(Bill.status == status)

    if payment in ("cash", "upi", "card", "credit"):
        query = query.filter(Bill.payment_mode == payment)

    if q:
        like = f"%{q}%"
        query = query.filter(Bill.bill_number.ilike(like))

    if start_date:
        query = query.filter(
            Bill.bill_date >= datetime.combine(start_date, datetime.min.time())
        )
    if end_date:
        query = query.filter(
            Bill.bill_date <= datetime.combine(end_date, datetime.max.time())
        )

    return query.order_by(Bill.bill_date.desc())


@admin_bp.route("/bills")
@admin_required
def bills():
    page = request.args.get("page", 1, type=int)
    query = _bill_query_from_args(request.args)
    pagination = query.paginate(page=page, per_page=20, error_out=False)

    cancel_form = BillCancelForm()

    return render_template(
        "admin/bills.html",
        bills=pagination.items,
        pagination=pagination,
        filters=request.args,
        cancel_form=cancel_form,
    )


@admin_bp.route("/bills/<int:bill_id>")
@admin_required
def bill_detail(bill_id: int):
    bill = db.session.get(Bill, bill_id)
    if not bill:
        abort(404)

    settings = get_all_settings()
    gst_enabled = settings.get("gst_enabled", "true").lower() == "true"

    return render_template(
        "admin/bill_detail.html",
        bill=bill,
        gst_enabled=gst_enabled,
        settings=settings,
    )


@admin_bp.route("/bills/<int:bill_id>/cancel", methods=["POST"])
@admin_required
def admin_cancel_bill(bill_id: int):
    bill = db.session.get(Bill, bill_id)
    if not bill:
        abort(404)

    if bill.status == "cancelled":
        flash("Bill is already cancelled.", "warning")
        return redirect(url_for("admin.bills"))

    form = BillCancelForm()
    if not form.validate_on_submit():
        flash("Please provide a cancellation reason.", "danger")
        return redirect(url_for("admin.bills"))

    old_status = bill.status
    bill.status = "cancelled"
    bill.cancelled_at = datetime.utcnow()
    bill.cancel_reason = form.cancel_reason.data.strip()

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
            new_val={"status": "cancelled", "reason": bill.cancel_reason},
            ip_address=request.remote_addr,
        )
        upsert_daily_summary(bill.bill_date.date())
        db.session.commit()
        flash(f"Bill {bill.bill_number} cancelled.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to cancel bill: {exc}", "danger")

    return redirect(url_for("admin.bills"))


@admin_bp.route("/bills/export")
@admin_required
def export_bills():
    query = _bill_query_from_args(request.args)
    bills_list = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Bill Number",
        "Date",
        "Customer",
        "Items",
        "Grand Total",
        "Payment",
        "Status",
    ])

    for bill in bills_list:
        customer_name = bill.customer.name if bill.customer else "Walk-in"
        writer.writerow([
            bill.bill_number,
            bill.bill_date.strftime("%Y-%m-%d %H:%M"),
            customer_name,
            len(bill.items),
            f"{bill.grand_total:.2f}",
            bill.payment_mode,
            bill.status,
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = "attachment; filename=bills_export.csv"
    return response


# -- Reports --


def _report_date_range(args):
    today = date.today()
    start_date = parse_date(args.get("start_date"))
    end_date = parse_date(args.get("end_date"))

    if not start_date:
        start_date = today.replace(day=1)
    if not end_date:
        end_date = today

    return start_date, end_date


@admin_bp.route("/reports")
@admin_required
def reports():
    start_date, end_date = _report_date_range(request.args)

    # Revenue report: daily totals
    revenue_rows = (
        db.session.query(
            db.func.date(Bill.bill_date).label("day"),
            func.count(Bill.id).label("bill_count"),
            func.coalesce(func.sum(Bill.grand_total), 0).label("revenue"),
            func.coalesce(func.sum(Bill.gst_amount), 0).label("gst_total"),
        )
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(start_date, datetime.min.time()),
            Bill.bill_date <= datetime.combine(end_date, datetime.max.time()),
        )
        .group_by(db.func.date(Bill.bill_date))
        .order_by(db.func.date(Bill.bill_date))
        .all()
    )

    # Product-wise report
    product_rows = (
        db.session.query(
            BillItem.product_name,
            func.coalesce(func.sum(BillItem.qty), 0).label("qty_sold"),
            func.coalesce(func.sum(BillItem.line_total), 0).label("revenue"),
        )
        .join(Bill, BillItem.bill_id == Bill.id)
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(start_date, datetime.min.time()),
            Bill.bill_date <= datetime.combine(end_date, datetime.max.time()),
        )
        .group_by(BillItem.product_name)
        .order_by(func.sum(BillItem.qty).desc())
        .all()
    )

    # GST report (by rate slab)
    gst_rows = (
        db.session.query(
            BillItem.gst_rate,
            func.coalesce(func.sum(BillItem.line_total), 0).label("taxable"),
        )
        .join(Bill, BillItem.bill_id == Bill.id)
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(start_date, datetime.min.time()),
            Bill.bill_date <= datetime.combine(end_date, datetime.max.time()),
        )
        .group_by(BillItem.gst_rate)
        .order_by(BillItem.gst_rate)
        .all()
    )

    gst_report = []
    for row in gst_rows:
        rate = Decimal(row.gst_rate or 0)
        taxable = Decimal(row.taxable or 0)
        gst_total = (taxable * rate / Decimal("100")).quantize(Decimal("0.01"))
        gst_report.append({
            "rate": rate,
            "taxable": taxable,
            "cgst": gst_total / 2,
            "sgst": gst_total / 2,
            "gst_total": gst_total,
        })

    return render_template(
        "admin/reports.html",
        start_date=start_date,
        end_date=end_date,
        revenue_rows=revenue_rows,
        product_rows=product_rows,
        gst_report=gst_report,
    )


@admin_bp.route("/reports/export")
@admin_required
def export_reports():
    start_date, end_date = _report_date_range(request.args)
    export_format = request.args.get("format", "csv").lower()

    # Reuse the same datasets as reports()
    revenue_rows = (
        db.session.query(
            db.func.date(Bill.bill_date).label("day"),
            func.count(Bill.id).label("bill_count"),
            func.coalesce(func.sum(Bill.grand_total), 0).label("revenue"),
            func.coalesce(func.sum(Bill.gst_amount), 0).label("gst_total"),
        )
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(start_date, datetime.min.time()),
            Bill.bill_date <= datetime.combine(end_date, datetime.max.time()),
        )
        .group_by(db.func.date(Bill.bill_date))
        .order_by(db.func.date(Bill.bill_date))
        .all()
    )

    product_rows = (
        db.session.query(
            BillItem.product_name,
            func.coalesce(func.sum(BillItem.qty), 0).label("qty_sold"),
            func.coalesce(func.sum(BillItem.line_total), 0).label("revenue"),
        )
        .join(Bill, BillItem.bill_id == Bill.id)
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(start_date, datetime.min.time()),
            Bill.bill_date <= datetime.combine(end_date, datetime.max.time()),
        )
        .group_by(BillItem.product_name)
        .order_by(func.sum(BillItem.qty).desc())
        .all()
    )

    gst_rows = (
        db.session.query(
            BillItem.gst_rate,
            func.coalesce(func.sum(BillItem.line_total), 0).label("taxable"),
        )
        .join(Bill, BillItem.bill_id == Bill.id)
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(start_date, datetime.min.time()),
            Bill.bill_date <= datetime.combine(end_date, datetime.max.time()),
        )
        .group_by(BillItem.gst_rate)
        .order_by(BillItem.gst_rate)
        .all()
    )

    gst_report = []
    for row in gst_rows:
        rate = Decimal(row.gst_rate or 0)
        taxable = Decimal(row.taxable or 0)
        gst_total = (taxable * rate / Decimal("100")).quantize(Decimal("0.01"))
        gst_report.append({
            "rate": rate,
            "taxable": taxable,
            "cgst": gst_total / 2,
            "sgst": gst_total / 2,
            "gst_total": gst_total,
        })

    if export_format == "pdf":
        html = render_template(
            "admin/reports.html",
            start_date=start_date,
            end_date=end_date,
            revenue_rows=revenue_rows,
            product_rows=product_rows,
            gst_report=gst_report,
            export_mode="pdf",
        )
        try:
            from utils.pdf import html_to_pdf
            pdf_bytes = html_to_pdf(html, base_url=request.host_url)
        except Exception as exc:
            flash(f"PDF export failed: {exc}", "danger")
            return redirect(url_for("admin.reports"))

        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = (
            "attachment; filename=reports_export.pdf"
        )
        return response

    # CSV export (combined sections)
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Revenue Report"])
    writer.writerow(["Date", "Bills", "Revenue", "GST"])
    for row in revenue_rows:
        writer.writerow([
            row.day.strftime("%Y-%m-%d"),
            row.bill_count,
            f"{row.revenue:.2f}",
            f"{row.gst_total:.2f}",
        ])

    writer.writerow([])
    writer.writerow(["Product Report"])
    writer.writerow(["Product", "Qty Sold", "Revenue"])
    for row in product_rows:
        writer.writerow([
            row.product_name,
            f"{row.qty_sold:.3f}",
            f"{row.revenue:.2f}",
        ])

    writer.writerow([])
    writer.writerow(["GST Report"])
    writer.writerow(["GST Rate", "Taxable", "CGST", "SGST", "Total GST"])
    for row in gst_report:
        writer.writerow([
            f"{row['rate']}%",
            f"{row['taxable']:.2f}",
            f"{row['cgst']:.2f}",
            f"{row['sgst']:.2f}",
            f"{row['gst_total']:.2f}",
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = "attachment; filename=reports_export.csv"
    return response


# -- Customers --

@admin_bp.route("/customers")
@admin_required
def customers():
    q = request.args.get("q", "").strip()

    query = db.session.query(
        Customer,
        func.coalesce(func.count(Bill.id), 0).label("bill_count"),
        func.coalesce(func.sum(Bill.grand_total), 0).label("total_spent"),
        func.max(Bill.bill_date).label("last_visit"),
    ).outerjoin(
        Bill,
        and_(Bill.customer_id == Customer.id, Bill.status == "confirmed"),
    ).filter(Customer.deleted_at == None)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Customer.name.ilike(like), Customer.phone.ilike(like))
        )

    rows = (
        query.group_by(Customer.id)
        .order_by(Customer.name)
        .all()
    )

    customer_rows = []
    for row in rows:
        customer_rows.append({
            "customer": row[0],
            "bill_count": row.bill_count,
            "total_spent": row.total_spent,
            "last_visit": row.last_visit,
        })

    form = CustomerForm()

    return render_template(
        "admin/customers.html",
        customers=customer_rows,
        form=form,
        q=q,
    )


@admin_bp.route("/customers/export")
@admin_required
def export_customers():
    q = request.args.get("q", "").strip()

    query = db.session.query(
        Customer,
        func.coalesce(func.count(Bill.id), 0).label("bill_count"),
        func.coalesce(func.sum(Bill.grand_total), 0).label("total_spent"),
        func.max(Bill.bill_date).label("last_visit"),
    ).outerjoin(
        Bill,
        and_(Bill.customer_id == Customer.id, Bill.status == "confirmed"),
    ).filter(Customer.deleted_at == None)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Customer.name.ilike(like), Customer.phone.ilike(like))
        )

    rows = query.group_by(Customer.id).order_by(Customer.name).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name",
        "Phone",
        "Address",
        "GSTIN",
        "Total Bills",
        "Total Spent",
        "Last Visit",
    ])

    for row in rows:
        customer = row[0]
        last_visit = row.last_visit.strftime("%Y-%m-%d %H:%M") if row.last_visit else "Never"
        writer.writerow([
            customer.name,
            customer.phone or "",
            customer.address or "",
            customer.gstin or "",
            row.bill_count,
            f"{row.total_spent:.2f}",
            last_visit,
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = "attachment; filename=customers_export.csv"
    return response


@admin_bp.route("/customers/add", methods=["POST"])
@admin_required
def add_customer():
    form = CustomerForm()
    if not form.validate_on_submit():
        flash("Please correct the errors in the customer form.", "danger")
        return redirect(url_for("admin.customers"))

    phone = (form.phone.data or "").strip() or None
    if phone and Customer.query.filter_by(phone=phone).first():
        flash("Phone already exists.", "danger")
        return redirect(url_for("admin.customers"))

    customer = Customer(
        name=form.name.data.strip(),
        phone=phone,
        address=(form.address.data or "").strip() or None,
        gstin=(form.gstin.data or "").strip() or None,
    )

    try:
        db.session.add(customer)
        db.session.flush()
        log_action(
            actor_id=current_user.id,
            action="CREATE",
            entity="customer",
            entity_id=customer.id,
            new_val={"name": customer.name, "phone": customer.phone},
            ip_address=request.remote_addr,
        )
        db.session.commit()
        flash("Customer added successfully.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to add customer: {exc}", "danger")

    return redirect(url_for("admin.customers"))


@admin_bp.route("/customers/<int:customer_id>")
@admin_required
def customer_detail(customer_id: int):
    customer = db.session.get(Customer, customer_id)
    if not customer or customer.deleted_at:
        abort(404)

    bills_list = (
        Bill.query.filter(Bill.customer_id == customer.id)
        .order_by(Bill.bill_date.desc())
        .all()
    )

    totals = (
        db.session.query(
            func.coalesce(func.count(Bill.id), 0).label("bill_count"),
            func.coalesce(func.sum(Bill.grand_total), 0).label("total_spent"),
        )
        .filter(
            Bill.customer_id == customer.id,
            Bill.status == "confirmed",
        )
        .first()
    )

    form = CustomerForm(obj=customer)

    return render_template(
        "admin/customer_detail.html",
        customer=customer,
        bills=bills_list,
        bill_count=totals.bill_count or 0,
        total_spent=totals.total_spent or 0,
        form=form,
    )


@admin_bp.route("/customers/<int:customer_id>/edit", methods=["POST"])
@admin_required
def edit_customer(customer_id: int):
    customer = db.session.get(Customer, customer_id)
    if not customer or customer.deleted_at:
        abort(404)

    form = CustomerForm()
    if not form.validate_on_submit():
        flash("Please correct the customer form.", "danger")
        return redirect(url_for("admin.customer_detail", customer_id=customer.id))

    phone = (form.phone.data or "").strip() or None
    existing = Customer.query.filter(
        Customer.phone == phone,
        Customer.id != customer.id,
    ).first()
    if phone and existing:
        flash("Phone already exists.", "danger")
        return redirect(url_for("admin.customer_detail", customer_id=customer.id))

    old_val = {
        "name": customer.name,
        "phone": customer.phone,
    }

    customer.name = form.name.data.strip()
    customer.phone = phone
    customer.address = (form.address.data or "").strip() or None
    customer.gstin = (form.gstin.data or "").strip() or None

    try:
        log_action(
            actor_id=current_user.id,
            action="UPDATE",
            entity="customer",
            entity_id=customer.id,
            old_val=old_val,
            new_val={"name": customer.name, "phone": customer.phone},
            ip_address=request.remote_addr,
        )
        db.session.commit()
        flash("Customer updated successfully.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to update customer: {exc}", "danger")

    return redirect(url_for("admin.customer_detail", customer_id=customer.id))


@admin_bp.route("/customers/<int:customer_id>/delete", methods=["POST"])
@admin_required
def delete_customer(customer_id: int):
    customer = db.session.get(Customer, customer_id)
    if not customer:
        abort(404)

    if customer.deleted_at:
        flash("Customer already deleted.", "warning")
        return redirect(url_for("admin.customers"))

    customer.deleted_at = datetime.utcnow()

    try:
        log_action(
            actor_id=current_user.id,
            action="DELETE",
            entity="customer",
            entity_id=customer.id,
            old_val={"name": customer.name, "phone": customer.phone},
            new_val={"deleted_at": customer.deleted_at.isoformat()},
            ip_address=request.remote_addr,
        )
        db.session.commit()
        flash("Customer deleted (soft).", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to delete customer: {exc}", "danger")

    return redirect(url_for("admin.customers"))


# -- Business Settings --

@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    settings_map = get_all_settings()
    form = BusinessSettingsForm()

    if request.method == "GET":
        for key in SETTINGS_KEYS:
            if hasattr(form, key) and key in settings_map:
                if key == "gst_enabled":
                    getattr(form, key).data = settings_map.get(key, "true").lower() == "true"
                else:
                    getattr(form, key).data = settings_map.get(key)

    if form.validate_on_submit():
        changes = {}
        # File path keys are managed separately via uploads
        file_path_keys = set(LOGO_FIELDS.values())

        for key in SETTINGS_KEYS:
            if not hasattr(form, key) or key in file_path_keys:
                continue

            if key == "gst_enabled":
                new_val = "true" if form.gst_enabled.data else "false"
            else:
                new_val = (getattr(form, key).data or "").strip()

            old_val = settings_map.get(key)
            if new_val != old_val:
                changes[key] = {"old": old_val, "new": new_val}

                row = BusinessSettings.query.filter_by(key=key).first()
                if not row:
                    row = BusinessSettings(key=key)
                    db.session.add(row)
                row.value = new_val
                row.updated_by = current_user.id

        # Handle all file uploads (logo, fssai_logo, iso_logo)
        for form_field_name, settings_key in LOGO_FIELDS.items():
            field = getattr(form, form_field_name, None)
            if field and field.data and hasattr(field.data, 'filename') and field.data.filename:
                file = field.data
                if not allowed_file(file.filename):
                    flash(f"Invalid file type for {form_field_name}.", "danger")
                    continue

                ext = os.path.splitext(file.filename)[1].lower()
                filename = f"{form_field_name}_{uuid.uuid4().hex}{ext}"
                save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
                file.save(save_path)

                rel_path = f"uploads/{filename}"
                old_val = settings_map.get(settings_key)

                row = BusinessSettings.query.filter_by(key=settings_key).first()
                if not row:
                    row = BusinessSettings(key=settings_key)
                    db.session.add(row)
                row.value = rel_path
                row.updated_by = current_user.id

                changes[settings_key] = {"old": old_val, "new": rel_path}

        if not changes:
            flash("No changes to save.", "info")
            return redirect(url_for("admin.settings"))

        try:
            log_action(
                actor_id=current_user.id,
                action="UPDATE",
                entity="settings",
                entity_id=None,
                old_val={k: v["old"] for k, v in changes.items()},
                new_val={k: v["new"] for k, v in changes.items()},
                ip_address=request.remote_addr,
            )
            db.session.commit()
            flash("Settings updated successfully.", "success")
        except Exception as exc:
            db.session.rollback()
            flash(f"Failed to update settings: {exc}", "danger")

        return redirect(url_for("admin.settings"))

    if request.method == "POST":
        flash("Please correct the errors in the form.", "danger")

    return render_template(
        "admin/settings.html",
        form=form,
        settings=settings_map,
    )


# -- Staff Management --

@admin_bp.route("/staff")
@superadmin_required
def staff():
    users = AdminUser.query.order_by(AdminUser.username).all()
    add_form = StaffAddForm()
    reset_form = StaffPasswordResetForm()

    audit_user_id = request.args.get("user_id", type=int)
    audit_logs = []
    if audit_user_id:
        audit_logs = (
            AuditLog.query.filter(AuditLog.actor_id == audit_user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(100)
            .all()
        )

    return render_template(
        "admin/staff.html",
        users=users,
        add_form=add_form,
        reset_form=reset_form,
        audit_logs=audit_logs,
        selected_user_id=audit_user_id,
    )


@admin_bp.route("/staff/add", methods=["POST"])
@superadmin_required
def add_staff():
    form = StaffAddForm()
    if not form.validate_on_submit():
        flash("Please correct the staff form.", "danger")
        return redirect(url_for("admin.staff"))

    username = form.username.data.strip()
    if AdminUser.query.filter_by(username=username).first():
        flash("Username already exists.", "danger")
        return redirect(url_for("admin.staff"))

    password_hash = bcrypt.hashpw(
        form.password.data.encode("utf-8"),
        bcrypt.gensalt(rounds=12),
    ).decode("utf-8")

    user = AdminUser(
        username=username,
        password_hash=password_hash,
        role="staff",
        is_active=True,
    )

    try:
        db.session.add(user)
        db.session.flush()
        log_action(
            actor_id=current_user.id,
            action="CREATE",
            entity="staff",
            entity_id=user.id,
            new_val={"username": user.username, "role": user.role},
            ip_address=request.remote_addr,
        )
        db.session.commit()
        flash("Staff user created.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to create staff user: {exc}", "danger")

    return redirect(url_for("admin.staff"))


@admin_bp.route("/staff/<int:user_id>/toggle", methods=["POST"])
@superadmin_required
def toggle_staff(user_id: int):
    user = db.session.get(AdminUser, user_id)
    if not user:
        abort(404)

    if user.role == "superadmin":
        flash("Cannot deactivate superadmin.", "danger")
        return redirect(url_for("admin.staff"))

    user.is_active = not user.is_active

    try:
        log_action(
            actor_id=current_user.id,
            action="UPDATE",
            entity="staff",
            entity_id=user.id,
            old_val={"is_active": not user.is_active},
            new_val={"is_active": user.is_active},
            ip_address=request.remote_addr,
        )
        db.session.commit()
        flash("Staff status updated.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to update staff: {exc}", "danger")

    return redirect(url_for("admin.staff"))


@admin_bp.route("/staff/<int:user_id>/reset-pass", methods=["POST"])
@superadmin_required
def reset_staff_password(user_id: int):
    user = db.session.get(AdminUser, user_id)
    if not user:
        abort(404)

    if user.role == "superadmin":
        flash("Cannot reset superadmin password here.", "danger")
        return redirect(url_for("admin.staff"))

    new_password = secrets.token_urlsafe(8)

    password_hash = bcrypt.hashpw(
        new_password.encode("utf-8"),
        bcrypt.gensalt(rounds=12),
    ).decode("utf-8")
    user.password_hash = password_hash

    try:
        log_action(
            actor_id=current_user.id,
            action="UPDATE",
            entity="staff",
            entity_id=user.id,
            old_val=None,
            new_val={"password_reset": True},
            ip_address=request.remote_addr,
        )
        db.session.commit()
        flash(
            f"Temporary password for {user.username}: {new_password}",
            "warning",
        )
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to reset password: {exc}", "danger")

    return redirect(url_for("admin.staff"))


# ── GST REPORT ────────────────────────────────────────────────────────────────

def _gst_report_data(date_from, date_to):
    """Build GST report rows from confirmed bills in the given date range."""
    bills = (
        Bill.query
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= date_from,
            Bill.bill_date <= date_to,
        )
        .order_by(Bill.bill_date, Bill.bill_number)
        .all()
    )

    rows = []
    summary = {
        "total_bills": 0,
        "subtotal": Decimal("0.00"),
        "discount": Decimal("0.00"),
        "taxable": Decimal("0.00"),
        "cgst": Decimal("0.00"),
        "sgst": Decimal("0.00"),
        "igst": Decimal("0.00"),
        "gst_total": Decimal("0.00"),
        "grand_total": Decimal("0.00"),
    }

    for bill in bills:
        gst = bill.gst_amount or Decimal("0.00")
        # Split GST into CGST/SGST (intra-state) or IGST (inter-state)
        # Determine from customer GSTIN state code vs shop state
        cust_gstin = ""
        if bill.customer_id and bill.customer:
            cust_gstin = bill.customer.gstin or ""

        is_igst = False  # default intra-state
        cgst = (gst / 2).quantize(Decimal("0.01"))
        sgst = (gst / 2).quantize(Decimal("0.01"))
        igst = Decimal("0.00")
        if is_igst:
            igst = gst
            cgst = sgst = Decimal("0.00")

        rows.append({
            "bill_number": bill.bill_number,
            "date": bill.bill_date.strftime("%d-%b-%Y"),
            "customer": bill.customer.name if bill.customer_id and bill.customer else "Walk-in",
            "customer_gstin": cust_gstin,
            "payment": bill.payment_mode.upper(),
            "subtotal": bill.subtotal,
            "discount": bill.discount_amount or Decimal("0.00"),
            "taxable": bill.taxable_amount,
            "cgst": cgst,
            "sgst": sgst,
            "igst": igst,
            "gst_total": gst,
            "grand_total": bill.grand_total,
        })

        summary["total_bills"] += 1
        summary["subtotal"] += bill.subtotal
        summary["discount"] += bill.discount_amount or Decimal("0.00")
        summary["taxable"] += bill.taxable_amount
        summary["cgst"] += cgst
        summary["sgst"] += sgst
        summary["igst"] += igst
        summary["gst_total"] += gst
        summary["grand_total"] += bill.grand_total

    return rows, summary


@admin_bp.route("/gst-report", methods=["GET"])
@admin_required
def gst_report():
    settings = get_all_settings()

    # Default: current month
    today = date.today()
    default_from = today.replace(day=1).strftime("%Y-%m-%d")
    default_to = today.strftime("%Y-%m-%d")

    date_from_str = request.args.get("date_from", default_from)
    date_to_str = request.args.get("date_to", default_to)

    try:
        date_from = datetime.strptime(date_from_str, "%Y-%m-%d")
        date_to = datetime.strptime(date_to_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
    except ValueError:
        date_from = datetime.strptime(default_from, "%Y-%m-%d")
        date_to = datetime.strptime(default_to, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )

    rows, summary = _gst_report_data(date_from, date_to)

    return render_template(
        "admin/gst_report.html",
        rows=rows,
        summary=summary,
        date_from=date_from.strftime("%Y-%m-%d"),
        date_to=date_to.strftime("%Y-%m-%d"),
        date_from_display=date_from.strftime("%d %b %Y"),
        date_to_display=date_to.strftime("%d %b %Y"),
        settings=settings,
        generated_at=datetime.now().strftime("%d-%b-%Y %I:%M %p"),
    )


@admin_bp.route("/gst-report/csv")
@admin_required
def gst_report_csv():
    today = date.today()
    date_from_str = request.args.get("date_from", today.replace(day=1).strftime("%Y-%m-%d"))
    date_to_str = request.args.get("date_to", today.strftime("%Y-%m-%d"))

    try:
        date_from = datetime.strptime(date_from_str, "%Y-%m-%d")
        date_to = datetime.strptime(date_to_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
    except ValueError:
        date_from = datetime.now().replace(day=1)
        date_to = datetime.now()

    rows, summary = _gst_report_data(date_from, date_to)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header block
    settings = get_all_settings()
    writer.writerow(["GST REPORT — " + settings.get("shop_name", "Impana Gold")])
    writer.writerow(["GSTIN:", settings.get("gstin", "")])
    writer.writerow(["Period:", f"{date_from.strftime('%d-%b-%Y')} to {date_to.strftime('%d-%b-%Y')}"])
    writer.writerow([])

    # Column headers
    writer.writerow([
        "Invoice No.", "Date", "Customer Name", "Customer GSTIN",
        "Payment", "Gross Amount (₹)", "Discount (₹)", "Taxable Amount (₹)",
        "CGST (₹)", "SGST (₹)", "IGST (₹)", "Total GST (₹)", "Grand Total (₹)"
    ])

    for r in rows:
        writer.writerow([
            r["bill_number"], r["date"], r["customer"], r["customer_gstin"],
            r["payment"],
            f"{r['subtotal']:.2f}", f"{r['discount']:.2f}", f"{r['taxable']:.2f}",
            f"{r['cgst']:.2f}", f"{r['sgst']:.2f}", f"{r['igst']:.2f}",
            f"{r['gst_total']:.2f}", f"{r['grand_total']:.2f}",
        ])

    # Summary footer
    writer.writerow([])
    writer.writerow(["TOTAL", "", "", "", "",
        f"{summary['subtotal']:.2f}", f"{summary['discount']:.2f}", f"{summary['taxable']:.2f}",
        f"{summary['cgst']:.2f}", f"{summary['sgst']:.2f}", f"{summary['igst']:.2f}",
        f"{summary['gst_total']:.2f}", f"{summary['grand_total']:.2f}",
    ])
    writer.writerow([])
    writer.writerow(["Total Bills:", summary["total_bills"]])
    writer.writerow(["Generated:", datetime.now().strftime("%d-%b-%Y %I:%M %p")])

    output.seek(0)
    filename = f"GST_Report_{date_from.strftime('%Y%m%d')}_{date_to.strftime('%Y%m%d')}.csv"
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    return response


@admin_bp.route("/gst-report/print")
@admin_required
def gst_report_print():
    """Printable/PDF version of the GST report."""
    settings = get_all_settings()

    today = date.today()
    date_from_str = request.args.get("date_from", today.replace(day=1).strftime("%Y-%m-%d"))
    date_to_str = request.args.get("date_to", today.strftime("%Y-%m-%d"))

    try:
        date_from = datetime.strptime(date_from_str, "%Y-%m-%d")
        date_to = datetime.strptime(date_to_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
    except ValueError:
        date_from = datetime.now().replace(day=1)
        date_to = datetime.now()

    rows, summary = _gst_report_data(date_from, date_to)

    return render_template(
        "admin/gst_report_print.html",
        rows=rows,
        summary=summary,
        date_from=date_from.strftime("%d %b %Y"),
        date_to=date_to.strftime("%d %b %Y"),
        settings=settings,
        generated_at=datetime.now().strftime("%d-%b-%Y %I:%M %p"),
    )
