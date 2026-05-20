"""
api/routes.py — JSON API endpoints for Impana Gold.

GET /api/products/search?q=<query>          → search by name/SKU/barcode
GET /api/products/search?barcode=<code>     → exact barcode lookup
GET /api/customers/search?q=<phone_or_name> → typeahead for billing screen
"""

from flask import jsonify, request
from flask_login import login_required

from api import api_bp
from models import Product, Customer
from extensions import db
from sqlalchemy import or_


@api_bp.route("/products/search")
@login_required
def products_search():
    """
    Fast product search. Returns up to 20 results.
    Supports:
      ?q=<text>          — name/SKU/barcode contains text
      ?barcode=<code>    — exact barcode match
    """
    barcode = request.args.get("barcode", "").strip()
    q = request.args.get("q", "").strip()

    query = Product.query.filter(
        Product.is_active == True,
        Product.deleted_at == None,
    )

    if barcode:
        query = query.filter(Product.barcode == barcode)
    elif q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.barcode.ilike(like),
            )
        )
    else:
        # Return all active products (for initial load)
        pass

    products = query.order_by(Product.name).limit(50).all()

    return jsonify(
        [
            {
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "price": float(p.price_per_unit),
                "unit": p.unit,
                "weight_grams": p.weight_grams,
                "gst_rate": float(p.gst_rate),
                "hsn_code": p.hsn_code or "",
                "barcode": p.barcode or "",
                "category_id": p.category_id,
            }
            for p in products
        ]
    )


@api_bp.route("/customers/search")
@login_required
def customers_search():
    """
    Customer typeahead for billing screen.
    ?q=<phone_or_name>  — returns up to 10 matching customers
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    like = f"%{q}%"
    customers = (
        Customer.query.filter(
            Customer.deleted_at == None,
            or_(Customer.name.ilike(like), Customer.phone.ilike(like)),
        )
        .limit(10)
        .all()
    )

    return jsonify(
        [
            {
                "id": c.id,
                "name": c.name,
                "phone": c.phone or "",
                "address": c.address or "",
                "gstin": c.gstin or "",
            }
            for c in customers
        ]
    )
