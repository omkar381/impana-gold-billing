"""
app.py — Application factory for Impana Gold Billing System.

Usage:
    flask run                   (development)
    gunicorn -c gunicorn.conf.py "app:create_app()"   (production)
"""

import os
from flask import Flask
from config import config_map
from extensions import db, login_manager, migrate, csrf


def create_app(config_name: str = None) -> Flask:
    """Create and configure the Flask application."""

    app = Flask(__name__)

    # Trust Render's load balancer for HTTPS / Secure cookies
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ── Configuration ──────────────────────────────────────────────────────
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_map.get(config_name, config_map["development"]))

    # Ensure upload folder exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ── Extensions ─────────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    # ── User loader (Flask-Login) ───────────────────────────────────────────
    from models import AdminUser

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(AdminUser, int(user_id))

    # ── Schema safeguard (adds Marketing Officer table/columns if missing) ──
    from utils.schema import ensure_marketing_officer_schema
    with app.app_context():
        ensure_marketing_officer_schema(db)

    # ── Brand logo available to every template ─────────────────────────────
    @app.context_processor
    def inject_brand():
        from flask import url_for
        logo = "img/impana-logo.png"
        return {"brand_logo_url": url_for("static", filename=logo)}

    # ── Pending-approval badge for the admin sidebar ───────────────────────
    @app.context_processor
    def inject_pending_orders():
        from flask import request
        from flask_login import current_user
        try:
            if (request.blueprint == "admin" and current_user.is_authenticated
                    and current_user.role == "superadmin"):
                from models import OrderRequest
                return {"pending_orders_count": OrderRequest.query.filter_by(status="pending").count()}
        except Exception:
            db.session.rollback()
        return {"pending_orders_count": 0}

    # ── Blueprints ─────────────────────────────────────────────────────────
    from auth import auth_bp
    from billing import billing_bp
    from admin import admin_bp
    from api import api_bp
    from officer_app import officer_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(officer_bp)

    # ── Health-check route ─────────────────────────────────────────────────
    from flask import jsonify
    from sqlalchemy import text

    @app.route("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception:
            db_status = "error"
        return jsonify({"status": "ok", "db": db_status})

    # ── Shell context for flask shell ──────────────────────────────────────
    @app.shell_context_processor
    def make_shell_context():
        from models import (
            AdminUser, BusinessSettings, Category, Product,
            Customer, Bill, BillItem, DailySummary, AuditLog, InventoryTransaction,
            MarketingOfficer,
        )
        return {
            "db": db,
            "AdminUser": AdminUser,
            "BusinessSettings": BusinessSettings,
            "Category": Category,
            "Product": Product,
            "Customer": Customer,
            "Bill": Bill,
            "BillItem": BillItem,
            "DailySummary": DailySummary,
            "AuditLog": AuditLog,
            "InventoryTransaction": InventoryTransaction,
            "MarketingOfficer": MarketingOfficer,
        }

    return app


# Allow `flask run` and direct `python app.py`
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
