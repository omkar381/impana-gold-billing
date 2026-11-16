"""Shared test setup: every test runs on a throwaway in-memory SQLite database."""

import os

import tempfile

# app.py builds a module-level app on import, so point it at a throwaway file
# database first. Tests never touch a real database.
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "import.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import bcrypt
import pytest

from app import create_app
from extensions import db
from models import AdminUser, BusinessSettings, Category, Customer, Product

OWNER_USER = "owner"
OWNER_PASS = "Owner@12345"


@pytest.fixture()
def app():
    app = create_app("testing")
    # No context is held open while a test runs, so every request gets its own
    # (like production) and nothing is cached between requests.
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(
            AdminUser(
                username=OWNER_USER,
                password_hash=bcrypt.hashpw(OWNER_PASS.encode(), bcrypt.gensalt(rounds=4)).decode(),
                role="superadmin",
            )
        )
        for key, value in {"gst_enabled": "true", "bill_prefix": "IG", "bill_counter_reset": "daily"}.items():
            db.session.add(BusinessSettings(key=key, value=value))
        cat = Category(name="Rava", sort_order=1)
        db.session.add(cat)
        db.session.flush()
        db.session.add_all(
            [
                Product(name="Rava 30kg", sku="RAVA", category_id=cat.id, price_per_unit="50.00",
                        unit="kg", gst_rate="5", hsn_code="1104", stock_qty="500"),
                Product(name="Tofu", sku="TOFU", category_id=cat.id, price_per_unit="35.00",
                        unit="pcs", gst_rate="0", stock_qty="10"),
                Product(name="Empty", sku="EMPTY", category_id=cat.id, price_per_unit="10.00",
                        unit="pcs", gst_rate="12", stock_qty="0"),
            ]
        )
        db.session.add(Customer(name="Ravi Stores", phone="+91 98765 43210"))
        db.session.commit()
        db.session.remove()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(client, app):
    """A client signed in to the desktop screen."""
    client.post("/login", data={"username": OWNER_USER, "password": OWNER_PASS})
    return client
