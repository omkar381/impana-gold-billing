"""owner_app/routes.py — screens and JSON calls for the owner's phone app."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

import bcrypt
from flask import (
    abort, current_app, flash, g, jsonify, make_response, redirect, render_template,
    request, send_from_directory, url_for,
)
from flask_wtf.csrf import generate_csrf
from sqlalchemy import func, or_

from extensions import db
from models import Bill, Customer, MarketingOfficer, OwnerPasskey, Product, Category, AdminUser
from owner_app import owner_bp
from owner_app.auth import (
    DEVICE_DAYS, clear_device_cookie, current_device, device_required, has_passkey,
    issue_device_cookie, mark_locked, owner_required,
)
from utils.audit import log_action
from utils.bill_link import UNNAMED_BUYER, is_mobile, phone10, whatsapp_url
from utils.billing_service import BillError, save_bill
from utils.timeutil import now_ist, today_ist

LOCKOUT_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
PAGE_SIZE = 20
MAX_ITEMS = 60
MAX_QTY = Decimal("100000")
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=10))


def _asset_version() -> int:
    """Changes whenever the app's CSS/JS change, so phones never keep old files."""
    import os
    root = current_app.static_folder
    files = ("css/owner.css", "js/owner.js", "js/owner_lock.js", "js/owner_billing.js", "js/owner_bills.js")
    try:
        return int(max(os.path.getmtime(os.path.join(root, f)) for f in files if os.path.exists(os.path.join(root, f))))
    except ValueError:
        return 0


@owner_bp.context_processor
def _owner_context():
    return {"asset_v": _asset_version()}


def _shop_name() -> str:
    from billing.routes import get_setting
    return get_setting("shop_name", "Impana Gold") or "Impana Gold"


def _safe_next(value, fallback):
    """Only ever send him to a page inside this app."""
    if value and value.startswith("/b/") and not value.startswith("//"):
        return value
    return fallback


@owner_bp.after_request
def _headers(response):
    # Billing pages hold sales and customer data: never keep them in shared caches.
    if request.endpoint in ("owner.manifest", "owner.service_worker"):
        return response
    response.headers["Cache-Control"] = "no-store"
    return response


# ── Sign in / out ──────────────────────────────────────────────────────────

@owner_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_device():
        return redirect(url_for("owner.home"))

    username = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = AdminUser.query.filter_by(username=username).first()

        if user and user.locked_until and user.locked_until > now_ist():
            flash("Too many wrong attempts. Please try again in a few minutes.", "danger")
        elif user and user.is_active and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            user.failed_login_count = 0
            user.locked_until = None
            user.last_login = now_ist()
            log_action(actor_id=user.id, action="LOGIN", entity="admin_users", entity_id=user.id,
                       ip_address=request.remote_addr)
            db.session.commit()
            response = redirect(url_for("owner.setup_lock"))
            issue_device_cookie(response, user)
            mark_locked()
            return response
        else:
            if user is None:
                bcrypt.checkpw(password.encode(), _DUMMY_HASH)  # same timing whether or not the user exists
            else:
                user.failed_login_count = (user.failed_login_count or 0) + 1
                if user.failed_login_count >= LOCKOUT_ATTEMPTS:
                    user.locked_until = now_ist() + timedelta(minutes=LOCKOUT_MINUTES)
                    user.failed_login_count = 0
                db.session.commit()
            flash("Wrong username or password.", "danger")

    return render_template("owner/login.html", username=username)


@owner_bp.route("/logout", methods=["POST"])
def logout():
    device = current_device()
    if device:
        OwnerPasskey.query.filter_by(
            admin_user_id=device["user"].id, device_id=device["device_id"]
        ).delete()
        log_action(actor_id=device["user"].id, action="LOGOUT", entity="admin_users",
                   entity_id=device["user"].id, ip_address=request.remote_addr)
        db.session.commit()
    mark_locked()
    response = redirect(url_for("owner.login"))
    clear_device_cookie(response)
    return response


# ── Fingerprint lock screens ───────────────────────────────────────────────

