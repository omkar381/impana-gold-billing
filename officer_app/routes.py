"""officer_app/routes.py — screens and actions for the marketing officer app."""

from datetime import timedelta
from functools import wraps

import bcrypt
from flask import (
    abort, flash, g, jsonify, make_response, redirect, render_template,
    request, send_from_directory, session, url_for, current_app,
)

from extensions import db
from models import MarketingOfficer, OrderRequest, Product
from officer_app import officer_bp
from utils import officer_stats
from utils.orders import cancel_order, create_order_request, digits10
from utils.timeutil import now_ist

LOCKOUT_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=10))


# ── Session helpers ────────────────────────────────────────────────────────

def _fingerprint(officer) -> str:
    # Changes whenever the superadmin resets the password, which ends old sessions.
    return (officer.password_hash or "")[-16:]


def _start_session(officer):
    session["officer_id"] = officer.id
    session["officer_fp"] = _fingerprint(officer)
    session.permanent = True


def _end_session():
    session.pop("officer_id", None)
    session.pop("officer_fp", None)


def current_officer():
    oid = session.get("officer_id")
    if not oid:
        return None
    officer = db.session.get(MarketingOfficer, oid)
    # Re-checked on every request, so deactivating an officer locks them out at once.
    if not officer or not officer.can_login or session.get("officer_fp") != _fingerprint(officer):
        _end_session()
        return None
    return officer


def officer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        officer = current_officer()
        if not officer:
            if request.accept_mimetypes.best == "application/json" or request.is_json:
                return jsonify({"error": "Please sign in again."}), 401
            return redirect(url_for("officer.login"))
        g.officer = officer
        return view(*args, **kwargs)
    return wrapped


@officer_bp.app_template_global("officer_photo")
def officer_photo(o):
    return url_for("officer.photo", officer_id=o.id, v=o.photo_path) if o and o.photo_path else None


@officer_bp.route("/photo/<int:officer_id>")
def photo(officer_id):
    """Officer photos live in the database. Visible to signed-in officers and admins only."""
    from flask_login import current_user
    if not (current_officer() or current_user.is_authenticated):
        abort(404)
    officer = db.session.get(MarketingOfficer, officer_id)
    if not officer or not officer.photo_data:
        abort(404)
    resp = make_response(bytes(officer.photo_data))
    resp.headers["Content-Type"] = "image/jpeg"
    resp.headers["Cache-Control"] = "private, max-age=86400"  # the ?v= token changes with each new photo
    return resp


@officer_bp.after_request
def _no_store(response):
    # Officer pages hold sales data; never keep them in shared caches.
    if request.endpoint and request.endpoint.startswith("officer.") and not request.path.endswith(("/sw.js", ".webmanifest")) and request.endpoint != "officer.photo":
        response.headers["Cache-Control"] = "no-store"
    return response


# ── Sign in / out ──────────────────────────────────────────────────────────

@officer_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_officer():
        return redirect(url_for("officer.home"))

    phone = ""
    if request.method == "POST":
        phone = digits10(request.form.get("phone"))
        password = request.form.get("password") or ""
        officer = next(
            (o for o in MarketingOfficer.query.filter(MarketingOfficer.password_hash.isnot(None)).all()
             if o.login_phone == phone and phone),
            None,
        )

        if officer and officer.locked_until and officer.locked_until > now_ist():
            flash("Too many wrong attempts. Try again in a few minutes or ask the admin.", "danger")
        elif officer and officer.is_active and bcrypt.checkpw(password.encode(), officer.password_hash.encode()):
            officer.failed_login_count = 0
            officer.locked_until = None
            officer.last_login = now_ist()
            db.session.commit()
            _start_session(officer)
            return redirect(url_for("officer.home"))
        else:
            if officer is None:
                bcrypt.checkpw(password.encode(), _DUMMY_HASH)  # same timing whether or not the phone exists
            else:
                officer.failed_login_count = (officer.failed_login_count or 0) + 1
                if officer.failed_login_count >= LOCKOUT_ATTEMPTS:
                    officer.locked_until = now_ist() + timedelta(minutes=LOCKOUT_MINUTES)
                    officer.failed_login_count = 0
                db.session.commit()
            flash("Wrong phone number or password.", "danger")

    return render_template("officer/login.html", phone=phone)


@officer_bp.route("/logout", methods=["POST", "GET"])
def logout():
    _end_session()
    return redirect(url_for("officer.login"))


# ── Home ───────────────────────────────────────────────────────────────────

@officer_bp.route("/")
@officer_required
def home():
    o = g.officer
    ov = officer_stats.overview(o)
    recent = OrderRequest.query.filter_by(officer_id=o.id).order_by(OrderRequest.created_at.desc()).limit(5).all()
    pending = OrderRequest.query.filter_by(officer_id=o.id, status="pending").count()
    updates = (
        OrderRequest.query.filter(
            OrderRequest.officer_id == o.id,
            OrderRequest.status.in_(("approved", "rejected")),
            OrderRequest.seen_by_officer.is_(False),
        ).order_by(OrderRequest.decided_at).all()
    )
    return render_template("officer/home.html", o=o, ov=ov, recent=recent, pending=pending, updates=updates)


