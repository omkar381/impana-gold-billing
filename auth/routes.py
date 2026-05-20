"""
auth/routes.py — Login and logout routes.

Security features:
  - bcrypt password verification (cost 12)
  - Brute-force lockout: 5 consecutive failures → 15-minute block
  - Audit log for LOGIN events
  - CSRF protection via Flask-WTF (form.validate_on_submit)
"""

from datetime import datetime, timedelta
import bcrypt

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user

from auth import auth_bp
from extensions import db
from models import AdminUser
from forms import LoginForm
from utils.audit import log_action

LOCKOUT_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Render login form and authenticate users."""
    if current_user.is_authenticated:
        return redirect(url_for("billing.pos"))

    form = LoginForm()

    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data

        user = AdminUser.query.filter_by(username=username).first()

        # --- User not found ---
        if not user:
            flash("Invalid username or password.", "danger")
            return render_template("login.html", form=form)

        # --- Account inactive ---
        if not user.is_active:
            flash("Your account has been deactivated. Contact admin.", "danger")
            return render_template("login.html", form=form)

        # --- Brute-force lockout check ---
        locked_until = user.locked_until
        if locked_until and locked_until.tzinfo is not None:
            locked_until = locked_until.replace(tzinfo=None)

        if locked_until and datetime.utcnow() < locked_until:
            remaining = int((locked_until - datetime.utcnow()).total_seconds() / 60) + 1
            flash(
                f"Account locked due to too many failed attempts. "
                f"Try again in {remaining} minute(s).",
                "danger",
            )
            return render_template("login.html", form=form)

        # --- Password check ---
        password_correct = bcrypt.checkpw(
            password.encode("utf-8"), user.password_hash.encode("utf-8")
        )

        if not password_correct:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= LOCKOUT_ATTEMPTS:
                user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
                flash(
                    f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.",
                    "danger",
                )
            else:
                remaining_attempts = LOCKOUT_ATTEMPTS - user.failed_login_count
                flash(
                    f"Invalid password. {remaining_attempts} attempt(s) remaining before lockout.",
                    "danger",
                )
            db.session.commit()
            return render_template("login.html", form=form)

        # --- Success ---
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login = datetime.utcnow()
        db.session.commit()

        login_user(user, remember=False)

        log_action(
            actor_id=user.id,
            action="LOGIN",
            entity="admin_users",
            entity_id=user.id,
            ip_address=request.remote_addr,
        )
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

        flash(f"Welcome back, {user.username}!", "success")
        next_page = request.args.get("next")
        return redirect(next_page or url_for("billing.pos"))

    return render_template("login.html", form=form)


@auth_bp.route("/logout")
def logout():
    """Log out the current user."""
    if current_user.is_authenticated:
        log_action(
            actor_id=current_user.id,
            action="LOGOUT",
            entity="admin_users",
            entity_id=current_user.id,
            ip_address=request.remote_addr,
        )
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