@owner_bp.route("/setup-lock")
@device_required
def setup_lock():
    if g.owner_device["no_lock"] or has_passkey(g.owner_device):
        return redirect(url_for("owner.home"))
    return render_template("owner/setup_lock.html")


@owner_bp.route("/setup-lock/skip", methods=["POST"])
@device_required
def setup_lock_skip():
    """Only for a phone with no fingerprint or screen-lock hardware at all."""
    if has_passkey(g.owner_device):
        return redirect(url_for("owner.home"))
    response = redirect(url_for("owner.home"))
    issue_device_cookie(response, g.owner, g.owner_device["device_id"], no_lock=True)
    return response


@owner_bp.route("/lock")
@device_required
def lock():
    """The lock screen. Visiting it always drops the unlocked state."""
    mark_locked()
    if g.owner_device["no_lock"]:
        return redirect(url_for("owner.home"))
    if not has_passkey(g.owner_device):
        return redirect(url_for("owner.setup_lock"))
    return render_template("owner/lock.html", next=_safe_next(request.args.get("next"), url_for("owner.home")))


@owner_bp.route("/csrf")
@device_required
def csrf_token():
    """A fresh token, for a phone that has had the app open for more than an hour."""
    return jsonify({"token": generate_csrf()})


# ── New bill ───────────────────────────────────────────────────────────────

@owner_bp.route("/")
@owner_required
def home():
    officers = MarketingOfficer.query.filter(MarketingOfficer.is_active.is_(True)).order_by(
        MarketingOfficer.is_default.desc(), MarketingOfficer.name
    ).all()
    from billing.routes import get_all_settings
    settings = get_all_settings()
    return render_template(
        "owner/new_bill.html",
        officers=officers,
        gst_enabled=settings.get("gst_enabled", "true").lower() == "true",
    )


@owner_bp.route("/api/products")
@owner_required
def api_products():
    categories = Category.query.order_by(Category.sort_order, Category.name).all()
    products = Product.query.filter(Product.is_active.is_(True), Product.deleted_at.is_(None)).order_by(Product.name).all()
    return jsonify({
        "categories": [{"id": c.id, "name": c.name} for c in categories],
        "products": [
            {
                "id": p.id, "name": p.name, "sku": p.sku, "unit": p.unit,
                "price": float(p.price_per_unit), "gst": float(p.gst_rate or 0),
                "stock": float(p.stock_qty or 0), "category_id": p.category_id,
                "weight": p.weight_grams or 0,
                "image": url_for("static", filename=p.image_path) if p.image_path else "",
            }
            for p in products
        ],
    })


def _phone_digits():
    """Customer.phone with spaces, dashes and '+' removed, so '+91 98765 43210' matches 9876543210."""
    col = Customer.phone
    for ch in (" ", "-", "+", "(", ")"):
        col = func.replace(col, ch, "")
    return col


def _customer_json(c):
    return {"id": c.id, "name": c.name, "phone": phone10(c.phone), "address": c.address or ""}


@owner_bp.route("/api/customers")
@owner_required
def api_customers():
    q = (request.args.get("q") or "").strip()
    query = Customer.query.filter(Customer.deleted_at.is_(None))
    if not q:
        # Buyers he billed most recently come first, so a repeat customer is one tap away.
        recent = (
            db.session.query(Customer, func.max(Bill.bill_date).label("last"))
            .join(Bill, Bill.customer_id == Customer.id)
            .filter(Customer.deleted_at.is_(None))
            .group_by(Customer.id)
            .order_by(func.max(Bill.bill_date).desc())
            .limit(6).all()
        )
        people = [c for c, _ in recent]
        if len(people) < 6:  # not many billed yet: fill up with the newest customers
            seen = {c.id for c in people}
            newest = query.order_by(Customer.id.desc()).limit(12).all()
            people += [c for c in newest if c.id not in seen][: 6 - len(people)]
        return jsonify([_customer_json(c) for c in people])

    like = f"%{q}%"
    clauses = [Customer.name.ilike(like)]
    digits = "".join(ch for ch in q if ch.isdigit())
    if digits:
        clauses.append(_phone_digits().like(f"%{digits}%"))
    rows = query.filter(or_(*clauses)).order_by(Customer.name).limit(8).all()
    return jsonify([_customer_json(c) for c in rows])


