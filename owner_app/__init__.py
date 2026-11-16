"""
owner_app — the owner's installable billing app (PWA), mounted at /b.

Built for one person billing from his own phone:
  * He signs in once with his normal admin account; the phone stays signed in
    for 90 days.
  * Every time the app opens (or comes back after a minute in the background)
    it asks for his fingerprint, falling back to the phone's own screen-lock PIN.
  * Bills are saved with the same routine as the desktop screen.

Auth lives in owner_app/auth.py. The app uses its own cookie and session keys,
so it never mixes with the desktop login or the marketing officer app.
"""

from flask import Blueprint

owner_bp = Blueprint("owner", __name__, url_prefix="/b")

from owner_app import routes  # noqa: E402,F401

try:
    from owner_app import passkeys  # noqa: E402,F401
except ImportError:  # the `webauthn` package is missing: never let that stop desktop billing booting
    import logging
    logging.getLogger(__name__).exception("Owner app fingerprint lock unavailable: pip install -r requirements.txt")
