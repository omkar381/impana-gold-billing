"""
Seed script for Impana Gold Billing System.
Creates default business settings, categories, products, and a superadmin.
"""

import os
import bcrypt

from app import create_app
from extensions import db
from models import AdminUser, BusinessSettings, Category, Product


DEFAULT_SETTINGS = {
    "shop_name": "Impana Gold",
    "tagline": "Manufacturing & Supply of Premium Quality Rava and Poha",
    "address_line1": "Plot No. 1, Industrial Area",
    "address_line2": "",
    "city": "Hubli",
    "state": "Karnataka",
    "state_code": "29",
    "pincode": "580001",
    "phone": "9876543210",
    "phone2": "",
    "email": "",
    "website": "",
    "gstin": "",
    "fssai": "",
    "iso_certification": "",
    "logo_path": "",
    "fssai_logo_path": "",
    "iso_logo_path": "",
    "other_cert_logo_path": "",
    "bill_prefix": "IG",
    "gst_enabled": "true",
    "bill_counter_reset": "daily",
    "bank_name": "",
    "bank_branch": "",
    "bank_account": "",
    "bank_ifsc": "",
    "upi_id": "",
    "terms_conditions": "Goods once sold will not be taken back.\nSubject to local jurisdiction.",
    "declaration": "We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.",
    "signature_name": "FOR M/S Sri Devi Industries",
}

CATEGORIES = [
    {"name": "Rava/Poha", "sort_order": 1},
    {"name": "Other", "sort_order": 2},
]

PRODUCTS = [
    {
        "name": "Impana Gold Bombay Rava",
        "sku": "IG-BRAVA",
        "price_per_unit": 60.00,
        "unit": "kg",
        "weight_grams": 1000,
        "gst_rate": 5,
        "hsn_code": "1103",
        "category": "Rava/Poha",
    },
    {
        "name": "Impana Gold Bansi Rava",
        "sku": "IG-BNSR",
        "price_per_unit": 62.00,
        "unit": "kg",
        "weight_grams": 1000,
        "gst_rate": 5,
        "hsn_code": "1103",
        "category": "Rava/Poha",
    },
    {
        "name": "Impana Gold Idli Rava",
        "sku": "IG-IDLR",
        "price_per_unit": 58.00,
        "unit": "kg",
        "weight_grams": 1000,
        "gst_rate": 5,
        "hsn_code": "1103",
        "category": "Rava/Poha",
    },
    {
        "name": "Impana Gold Nylon Poha",
        "sku": "IG-NYLPO",
        "price_per_unit": 45.00,
        "unit": "kg",
        "weight_grams": 1000,
        "gst_rate": 5,
        "hsn_code": "1104",
        "category": "Rava/Poha",
    },
    {
        "name": "Impana Gold Deluxe Poha",
        "sku": "IG-DLXPO",
        "price_per_unit": 52.00,
        "unit": "kg",
        "weight_grams": 1000,
        "gst_rate": 5,
        "hsn_code": "1104",
        "category": "Rava/Poha",
    },
    {
        "name": "Impana Gold Tofu",
        "sku": "IG-TOFU",
        "price_per_unit": 35.00,
        "unit": "pcs",
        "weight_grams": None,
        "gst_rate": 0,
        "hsn_code": "",
        "category": "Other",
    },
]


def seed_admin() -> None:
    username = os.environ.get("SEED_ADMIN_USERNAME", "admin")
    password = os.environ.get("SEED_ADMIN_PASSWORD", "ChangeMe@123")

    existing = AdminUser.query.filter_by(username=username).first()
    if existing:
        return

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

    user = AdminUser(
        username=username,
        password_hash=password_hash,
        role="superadmin",
        is_active=True,
    )
    db.session.add(user)


def seed_settings() -> None:
    for key, value in DEFAULT_SETTINGS.items():
        exists = BusinessSettings.query.filter_by(key=key).first()
        if exists:
            continue
        db.session.add(BusinessSettings(key=key, value=value))


def seed_categories() -> None:
    for item in CATEGORIES:
        existing = Category.query.filter_by(name=item["name"]).first()
        if existing:
            continue
        db.session.add(Category(name=item["name"], sort_order=item["sort_order"]))


def seed_products() -> None:
    categories = {c.name: c for c in Category.query.all()}
    for item in PRODUCTS:
        existing = Product.query.filter_by(sku=item["sku"]).first()
        if existing:
            continue
        category = categories.get(item["category"])
        db.session.add(
            Product(
                name=item["name"],
                sku=item["sku"],
                category_id=category.id if category else None,
                price_per_unit=item["price_per_unit"],
                unit=item["unit"],
                weight_grams=item["weight_grams"],
                gst_rate=item["gst_rate"],
                hsn_code=item.get("hsn_code", ""),
                stock_qty=0,
                is_active=True,
            )
        )


def main() -> None:
    app = create_app()
    with app.app_context():
        seed_admin()
        seed_settings()
        seed_categories()
        seed_products()
        db.session.commit()
        print("Seed completed successfully.")


if __name__ == "__main__":
    main()
