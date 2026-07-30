"""
config.py — Application configuration classes.
Loaded by the app factory (app.py) via FLASK_ENV environment variable.
All secrets are read from .env (never hardcoded here).
"""

import os
try:
    from dotenv import load_dotenv
    import sys

    # Load .env file from the correct directory (supports PyInstaller)
    if getattr(sys, 'frozen', False):
        basedir = os.path.dirname(sys.executable)
    else:
        basedir = os.path.dirname(__file__)

    env_path = os.path.join(basedir, '.env')
    load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed — hardcoded values will be used


class BaseConfig:
    """Shared settings across all environments."""

    # Flask core
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    WTF_CSRF_ENABLED = True

    # SQLAlchemy — PRODUCTION Neon Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", 
        "postgresql://neondb_owner:npg_2CZtvbkl1gFO@ep-damp-sun-aobcdfmv.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,          # Detect stale connections
        "pool_recycle": 300,            # Recycle connections every 5 minutes
        "pool_size": 10,
        "max_overflow": 20,
    }

    # File uploads
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB


class DevelopmentConfig(BaseConfig):
    """Development — verbose errors, no HTTPS enforcement."""
    DEBUG = True
    TESTING = False
    TEMPLATES_AUTO_RELOAD = True


class ProductionConfig(BaseConfig):
    """Production — strict security, no debug output."""
    DEBUG = False
    TESTING = False
    # Force HTTPS cookies in production
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = True


class TestingConfig(BaseConfig):
    """Testing — in-memory SQLite, no CSRF."""
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


# Map FLASK_ENV string → config class
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
