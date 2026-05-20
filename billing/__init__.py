"""billing/__init__.py"""
from flask import Blueprint

billing_bp = Blueprint("billing", __name__)

from billing import routes  # noqa: F401, E402
