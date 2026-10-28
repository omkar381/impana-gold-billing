"""
admin/officer_routes.py — Marketing officers, their order approvals and sales report.

Everything here is superadmin-only: officers are managed, and their orders
approved, by the superadmin and nobody else (staff accounts cannot open these).
"""

import csv
import io
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

import bcrypt
from flask import (
    abort, current_app, flash, make_response, redirect, render_template,
    request, url_for,
)
from flask_login import current_user
from sqlalchemy import func

from admin import admin_bp
from auth.decorators import superadmin_required
from extensions import db
from forms import OfficerForm
from models import Bill, MarketingOfficer, OrderRequest
from utils import officer_stats
from utils.audit import log_action
from utils.orders import PAYMENT_MODES, approve_order, duplicate_hints, reject_order
from utils.timeutil import now_ist, today_ist


# ── helpers ────────────────────────────────────────────────────────────────

def _read_photo(file) -> bytes:
    """Re-encode the upload as a 480px square JPEG (also strips anything hidden in the file)."""
    from PIL import Image, ImageOps

    try:
        img = Image.open(file.stream)
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageOps.fit(img, (480, 480), Image.LANCZOS)
    except Exception:
        raise ValueError("That image could not be read. Try a JPG or PNG photo.")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _phone_taken(phone10: str, exclude_id=None) -> bool:
    for o in MarketingOfficer.query.all():
        if o.id != exclude_id and o.login_phone and o.login_phone == phone10:
            return True
    return False