def _clean_items(raw):
    """Check the cart before it reaches the shared bill routine (which expects clean numbers)."""
    if not isinstance(raw, list) or not raw:
        raise BillError("Add at least one item.")
    if len(raw) > MAX_ITEMS:
        raise BillError("Too many items on one bill.")
    cleaned = []
    for row in raw:
        try:
            product_id = int(row["product_id"])
            qty = Decimal(str(row["qty"]))
            price = Decimal(str(row["unit_price"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise BillError("Check the quantity and rate on each item.")
        if not (Decimal("0") < qty <= MAX_QTY) or not (Decimal("0") < price <= Decimal("10000000")):
            raise BillError("Check the quantity and rate on each item.")
        cleaned.append({
            "product_id": product_id, "qty": str(qty), "unit_price": str(price),
            "is_loose": bool(row.get("is_loose")),
        })
    return cleaned


def _resolve_customer(buyer):
    """Find the buyer by tapped id or phone, so a repeat customer never becomes a duplicate."""
    number = phone10(buyer.get("phone"))
    customer = None
    if buyer.get("id"):
        customer = db.session.get(Customer, int(buyer["id"]))
        if customer and number and phone10(customer.phone) != number:
            customer = None  # he changed the number after picking, so it is someone else
    if not customer and number:
        base = Customer.query.filter(Customer.deleted_at.is_(None))
        customer = base.filter(Customer.phone == number).first() or base.filter(
            _phone_digits().like("%" + number)
        ).first()
    return customer, number


@owner_bp.route("/api/bills", methods=["POST"])
@owner_required
def api_create_bill():
    data = request.get_json(silent=True) or {}
    buyer = data.get("buyer") or {}
    name = (buyer.get("name") or "").strip()[:200]
    if buyer.get("phone") and not is_mobile(buyer["phone"]):
        return jsonify({"error": "Enter the buyer's 10-digit mobile number."}), 400

    try:
        payload = {
            "items": _clean_items(data.get("items")),
            "payment_mode": data.get("payment_mode", "cash"),
            "discount_type": "percent" if data.get("discount_type") == "percent" else "flat",
            "discount_amount": _decimal_or_zero(data.get("discount_amount")),
            "notes": (data.get("notes") or "")[:500],
            "marketing_officer_id": data.get("marketing_officer_id") or None,
            "apply_overall_gst": False,
            "status": "confirmed",
        }
        customer, number = _resolve_customer(buyer)
        if customer:
            payload["customer_id"] = customer.id
            payload["customer_name"] = name or customer.name
            payload["customer_phone"] = "" if customer.phone else number
        elif name or number:
            payload["customer_name"] = name or UNNAMED_BUYER
            payload["customer_phone"] = number
        bill = save_bill(payload, g.owner.id, request.remote_addr)
    except BillError as exc:
        return jsonify({"error": str(exc)}), exc.status

    return jsonify({
        "ok": True, "id": bill.id, "number": bill.bill_number,
        "url": url_for("owner.bill_detail", bill_id=bill.id, new=1),
    })


def _decimal_or_zero(value):
    try:
        number = Decimal(str(value or 0))
    except InvalidOperation:
        raise BillError("Check the discount.")
    if number < 0:
        raise BillError("Check the discount.")
    return str(number)


# ── Bills: list, one bill, resend ──────────────────────────────────────────

def _day_label(dt):
    today = today_ist()
    day = dt.date()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return dt.strftime("%d %b %Y")


@owner_bp.route("/bills")
@owner_required
def bills():
    q = (request.args.get("q") or "").strip()
    page = max(request.args.get("page", 1, type=int), 1)

    query = (
        Bill.query.outerjoin(Customer, Bill.customer_id == Customer.id)
        .options(db.lazyload(Bill.items))
        .filter(Bill.status.in_(("confirmed", "cancelled")))
    )
    if q:
        like = f"%{q}%"
        clauses = [Bill.bill_number.ilike(like), Customer.name.ilike(like)]
        digits = "".join(ch for ch in q if ch.isdigit())
        if digits:
            clauses.append(_phone_digits().like(f"%{digits}%"))
        query = query.filter(or_(*clauses))

    rows = query.order_by(Bill.bill_date.desc(), Bill.id.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE + 1).all()
    has_more = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]

    groups = []
    for bill in rows:
        label = _day_label(bill.bill_date)
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "bills": []})
        groups[-1]["bills"].append(bill)

    today_totals = None
    if page == 1 and not q:
        count, total = (
            db.session.query(func.count(Bill.id), func.coalesce(func.sum(Bill.grand_total), 0))
            .filter(Bill.status == "confirmed", db.func.date(Bill.bill_date) == today_ist())
            .one()
        )
        today_totals = {"count": count, "total": total}

    template = "owner/_bill_rows.html" if request.args.get("partial") else "owner/bills.html"
    return render_template(template, groups=groups, q=q, page=page, has_more=has_more, today=today_totals)


