"""The owner's phone app (/b): sign-in, lock rules, bill saving, buyer link."""

import time
from datetime import timedelta
from decimal import Decimal

import pytest
from itsdangerous import URLSafeTimedSerializer

from extensions import db
from models import AdminUser, Bill, Customer, OwnerPasskey, Product
from tests.conftest import OWNER_PASS, OWNER_USER
from utils.bill_link import bill_id_from_token, bill_token, is_mobile, phone10


def _device(client, app):
    cookie = client.get_cookie("ig_owner_device", path="/b")
    assert cookie is not None, "device cookie was not set"
    ser = URLSafeTimedSerializer(app.secret_key, salt="impana-owner-device")
    return ser.loads(cookie.value)


def sign_in(client):
    return client.post("/b/login", data={"username": OWNER_USER, "password": OWNER_PASS})


def unlock(client, app):
    """Pretend the fingerprint check passed (the real check is covered by the browser test)."""
    payload = _device(client, app)
    with app.app_context():
        db.session.add(OwnerPasskey(
            admin_user_id=payload["u"], device_id=payload["d"],
            credential_id=f"cred-{payload['d']}", public_key="key",
        ))
        db.session.commit()
    with client.session_transaction() as s:
        s["b_unlock"] = {"u": payload["u"], "d": payload["d"], "t": int(time.time())}


@pytest.fixture()
def phone(client, app):
    sign_in(client)
    unlock(client, app)
    return client


def pid(app, sku):
    with app.app_context():
        return Product.query.filter_by(sku=sku).first().id


def bill_body(app, **over):
    body = {
        "items": [{"product_id": pid(app, "RAVA"), "qty": 2, "unit_price": 50}],
        "buyer": {"name": "", "phone": ""},
        "payment_mode": "upi",
    }
    body.update(over)
    return body


# ── Sign in and the 90-day phone login ─────────────────────────────────────

def test_pages_need_sign_in(client):
    for path in ("/b/", "/b/bills", "/b/account"):
        r = client.get(path)
        assert r.status_code == 302 and "/b/login" in r.headers["Location"]
    r = client.get("/b/api/products")
    assert r.status_code == 401 and r.get_json()["code"] == "signed_out"


def test_wrong_password_is_refused_and_locks_out_after_five(client, app):
    for _ in range(5):
        r = client.post("/b/login", data={"username": OWNER_USER, "password": "nope"})
        assert r.status_code == 200 and b"Wrong username or password" in r.data
    r = sign_in(client)  # even the right password is refused while locked
    assert r.status_code == 200 and b"Too many wrong attempts" in r.data
    assert client.get_cookie("ig_owner_device", path="/b") is None