def _date_range(args):
    def parse(value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    today = today_ist()
    start = parse(args.get("start_date")) or today.replace(day=1)
    end = parse(args.get("end_date")) or today
    if start > end:
        start, end = end, start
    return start, end


# ── Officers ───────────────────────────────────────────────────────────────

@admin_bp.route("/officers")
@superadmin_required
def officers():
    rows = []
    m_start, m_end = officer_stats.month_bounds()
    for o in MarketingOfficer.query.order_by(MarketingOfficer.is_active.desc(), MarketingOfficer.name).all():
        count, total = officer_stats.sales_between(o, m_start, m_end)
        locked = bool(o.locked_until and o.locked_until.replace(tzinfo=None) > now_ist())
        rows.append({"o": o, "orders": count, "sales": total, "locked": locked})
    return render_template("admin/officers.html", rows=rows)


@admin_bp.route("/officers/new", methods=["GET", "POST"])
@superadmin_required
def officer_new():
    form = OfficerForm()
    if form.validate_on_submit():
        return _save_officer(form, None)
    return render_template("admin/officer_edit.html", form=form, officer=None)


@admin_bp.route("/officers/<int:officer_id>", methods=["GET", "POST"])
@superadmin_required
def officer_edit(officer_id: int):
    officer = db.session.get(MarketingOfficer, officer_id)
    if not officer:
        abort(404)
    form = OfficerForm(obj=officer if request.method == "GET" else None)
    if request.method == "GET":
        form.monthly_target.data = officer.monthly_target or None
        form.password.data = ""
    if form.validate_on_submit():
        return _save_officer(form, officer)
    return render_template("admin/officer_edit.html", form=form, officer=officer)


def _save_officer(form, officer):
    from utils.orders import digits10

    new = officer is None
    name = form.name.data.strip()
    phone_text = form.phone.data.strip()
    phone10 = digits10(phone_text)
    password = form.password.data or ""

    problem = None
    if len(phone10) != 10:
        problem = "Enter a valid 10-digit phone number. The officer signs in with it."
    elif _phone_taken(phone10, officer.id if officer else None):
        problem = "Another officer already uses this phone number."
    elif new and len(password) < 6:
        problem = "Set a password of at least 6 characters so the officer can sign in."
    if problem:
        flash(problem, "danger")
        return render_template("admin/officer_edit.html", form=form, officer=officer)

    try:
        photo = _read_photo(form.photo.data) if form.photo.data and getattr(form.photo.data, "filename", "") else None
    except ValueError as exc:
        flash(str(exc), "danger")
        return render_template("admin/officer_edit.html", form=form, officer=officer)

    if new:
        officer = MarketingOfficer(is_default=False)
        db.session.add(officer)
    officer.name = name
    officer.phone = phone_text if phone_text.startswith("+") else "+91 " + phone10[:5] + " " + phone10[5:]
    officer.monthly_target = form.monthly_target.data or Decimal("0")
    officer.is_active = bool(form.is_active.data) if not new else True
    if photo:
        officer.photo_data = photo
        officer.photo_path = f"v{int(time.time())}"
    if password:
        officer.password_hash = _hash(password)  # also ends any signed-in sessions on other phones
        officer.failed_login_count = 0
        officer.locked_until = None

    db.session.flush()
    log_action(
        actor_id=current_user.id, action="CREATE" if new else "UPDATE", entity="marketing_officer",
        entity_id=officer.id,
        new_val={"name": officer.name, "phone": officer.phone, "target": float(officer.monthly_target or 0),
                 "active": officer.is_active, "password_changed": bool(password)},
        ip_address=request.remote_addr,
    )
    db.session.commit()
    flash("Officer added." if new else "Officer saved.", "success")
    return redirect(url_for("admin.officers"))


@admin_bp.route("/officers/<int:officer_id>/toggle", methods=["POST"])
@superadmin_required
def toggle_officer(officer_id: int):
    officer = db.session.get(MarketingOfficer, officer_id)
    if not officer:
        abort(404)
    officer.is_active = not officer.is_active
    log_action(actor_id=current_user.id, action="UPDATE", entity="marketing_officer", entity_id=officer.id,
               new_val={"active": officer.is_active}, ip_address=request.remote_addr)
    db.session.commit()
    flash(f"{officer.name} is now {'active' if officer.is_active else 'deactivated and signed out'}.", "success")
    return redirect(url_for("admin.officers"))


@admin_bp.route("/officers/<int:officer_id>/unlock", methods=["POST"])
@superadmin_required
def unlock_officer(officer_id: int):
    officer = db.session.get(MarketingOfficer, officer_id)
    if not officer:
        abort(404)
    officer.failed_login_count = 0
    officer.locked_until = None
    db.session.commit()
    flash("Sign-in unlocked.", "success")
    return redirect(url_for("admin.officers"))


@admin_bp.route("/officers/<int:officer_id>/delete", methods=["POST"])
@superadmin_required
def delete_officer(officer_id: int):
    officer = db.session.get(MarketingOfficer, officer_id)
    if not officer:
        abort(404)
    if OrderRequest.query.filter_by(officer_id=officer.id).first():
        flash("This officer has order history, so it is kept for your records. Deactivate them instead.", "warning")
        return redirect(url_for("admin.officers"))
    # Bills keep their own copy of the name/phone, so past invoices are unaffected.
    db.session.delete(officer)
    db.session.commit()
    flash("Officer deleted.", "success")
    return redirect(url_for("admin.officers"))


# ── Order requests (approval inbox) ────────────────────────────────────────

@admin_bp.route("/orders")
@superadmin_required
def order_requests():
    status = request.args.get("status", "pending")
    q = OrderRequest.query
    if status in ("pending", "approved", "rejected", "cancelled"):
        q = q.filter_by(status=status)
    rows = q.order_by(OrderRequest.created_at.desc() if status != "pending" else OrderRequest.created_at.asc()).limit(200).all()
    counts = dict(db.session.query(OrderRequest.status, func.count(OrderRequest.id)).group_by(OrderRequest.status).all())
    return render_template("admin/orders.html", rows=rows, status=status, counts=counts)


@admin_bp.route("/orders/<int:order_id>")
@superadmin_required
def order_review(order_id: int):
    order = db.session.get(OrderRequest, order_id)
    if not order:
        abort(404)
    existing = None
    if not order.customer_id and order.new_customer_phone:
        from models import Customer
        existing = Customer.query.filter(Customer.phone.like("%" + order.new_customer_phone)).first()
    return render_template(
        "admin/order_review.html", order=order, hints=duplicate_hints(order),
        existing=existing, modes=PAYMENT_MODES,
    )


@admin_bp.route("/orders/<int:order_id>/approve", methods=["POST"])
@superadmin_required
def order_approve(order_id: int):
    order = db.session.get(OrderRequest, order_id)
    if not order:
        abort(404)

    edits = {}
    try:
        for item in order.items:
            qty = request.form.get(f"qty_{item.id}")
            rate = request.form.get(f"rate_{item.id}")
            if qty is not None or rate is not None:
                edits[item.id] = {
                    "qty": Decimal(qty) if qty not in (None, "") else item.qty,
                    "rate": Decimal(rate) if rate not in (None, "") else item.unit_price,
                }
        bill = approve_order(order, current_user, request.form.get("payment_mode", order.payment_mode), edits)
    except (ValueError, InvalidOperation) as exc:
        flash(str(exc) if isinstance(exc, ValueError) else "Check the quantities and rates you entered.", "danger")
        return redirect(url_for("admin.order_review", order_id=order.id))

    flash(f"Approved. Bill {bill.bill_number} created for {order.shop_name}.", "success")
    return redirect(url_for("admin.order_requests"))


@admin_bp.route("/orders/<int:order_id>/reject", methods=["POST"])
@superadmin_required
def order_reject(order_id: int):
    order = db.session.get(OrderRequest, order_id)
    if not order:
        abort(404)
    try:
        reject_order(order, current_user, request.form.get("reason"))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("admin.order_review", order_id=order.id))
    flash("Order rejected. The officer will see your reason.", "success")
    return redirect(url_for("admin.order_requests"))