@owner_bp.route("/bill/<int:bill_id>")
@owner_required
def bill_detail(bill_id):
    bill = db.session.get(Bill, bill_id)
    if not bill or bill.status == "draft":
        abort(404)
    from utils.bill_link import bill_url
    return render_template(
        "owner/bill.html", bill=bill, is_new=bool(request.args.get("new")),
        wa_url=whatsapp_url(bill, _shop_name()), link=bill_url(bill),
        has_number=bool(bill.customer and is_mobile(bill.customer.phone)),
    )


@owner_bp.route("/api/bills/<int:bill_id>/phone", methods=["POST"])
@owner_required
def api_bill_phone(bill_id):
    """Add (or fix) the buyer's number on a bill so it can be sent on WhatsApp."""
    bill = db.session.get(Bill, bill_id)
    if not bill or bill.status == "draft":
        abort(404)
    data = request.get_json(silent=True) or {}
    number = phone10(data.get("phone"))
    if not is_mobile(number):
        return jsonify({"error": "Enter the buyer's 10-digit mobile number."}), 400

    existing = Customer.query.filter(Customer.deleted_at.is_(None), _phone_digits().like("%" + number)).first()
    if existing:
        bill.customer = existing
    elif bill.customer:
        bill.customer.phone = number
    else:
        bill.customer = Customer(name=(data.get("name") or "").strip()[:200] or UNNAMED_BUYER, phone=number)
    log_action(actor_id=g.owner.id, action="UPDATE", entity="bill", entity_id=bill.id,
               new_val={"buyer_phone_added": True}, ip_address=request.remote_addr)
    db.session.commit()
    return jsonify({"ok": True, "wa_url": whatsapp_url(bill, _shop_name())})


# ── Account ────────────────────────────────────────────────────────────────

@owner_bp.route("/account")
@owner_required
def account():
    signed_at = g.owner_device.get("signed_at")
    until = signed_at + timedelta(days=DEVICE_DAYS) if signed_at else None
    return render_template("owner/account.html", until=until, lock_on=not g.owner_device["no_lock"])


# ── PWA plumbing ───────────────────────────────────────────────────────────

@owner_bp.route("/manifest.webmanifest")
def manifest():
    data = {
        "id": "/b/",
        "name": "Impana Gold Billing",
        "short_name": "Impana Bill",
        "description": "Make bills and send them to buyers on WhatsApp",
        "start_url": "/b/",
        "scope": "/b/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#ffffff",
        "theme_color": "#ffffff",
        "icons": [
            {"src": url_for("static", filename="img/pwa-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": url_for("static", filename="img/pwa-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": url_for("static", filename="img/pwa-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    resp = make_response(jsonify(data))
    resp.headers["Content-Type"] = "application/manifest+json"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@owner_bp.route("/sw.js")
def service_worker():
    resp = make_response(send_from_directory(current_app.static_folder + "/pwa", "owner-sw.js"))
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/b/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@owner_bp.route("/offline")
def offline():
    return render_template("owner/offline.html")
