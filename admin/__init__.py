"""admin/__init__.py"""
from flask import Blueprint

admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")

from admin import routes  # noqa: F401, E402
