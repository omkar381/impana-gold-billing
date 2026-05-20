"""api/__init__.py"""
from flask import Blueprint

api_bp = Blueprint("api", __name__)

from api import routes  # noqa: F401, E402