@officer_bp.route("/updates/seen", methods=["POST"])
@officer_required
def updates_seen():
    OrderRequest.query.filter(
        OrderRequest.officer_id == g.officer.id, OrderRequest.seen_by_officer.is_(False)
    ).update({OrderRequest.seen_by_officer: True})
    db.session.commit()
    return jsonify({"ok": True})


# ── Orders ─────────────────────────────────────────────────────────────────

@officer_bp.route("/orders")
@officer_required
def orders():
    status = request.args.get("status", "all")
    q = OrderRequest.query.filter_by(officer_id=g.officer.id)
    if status in ("pending", "approved", "rejected", "cancelled"):
        q = q.filter_by(status=status)
    rows = q.order_by(OrderRequest.created_at.desc()).limit(100).all()
    return render_template("officer/orders.html", o=g.officer, rows=rows, status=status)


@officer_bp.route("/orders/new")
@officer_required
def order_new():
    products = Product.query.filter(Product.is_active.is_(True), Product.deleted_at.is_(None)).order_by(Product.name).all()
    product_data = [
        {
            "id": p.id, "name": p.name, "unit": p.unit, "price": float(p.price_per_unit),
            "image": p.image_path or "",
            "weight": p.weight_grams or 0,
        }
        for p in products
    ]
    shops = [
        {"id": s["id"], "name": s["name"], "phone": s["phone"] or ""}
        for s in officer_stats.shops_for(g.officer)
    ]
    selected = request.args.get("shop", type=int)
    return render_template("officer/order_new.html", o=g.officer, products=product_data, shops=shops, selected=selected)


@officer_bp.route("/orders", methods=["POST"])
@officer_required
def order_create():
    data = request.get_json(silent=True) or {}
    try:
        order = create_order_request(g.officer, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "id": order.id, "number": order.request_number, "url": url_for("officer.order_detail", order_id=order.id)})


@officer_bp.route("/orders/<int:order_id>")
@officer_required
def order_detail(order_id):
    order = OrderRequest.query.filter_by(id=order_id, officer_id=g.officer.id).first_or_404()
    if order.status != "pending" and not order.seen_by_officer:
        order.seen_by_officer = True
        db.session.commit()
    return render_template("officer/order_detail.html", o=g.officer, order=order)


@officer_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@officer_required
def order_cancel(order_id):
    order = OrderRequest.query.filter_by(id=order_id, officer_id=g.officer.id).first_or_404()
    try:
        cancel_order(order, g.officer)
        flash("Order cancelled.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("officer.order_detail", order_id=order.id))


# ── Shops, profile ─────────────────────────────────────────────────────────

@officer_bp.route("/shops")
@officer_required
def shops():
    return render_template("officer/shops.html", o=g.officer, shops=officer_stats.shops_for(g.officer))


@officer_bp.route("/profile", methods=["GET", "POST"])
@officer_required
def profile():
    o = g.officer
    if request.method == "POST":
        current = request.form.get("current") or ""
        new = request.form.get("new") or ""
        confirm = request.form.get("confirm") or ""
        if not bcrypt.checkpw(current.encode(), o.password_hash.encode()):
            flash("Your current password is wrong.", "danger")
        elif len(new) < 6:
            flash("New password must be at least 6 characters.", "danger")
        elif new != confirm:
            flash("The two new passwords do not match.", "danger")
        else:
            o.password_hash = bcrypt.hashpw(new.encode(), bcrypt.gensalt(rounds=12)).decode()
            db.session.commit()
            _start_session(o)  # keep this device signed in; all others are signed out
            flash("Password changed.", "success")
        return redirect(url_for("officer.profile"))
    ov = officer_stats.overview(o)
    return render_template("officer/profile.html", o=o, ov=ov)


# ── PWA plumbing ───────────────────────────────────────────────────────────

@officer_bp.route("/manifest.webmanifest")
def manifest():
    data = {
        "name": "Impana Gold Sales",
        "short_name": "Impana Sales",
        "description": "Impana Gold marketing officer app",
        "start_url": "/m/",
        "scope": "/m/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#ffffff",
        "theme_color": "#145a31",
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


@officer_bp.route("/sw.js")
def service_worker():
    resp = make_response(send_from_directory(current_app.static_folder + "/pwa", "sw.js"))
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/m/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@officer_bp.route("/offline")
def offline():
    return render_template("officer/offline.html")


# ── Template filters ───────────────────────────────────────────────────────

@officer_bp.app_template_filter("inr")
def inr(value, decimals=0):
    """12345678 -> 1,23,45,678 (Indian digit grouping)."""
    from decimal import Decimal
    n = Decimal(str(value or 0))
    text = f"{abs(n):.{decimals}f}"
    whole, _, frac = text.partition(".")
    if len(whole) > 3:
        head, tail, groups = whole[:-3], whole[-3:], []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if n < 0 else "") + whole + ("." + frac if frac else "")
