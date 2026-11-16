"""
owner_app/passkeys.py — the fingerprint lock (WebAuthn) endpoints.

The phone's fingerprint sensor (or its screen-lock PIN/pattern, which Android
offers automatically if the fingerprint fails) signs a one-time challenge from
the server. We verify the signature against the public key saved at set-up, so
there is no password to type and nothing secret stored here.
"""

import time

from flask import Response, g, jsonify, request, session
from webauthn import (
    base64url_to_bytes, generate_authentication_options, generate_registration_options,
    options_to_json, verify_authentication_response, verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorAttachment, AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
    ResidentKeyRequirement, UserVerificationRequirement,
)

from extensions import db
from models import OwnerPasskey
from owner_app import owner_bp
from owner_app.auth import device_required, mark_unlocked
from utils.audit import log_action
from utils.timeutil import now_ist

CHALLENGE_SECONDS = 5 * 60


def _rp_id() -> str:
    return request.host.split(":")[0]


def _origin() -> str:
    return request.host_url.rstrip("/")


def _device_passkeys():
    return OwnerPasskey.query.filter_by(admin_user_id=g.owner.id, device_id=g.owner_device["device_id"]).all()


def _json_options(options) -> Response:
    return Response(options_to_json(options), mimetype="application/json")


def _save_challenge(kind: str, challenge: bytes):
    session["b_challenge"] = {"k": kind, "v": bytes_to_base64url(challenge), "t": int(time.time())}


def _take_challenge(kind: str):
    state = session.pop("b_challenge", None)
    if not state or state.get("k") != kind or time.time() - state.get("t", 0) > CHALLENGE_SECONDS:
        return None
    return base64url_to_bytes(state["v"])


# ── Turn the lock on (once per phone) ──────────────────────────────────────

@owner_bp.route("/passkey/register/options", methods=["POST"])
@device_required
def passkey_register_options():
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name="Impana Gold",
        user_id=str(g.owner.id).encode(),
        user_name=g.owner.username,
        user_display_name=g.owner.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,   # this phone's own sensor
            resident_key=ResidentKeyRequirement.DISCOURAGED,
            user_verification=UserVerificationRequirement.REQUIRED,      # fingerprint or screen lock
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.credential_id)) for p in _device_passkeys()
        ],
    )
    _save_challenge("reg", options.challenge)
    return _json_options(options)


@owner_bp.route("/passkey/register/verify", methods=["POST"])
@device_required
def passkey_register_verify():
    challenge = _take_challenge("reg")
    if not challenge:
        return jsonify({"error": "That took too long. Please try again."}), 400
    try:
        verified = verify_registration_response(
            credential=request.get_json(silent=True) or {},
            expected_challenge=challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            require_user_verification=True,
        )
    except Exception:
        return jsonify({"error": "Could not turn on the fingerprint lock. Please try again."}), 400

    db.session.add(OwnerPasskey(
        admin_user_id=g.owner.id,
        device_id=g.owner_device["device_id"],
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=bytes_to_base64url(verified.credential_public_key),
        sign_count=verified.sign_count,
        label=(request.user_agent.platform or "Phone")[:100],
        last_used_at=now_ist(),
    ))
    log_action(actor_id=g.owner.id, action="CREATE", entity="owner_passkey", ip_address=request.remote_addr,
               new_val={"device": g.owner_device["device_id"][:8]})
    db.session.commit()
    mark_unlocked(g.owner_device)  # registering needed his fingerprint, so he is in
    return jsonify({"ok": True})


# ── Unlock (every time the app opens) ──────────────────────────────────────

@owner_bp.route("/passkey/auth/options", methods=["POST"])
@device_required
def passkey_auth_options():
    keys = _device_passkeys()
    if not keys:
        return jsonify({"error": "Fingerprint lock is not set up on this phone.", "code": "no_lock"}), 409
    options = generate_authentication_options(
        rp_id=_rp_id(),
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.credential_id)) for p in keys],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _save_challenge("auth", options.challenge)
    return _json_options(options)


@owner_bp.route("/passkey/auth/verify", methods=["POST"])
@device_required
def passkey_auth_verify():
    challenge = _take_challenge("auth")
    data = request.get_json(silent=True) or {}
    if not challenge:
        return jsonify({"error": "That took too long. Please try again."}), 400

    key = next((p for p in _device_passkeys() if p.credential_id == data.get("id")), None)
    if not key:
        return jsonify({"error": "This fingerprint is not registered on this phone."}), 400
    try:
        verified = verify_authentication_response(
            credential=data,
            expected_challenge=challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            credential_public_key=base64url_to_bytes(key.public_key),
            credential_current_sign_count=key.sign_count,
            require_user_verification=True,
        )
    except Exception:
        return jsonify({"error": "Could not unlock. Please try again."}), 400

    key.sign_count = verified.new_sign_count
    key.last_used_at = now_ist()
    db.session.commit()
    mark_unlocked(g.owner_device)
    return jsonify({"ok": True})
