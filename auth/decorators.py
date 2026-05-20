"""
auth/decorators.py — Custom route decorators for role-based access control.

Usage:
    @login_required                     — Any authenticated user
    @admin_required                     — Any active admin (staff or superadmin)
    @superadmin_required                — Only superadmin role
"""

from functools import wraps
from flask import redirect, url_for, flash, abort
from flask_login import current_user


def admin_required(f):
    """Allow any authenticated, active admin user (staff or superadmin)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access the admin panel.", "warning")
            return redirect(url_for("auth.login"))
        if not current_user.is_active:
            flash("Your account has been deactivated. Contact superadmin.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def superadmin_required(f):
    """Allow only superadmin role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in.", "warning")
            return redirect(url_for("auth.login"))
        if current_user.role != "superadmin":
            abort(403)
        return f(*args, **kwargs)
    return decorated