def test_sign_in_sets_a_90_day_cookie_and_goes_to_lock_setup(client, app):
    r = sign_in(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/b/setup-lock")
    header = next(h for h in r.headers.getlist("Set-Cookie") if h.startswith("ig_owner_device="))
    assert "Max-Age=7776000" in header and "HttpOnly" in header and "Path=/b" in header


def test_phone_login_expires_after_90_days(client, app):
    sign_in(client)
    payload = _device(client, app)
    old = URLSafeTimedSerializer(app.secret_key, salt="impana-owner-device")
    # A token signed 91 days ago must be rejected.
    import itsdangerous.timed as timed
    real_time = time.time
    orig = timed.time.time
    timed.time.time = lambda: real_time() - 91 * 86400
    try:
        stale = old.dumps(payload)
    finally:
        timed.time.time = orig
    client.set_cookie("ig_owner_device", stale, path="/b")
    r = client.get("/b/bills")
    assert r.status_code == 302 and "/b/login" in r.headers["Location"]


def test_password_change_signs_the_phone_out(client, app):
    sign_in(client)
    with app.app_context():
        user = AdminUser.query.filter_by(username=OWNER_USER).first()
        user.password_hash = user.password_hash[:-16] + "x" * 16
        db.session.commit()
    assert client.get("/b/bills").status_code == 302


def test_deactivated_admin_is_signed_out_at_once(phone, app):
    assert phone.get("/b/api/products").status_code == 200
    with app.app_context():
        AdminUser.query.filter_by(username=OWNER_USER).first().is_active = False
        db.session.commit()
    assert phone.get("/b/api/products").status_code == 401


def test_logout_removes_this_phones_fingerprint_and_cookie(phone, app):
    assert phone.post("/b/logout").status_code == 302
    with app.app_context():
        assert OwnerPasskey.query.count() == 0
    assert phone.get("/b/bills").status_code == 302


# ── The fingerprint lock is enforced on the server ─────────────────────────

def test_signed_in_but_no_fingerprint_set_up_cannot_use_the_app(client, app):
    sign_in(client)
    r = client.get("/b/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/b/setup-lock")
    r = client.get("/b/api/products")
    assert r.status_code == 403 and r.get_json()["code"] == "no_lock"


def test_locked_app_refuses_pages_and_data(phone, app):
    phone.get("/b/lock")  # opening the lock screen drops the unlocked state
    r = phone.get("/b/bills")
    assert r.status_code == 302 and "/b/lock" in r.headers["Location"]
    r = phone.get("/b/api/products")
    assert r.status_code == 401 and r.get_json()["code"] == "locked"
    assert phone.post("/b/api/bills", json=bill_body(app)).status_code == 401


def test_unlock_lapses_after_ten_idle_minutes(phone, app):
    assert phone.get("/b/api/products").status_code == 200
    with phone.session_transaction() as s:
        s["b_unlock"] = {**s["b_unlock"], "t": int(time.time()) - 11 * 60}
    assert phone.get("/b/api/products").status_code == 401


def test_unlock_from_another_phone_does_not_carry_over(phone, app):
    with phone.session_transaction() as s:
        s["b_unlock"] = {**s["b_unlock"], "d": "some-other-phone"}
    assert phone.get("/b/api/products").status_code == 401


def test_phone_without_fingerprint_hardware_can_continue_without_lock(client, app):
    sign_in(client)
    assert client.post("/b/setup-lock/skip").status_code == 302
    assert client.get("/b/api/products").status_code == 200


def test_skip_is_not_available_once_a_fingerprint_exists(phone, app):
    phone.get("/b/lock")
    assert phone.post("/b/setup-lock/skip").status_code == 302
    assert phone.get("/b/api/products").status_code == 401  # still locked


def test_open_redirect_is_blocked_on_the_lock_screen(phone):
    r = phone.get("/b/lock?next=https://evil.example/")
    assert b"evil.example" not in r.data


# ── Products, buyers, saving a bill ────────────────────────────────────────

def test_products_api_lists_active_products_with_stock(phone):
    data = phone.get("/b/api/products").get_json()
    names = {p["name"]: p for p in data["products"]}
    assert names["Rava 30kg"]["stock"] == 500 and names["Rava 30kg"]["gst"] == 5
    assert names["Empty"]["stock"] == 0


def test_save_bill_matches_the_desktop_totals(phone, app):
    r = phone.post("/b/api/bills", json=bill_body(app))
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        b = db.session.get(Bill, r.get_json()["id"])
        assert (b.subtotal, b.gst_amount, b.grand_total) == (Decimal("100.00"), Decimal("5.00"), Decimal("105.00"))
        assert b.payment_mode == "upi" and b.operator.username == OWNER_USER
        assert Product.query.filter_by(sku="RAVA").first().stock_qty == Decimal("498.000")


def test_existing_buyer_is_found_by_number_even_if_stored_with_country_code(phone, app):
    r = phone.post("/b/api/bills", json=bill_body(app, buyer={"name": "Ravi", "phone": "98765 43210"}))
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        assert Customer.query.count() == 1           # no duplicate of "+91 98765 43210"
        assert db.session.get(Bill, r.get_json()["id"]).customer.name == "Ravi"


def test_new_buyer_is_created_with_a_clean_ten_digit_number(phone, app):
    r = phone.post("/b/api/bills", json=bill_body(app, buyer={"name": "Lakshmi Traders", "phone": "+91 90000-11111"}))
    with app.app_context():
        assert Customer.query.filter_by(phone="9000011111").one().name == "Lakshmi Traders"
        assert r.status_code == 200


def test_bad_mobile_number_is_refused(phone, app):
    r = phone.post("/b/api/bills", json=bill_body(app, buyer={"name": "X", "phone": "12345"}))
    assert r.status_code == 400 and "10-digit" in r.get_json()["error"]


@pytest.mark.parametrize("items", [
    [], "nope", [{"product_id": 1, "qty": "abc", "unit_price": 5}],
    [{"product_id": 1, "qty": -1, "unit_price": 5}], [{"product_id": 1, "qty": 1, "unit_price": 0}],
    [{"qty": 1, "unit_price": 5}],
])
def test_bad_carts_are_refused_cleanly(phone, app, items):
    r = phone.post("/b/api/bills", json=bill_body(app, items=items))
    assert r.status_code == 400 and r.get_json()["error"]


def test_not_enough_stock_is_refused_with_a_clear_message(phone, app):
    body = bill_body(app, items=[{"product_id": pid(app, "TOFU"), "qty": 11, "unit_price": 35}])
    r = phone.post("/b/api/bills", json=body)
    assert r.status_code == 400 and "Insufficient stock" in r.get_json()["error"]


def test_walk_in_bill_without_buyer_is_allowed(phone, app):
    r = phone.post("/b/api/bills", json=bill_body(app))
    with app.app_context():
        assert db.session.get(Bill, r.get_json()["id"]).customer_id is None


def test_discount_applies(phone, app):
    r = phone.post("/b/api/bills", json=bill_body(app, discount_type="percent", discount_amount="10"))
    with app.app_context():
        b = db.session.get(Bill, r.get_json()["id"])
        assert b.discount_amount == Decimal("10.00") and b.grand_total == Decimal("95.00")


# ── Bills list and one bill ────────────────────────────────────────────────

def test_bills_list_search_and_detail(phone, app):
    phone.post("/b/api/bills", json=bill_body(app, buyer={"name": "Ravi", "phone": "9876543210"}))
    phone.post("/b/api/bills", json=bill_body(app, buyer={"name": "Sunita Foods", "phone": "9000000002"}))
    page = phone.get("/b/bills")
    assert page.status_code == 200 and b"Ravi" in page.data and b"Sunita Foods" in page.data and b"Today" in page.data
    found = phone.get("/b/bills?q=sunita&partial=1").data
    assert b"Sunita Foods" in found and b"Ravi" not in found
    assert b"Ravi" in phone.get("/b/bills?q=98765&partial=1").data          # by mobile
    assert b"No bills found" in phone.get("/b/bills?q=zzz&partial=1").data

    with app.app_context():
        bill_id = Bill.query.first().id
    detail = phone.get(f"/b/bill/{bill_id}")
    assert detail.status_code == 200 and b"Send on WhatsApp" in detail.data and b"https://wa.me/91" in detail.data


def test_whatsapp_link_goes_to_the_buyer_with_the_message_typed(phone, app):
    r = phone.post("/b/api/bills", json=bill_body(app, buyer={"name": "Ravi", "phone": "9876543210"}))
    page = phone.get(f"/b/bill/{r.get_json()['id']}?new=1").data.decode()
    assert "https://wa.me/919876543210?text=" in page
    assert "Thank%20you%20for%20shopping%20at%20Impana%20Gold" in page
    assert "%2Fr%2F" in page                       # the signed link to the bill is in the message


def test_adding_the_buyer_number_afterwards_builds_the_whatsapp_link(phone, app):
    r = phone.post("/b/api/bills", json=bill_body(app))
    bill_id = r.get_json()["id"]
    assert b"Buyer" in phone.get(f"/b/bill/{bill_id}").data and b"wa-phone" in phone.get(f"/b/bill/{bill_id}").data
    bad = phone.post(f"/b/api/bills/{bill_id}/phone", json={"phone": "123"})
    assert bad.status_code == 400
    ok = phone.post(f"/b/api/bills/{bill_id}/phone", json={"phone": "98000 12345", "name": "Anil"})
    assert ok.status_code == 200 and ok.get_json()["wa_url"].startswith("https://wa.me/919800012345?text=")
    with app.app_context():
        assert db.session.get(Bill, bill_id).customer.phone == "9800012345"


def test_draft_bills_are_hidden(phone, app):
    with app.app_context():
        from utils.billing_service import save_bill
        user = AdminUser.query.first()
        draft = save_bill({"items": [{"product_id": pid(app, "RAVA"), "qty": 1, "unit_price": 50}], "status": "draft"}, user.id)
        draft_id = draft.id
    assert phone.get(f"/b/bill/{draft_id}").status_code == 404


# ── The buyer's link ───────────────────────────────────────────────────────

def _make_bill(phone, app, **kw):
    return phone.post("/b/api/bills", json=bill_body(app, **kw)).get_json()["id"]


def test_buyer_link_opens_the_original_only_without_login(phone, app, client):
    bill_id = _make_bill(phone, app, buyer={"name": "Ravi", "phone": "9876543210"})
    with app.app_context():
        token = bill_token(bill_id)
    stranger = app.test_client()                    # no cookies at all
    r = stranger.get(f"/r/{token}")
    html = r.data.decode()
    assert r.status_code == 200
    assert "ORIGINAL" in html and "DUPLICATE" not in html
    assert "Save as PDF" in html and "Back to POS" not in html and "Print Invoice" not in html
    assert 'content="width=560"' in html
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow" and "no-store" in r.headers["Cache-Control"]


def test_forged_or_altered_links_find_nothing(phone, app):
    bill_id = _make_bill(phone, app)
    with app.app_context():
        token = bill_token(bill_id)
    stranger = app.test_client()
    assert stranger.get(f"/r/{token[:-2]}xx").status_code == 404      # signature changed
    assert stranger.get("/r/1").status_code == 404                     # plain id
    assert stranger.get("/r/MQ.AAAA").status_code == 404
    with app.app_context():
        assert bill_id_from_token("garbage") is None


def test_cancelled_bill_link_says_cancelled(phone, app):
    bill_id = _make_bill(phone, app)
    with app.app_context():
        db.session.get(Bill, bill_id).status = "cancelled"
        db.session.commit()
        token = bill_token(bill_id)
    r = app.test_client().get(f"/r/{token}")
    assert r.status_code == 410 and b"cancelled" in r.data.lower()


def test_phone_number_helpers():
    assert phone10("+91 98765-43210") == "9876543210"
    assert is_mobile("98765 43210") and is_mobile("+919876543210") and is_mobile("09876543210")
    assert not is_mobile("12345") and not is_mobile("5876543210") and not is_mobile("")


# ── PWA plumbing ───────────────────────────────────────────────────────────

def test_manifest_and_service_worker_are_public_and_scoped(client):
    m = client.get("/b/manifest.webmanifest").get_json()
    assert m["start_url"] == "/b/" and m["scope"] == "/b/" and m["display"] == "standalone"
    sw = client.get("/b/sw.js")
    assert sw.headers["Service-Worker-Allowed"] == "/b/" and sw.status_code == 200
    assert client.get("/b/offline").status_code == 200


def test_owner_pages_are_never_cached(phone):
    assert phone.get("/b/").headers["Cache-Control"] == "no-store"


def test_buyer_suggestions_recent_first_then_newest_customers(phone, app):
    # Nobody billed yet: newest customers are offered
    assert [c["name"] for c in phone.get("/b/api/customers").get_json()] == ["Ravi Stores"]
    with app.app_context():
        db.session.add(Customer(name="Zed Traders", phone="9111111111"))
        db.session.commit()
    phone.post("/b/api/bills", json=bill_body(app, buyer={"name": "Ravi Stores", "phone": "9876543210"}))
    names = [c["name"] for c in phone.get("/b/api/customers").get_json()]
    assert names[0] == "Ravi Stores" and "Zed Traders" in names   # billed buyer first, no duplicates
    assert len(names) == len(set(names))
    assert [c["name"] for c in phone.get("/b/api/customers?q=98765").get_json()] == ["Ravi Stores"]


def test_buyer_saved_with_only_a_number_is_greeted_without_a_fake_name(phone, app):
    r = phone.post("/b/api/bills", json=bill_body(app, buyer={"name": "", "phone": "9845012345"}))
    page = phone.get(f"/b/bill/{r.get_json()['id']}").data.decode()
    assert "https://wa.me/919845012345?text=Hello%2C%0A" in page   # "Hello," not "Hello Customer,"


# ── Nothing that already worked is disturbed ───────────────────────────────

def test_existing_screens_still_work(client, app):
    assert client.get("/login").status_code == 200            # desktop sign-in
    assert client.get("/m/login").status_code == 200          # marketing officer app
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 302                 # desktop POS still needs the desktop login
    client.post("/login", data={"username": OWNER_USER, "password": OWNER_PASS})
    assert client.get("/").status_code == 200
    assert client.get("/b/api/products").status_code == 401   # the desktop login does NOT open the phone app


def test_desktop_print_and_pdf_pages_still_render(admin_client, app):
    with app.app_context():
        pid_ = Product.query.filter_by(sku="RAVA").first().id
    bill_id = admin_client.post("/bill/create", json={
        "items": [{"product_id": pid_, "qty": 1, "unit_price": 50}], "payment_mode": "cash"}).get_json()["bill_id"]
    html = admin_client.get(f"/bill/{bill_id}/print").data.decode()
    assert "ORIGINAL" in html and "DUPLICATE" in html and "Print Invoice" in html   # both copies, staff buttons
    assert 'content="width=device-width, initial-scale=1"' in html


def test_bag_line_and_loose_line_of_the_same_product_on_one_bill(phone, app):
    """Like the desktop: 60 kg of bags (no GST) plus 5 kg loose (GST charged) as two lines."""
    rava = pid(app, "RAVA")
    r = phone.post("/b/api/bills", json=bill_body(app, items=[
        {"product_id": rava, "qty": 60, "unit_price": 50, "is_loose": False},
        {"product_id": rava, "qty": 5, "unit_price": 50, "is_loose": True},
    ]))
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        b = db.session.get(Bill, r.get_json()["id"])
        bag, loose = sorted(b.items, key=lambda i: i.qty, reverse=True)
        assert (bag.qty, bag.gst_rate, bag.line_total) == (Decimal("60.000"), Decimal("0.00"), Decimal("3000.00"))
        assert loose.product_name.endswith("(Loose)") and loose.gst_rate == Decimal("5.00")
        assert b.gst_amount == Decimal("12.50")            # 5% of 250 only
        assert b.grand_total == Decimal("3262.50")
        assert Product.query.filter_by(sku="RAVA").first().stock_qty == Decimal("435.000")


def test_two_lines_together_cannot_exceed_stock(phone, app):
    rava = pid(app, "RAVA")
    r = phone.post("/b/api/bills", json=bill_body(app, items=[
        {"product_id": rava, "qty": 300, "unit_price": 50}, {"product_id": rava, "qty": 250, "unit_price": 50, "is_loose": True},
    ]))
    assert r.status_code == 400 and "Insufficient stock" in r.get_json()["error"]
    with app.app_context():
        assert Product.query.filter_by(sku="RAVA").first().stock_qty == Decimal("500.000")  # nothing was deducted