# ── Officer sales report ───────────────────────────────────────────────────

def _report_rows(start, end):
    rows = (
        db.session.query(
            Bill.marketing_officer_id, Bill.marketing_officer_name,
            func.count(Bill.id), func.coalesce(func.sum(Bill.grand_total), 0),
        )
        .filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(start, datetime.min.time()),
            Bill.bill_date <= datetime.combine(end, datetime.max.time()),
        )
        .group_by(Bill.marketing_officer_id, Bill.marketing_officer_name)
        .all()
    )
    officers = MarketingOfficer.query.all()
    by_id = {o.id: o for o in officers}
    by_name = {o.name: o for o in officers}

    merged = {}
    for oid, name, count, total in rows:
        officer = by_id.get(oid) or (by_name.get(name) if oid is None else None)
        key = ("o", officer.id) if officer else ("n", name or "")
        entry = merged.setdefault(key, {
            "key": str(officer.id) if officer else ("none" if not name else "n:" + name),
            "name": officer.name if officer else (name or "No officer"),
            "officer": officer, "orders": 0, "sales": Decimal("0"),
        })
        entry["orders"] += int(count)
        entry["sales"] += Decimal(str(total))

    for o in officers:  # show active officers with no sales too
        if o.is_active and ("o", o.id) not in merged:
            merged[("o", o.id)] = {"key": str(o.id), "name": o.name, "officer": o, "orders": 0, "sales": Decimal("0")}

    result = sorted(merged.values(), key=lambda r: (-r["sales"], r["name"].lower()))
    total_sales = sum((r["sales"] for r in result), Decimal("0"))
    for r in result:
        r["avg"] = (r["sales"] / r["orders"]) if r["orders"] else Decimal("0")
        r["share"] = float(r["sales"] / total_sales * 100) if total_sales else 0
    return result, total_sales


@admin_bp.route("/officers/report")
@superadmin_required
def officer_report():
    start, end = _date_range(request.args)
    rows, total = _report_rows(start, end)
    selected = request.args.get("officer")
    bills, selected_row = [], None
    if selected:
        selected_row = next((r for r in rows if r["key"] == selected), None)
        q = Bill.query.filter(
            Bill.status == "confirmed",
            Bill.bill_date >= datetime.combine(start, datetime.min.time()),
            Bill.bill_date <= datetime.combine(end, datetime.max.time()),
        )
        if selected == "none":
            q = q.filter(Bill.marketing_officer_id.is_(None), Bill.marketing_officer_name.is_(None))
        elif selected.isdigit():
            o = db.session.get(MarketingOfficer, int(selected))
            q = q.filter(officer_stats.attributed(o)) if o else q.filter(db.false())
        elif selected.startswith("n:"):
            q = q.filter(Bill.marketing_officer_name == selected[2:], Bill.marketing_officer_id.is_(None))
        bills = q.order_by(Bill.bill_date.desc()).limit(300).all()
    return render_template(
        "admin/officer_report.html", rows=rows, total=total, start=start, end=end,
        selected=selected, selected_row=selected_row, bills=bills,
        order_count=sum(r["orders"] for r in rows),
    )


@admin_bp.route("/officers/report/export")
@superadmin_required
def officer_report_export():
    start, end = _date_range(request.args)
    rows, total = _report_rows(start, end)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Officer sales report", f"{start:%d-%b-%Y} to {end:%d-%b-%Y}"])
    w.writerow(["Officer", "Orders", "Sales (Rs)", "Average bill (Rs)", "Share %"])
    for r in rows:
        w.writerow([r["name"], r["orders"], f"{r['sales']:.2f}", f"{r['avg']:.2f}", f"{r['share']:.1f}"])
    w.writerow(["Total", sum(r["orders"] for r in rows), f"{total:.2f}", "", ""])
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = f"attachment; filename=Officer_Sales_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    return resp
