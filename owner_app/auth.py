"""
owner_app/auth.py — who is allowed into the owner app, and whether it is unlocked.

Two separate things:

  1. Signed-in phone  — a signed cookie (`ig_owner_device`) that lasts 90 days.
     Created by the admin password. Ends early if the admin deactivates the
     account or changes the password.
  2. Unlocked         — a short-lived marker in the session, set only after the
     phone's fingerprint (or screen-lock PIN) is verified on the server.
     It lapses after 10 idle minutes, and the app also drops it whenever it
     opens fresh or has been in the background for a minute.

Pages and JSON calls that touch money or customers need BOTH.
"""

import time
import uuid
from functools import wraps

from flask import current_app, g, jsonify, redirect, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from extensions import db
from models import AdminUser, OwnerPasskey

DEVICE_COOKIE = "ig_owner_device"
DEVICE_DAYS = 90
UNLOCK_IDLE_SECONDS = 10 * 60
_CACHE_KEY = "impana.owner_device"


# ── The signed-in phone (90 days) ──────────────────────────────────────────

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="impana-owner-device")


def _fingerprint(user: AdminUser) -> str:
    # Changes when the password changes, which signs every phone out.
    return (user.password_hash or "")[-16:]


def issue_device_cookie(response, user: AdminUser, device_id: str = None, no_lock: bool = False):
    payload = {
        "u": user.id,
        "d": device_id or uuid.uuid4().hex,
        "f": _fingerprint(user),
        "nl": 1 if no_lock else 0,  # phone with no fingerprint hardware; set once at setup
    }
    response.set_cookie(
        DEVICE_COOKIE, _serializer().dumps(payload),
        max_age=DEVICE_DAYS * 24 * 3600, httponly=True, samesite="Lax",
        secure=request.is_secure, path="/b",
    )
    return payload["d"]


def clear_device_cookie(response):
    response.delete_cookie(DEVICE_COOKIE, path="/b")


def current_device():
    """The signed-in owner on this phone, or None. Cached for this request only."""
    if _CACHE_KEY in request.environ:
        return request.environ[_CACHE_KEY]
    request.environ[_CACHE_KEY] = None
    device = None
    raw = request.cookies.get(DEVICE_COOKIE)
    if raw:
        try:
            payload, signed_at = _serializer().loads(
                raw, max_age=DEVICE_DAYS * 24 * 3600, return_timestamp=True
            )
        except (BadSignature, SignatureExpired):
            payload = None
        if payload:
            user = db.session.get(AdminUser, payload.get("u") or 0)
            if user and user.is_active and payload.get("f") == _fingerprint(user):
                device = {
                    "user": user, "device_id": payload["d"], "no_lock": bool(payload.get("nl")),
                    "signed_at": signed_at,
                }
    request.environ[_CACHE_KEY] = device
    return device


# ── Lock state ─────────────────────────────────────────────────────────────

def has_passkey(device) -> bool:
    return db.session.query(OwnerPasskey.id).filter_by(
        admin_user_id=device["user"].id, device_id=device["device_id"]
    ).first() is not None


def mark_unlocked(device):
    session["b_unlock"] = {"u": device["user"].id, "d": device["device_id"], "t": int(time.time())}


def mark_locked():
    session.pop("b_unlock", None)


def is_unlocked(device) -> bool:
    if device["no_lock"]:
        return True
    state = session.get("b_unlock")
    if not state or state.get("u") != device["user"].id or state.get("d") != device["device_id"]:
        return False
    if time.time() - state.get("t", 0) > UNLOCK_IDLE_SECONDS:
        mark_locked()
        return False
    state["t"] = int(time.time())  # sliding: stays unlocked while he is working
    session["b_unlock"] = state
    return True


# ── Decorators ─────────────────────────────────────────────────────────────

def _wants_json() -> bool:
    return request.is_json or request.path.startswith("/b/api/") or request.accept_mimetypes.best == "application/json"


def device_required(view):
    """Signed in on this phone (password done). Used by the lock and setup screens."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        device = current_device()
        if not device:
            if _wants_json():
                return jsonify({"error": "Please sign in again.", "code": "signed_out"}), 401
            return redirect(url_for("owner.login"))
        g.owner = device["user"]
        g.owner_device = device
        return view(*args, **kwargs)
    return wrapped


def owner_required(view):
    """Signed in AND unlocked with the fingerprint."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        device = current_device()
        if not device:
            if _wants_json():
                return jsonify({"error": "Please sign in again.", "code": "signed_out"}), 401
            return redirect(url_for("owner.login"))
        g.owner = device["user"]
        g.owner_device = device

        if not device["no_lock"] and not has_passkey(device):
            if _wants_json():
                return jsonify({"error": "Set up the fingerprint lock first.", "code": "no_lock"}), 403
            return redirect(url_for("owner.setup_lock"))
        if not is_unlocked(device):
            if _wants_json():
                return jsonify({"error": "Locked. Unlock with your fingerprint.", "code": "locked"}), 401
            return redirect(url_for("owner.lock", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped
