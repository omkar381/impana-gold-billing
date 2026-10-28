"""
officer_app — the marketing officer's installable web app (PWA), mounted at /m.

Officers sign in with their phone number and a password set by the superadmin.
They are NOT AdminUser accounts: they use their own session key, so nothing an
officer holds can open the billing screen or any /admin page.
"""

from flask import Blueprint

officer_bp = Blueprint("officer", __name__, url_prefix="/m")

from officer_app import routes  # noqa: E402,F401
