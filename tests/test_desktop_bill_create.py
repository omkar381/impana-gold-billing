"""Characterisation tests: the desktop /bill/create behaviour that must not change."""

from decimal import Decimal

from extensions import db
from models import Bill, Customer, InventoryTransaction, Product


def _pid(client, sku):
    with client.application.app_context():
        return Product.query.filter_by(sku=sku).first().id


def _post(client, **overrides):
    body = {
        "items": [{"product_id": _pid(client, "RAVA"), "qty": 2, "unit_price": 50}],
        "payment_mode": "cash",
        "customer_name": "", "customer_phone": "",
    }
    body.update(overrides)
    return client.post("/bill/create", json=body)


def test_requires_login(client):
    assert client.post("/bill/create", json={"items": []}).status_code in (302, 401)


def test_basic_cash_bill_with_gst(admin_client, app):
    r = _post(admin_client)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["status"] == "confirmed" and data["bill_number"].startswith("IG-")
    with app.app_context():
        b = db.session.get(Bill, data["bill_id"])
        assert b.subtotal == Decimal("100.00")
        assert b.gst_amount == Decimal("5.00")          # 5% of 100
        assert b.grand_total == Decimal("105.00")
        assert Product.query.filter_by(sku="RAVA").first().stock_qty == Decimal("498.000")
        assert InventoryTransaction.query.count() == 1


def test_bag_of_30kg_is_gst_free_but_loose_is_not(admin_client, app):
    r = _post(admin_client, items=[{"product_id": _pid(admin_client, "RAVA"), "qty": 30, "unit_price": 50}])
    with app.app_context():
        assert db.session.get(Bill, r.get_json()["bill_id"]).gst_amount == Decimal("0.00")
    r = _post(admin_client, items=[{"product_id": _pid(admin_client, "RAVA"), "qty": 30, "unit_price": 50, "is_loose": True}])
    with app.app_context():
        b = db.session.get(Bill, r.get_json()["bill_id"])
        assert b.gst_amount == Decimal("75.00")
        assert b.items[0].product_name.endswith("(Loose)")


def test_flat_and_percent_discount(admin_client, app):
    r = _post(admin_client, discount_type="flat", discount_amount=10)
    with app.app_context():
        b = db.session.get(Bill, r.get_json()["bill_id"])
        assert (b.discount_amount, b.taxable_amount, b.grand_total) == (Decimal("10.00"), Decimal("90.00"), Decimal("95.00"))
    r = _post(admin_client, discount_type="percent", discount_amount=10)
    with app.app_context():
        assert db.session.get(Bill, r.get_json()["bill_id"]).discount_amount == Decimal("10.00")


def test_overall_gst_override(admin_client, app):
    r = _post(admin_client, apply_overall_gst=True, overall_gst_rate=5,
              items=[{"product_id": _pid(admin_client, "TOFU"), "qty": 2, "unit_price": 35}])
    with app.app_context():
        assert db.session.get(Bill, r.get_json()["bill_id"]).gst_amount == Decimal("3.50")


def test_customer_created_and_reused_by_phone(admin_client, app):
    _post(admin_client, customer_name="New Shop", customer_phone="9000000001")
    _post(admin_client, customer_name="New Shop Renamed", customer_phone="9000000001")
    with app.app_context():
        rows = Customer.query.filter_by(phone="9000000001").all()
        assert len(rows) == 1 and rows[0].name == "New Shop Renamed"


def test_validation_errors(admin_client):
    assert _post(admin_client, items=[]).status_code == 400
    assert _post(admin_client, payment_mode="bitcoin").status_code == 400
    r = _post(admin_client, items=[{"product_id": _pid(admin_client, "EMPTY"), "qty": 1, "unit_price": 10}])
    assert r.status_code == 400 and "Insufficient stock" in r.get_json()["error"]


def test_draft_status_does_not_move_stock(admin_client, app):
    r = _post(admin_client, status="draft")
    assert r.status_code == 200
    with app.app_context():
        assert Product.query.filter_by(sku="RAVA").first().stock_qty == Decimal("500.000")


def test_bill_numbers_are_sequential(admin_client):
    a = _post(admin_client).get_json()["bill_number"]
    b = _post(admin_client).get_json()["bill_number"]
    assert int(b.rsplit("-", 1)[1]) == int(a.rsplit("-", 1)[1]) + 1
