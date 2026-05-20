"""
models.py — All SQLAlchemy ORM models for Impana Gold Billing System.

Tables:
  1. AdminUser        — Staff and superadmin accounts
  2. BusinessSettings — Key-value store for shop config
  3. Category         — Product categories
  4. Product          — Catalogue with GST/HSN details
  5. Customer         — Customer registry
  6. Bill             — Invoice header
  7. BillItem         — Invoice line items (with price snapshots)
  8. DailySummary     — Pre-aggregated daily totals
  9. AuditLog         — Immutable action log

All monetary columns use NUMERIC (not FLOAT) to prevent rounding errors.
updated_at is maintained via a PostgreSQL trigger (see schema.sql).
"""

from datetime import datetime
from extensions import db


# ---------------------------------------------------------------------------
# 1. AdminUser
# ---------------------------------------------------------------------------

class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.String(20),
        db.CheckConstraint("role IN ('superadmin','staff')"),
        default="staff",
        nullable=False,
    )
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login = db.Column(db.DateTime(timezone=True))
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime(timezone=True))  # brute-force lockout
    created_at = db.Column(
        db.DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Flask-Login interface
    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f"<AdminUser {self.username} ({self.role})>"


# ---------------------------------------------------------------------------
# 2. BusinessSettings
# ---------------------------------------------------------------------------

class BusinessSettings(db.Model):
    __tablename__ = "business_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    updated_by = db.Column(db.Integer, db.ForeignKey("admin_users.id"))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self):
        return f"<BusinessSettings {self.key}={self.value!r}>"


# ---------------------------------------------------------------------------
# 3. Category
# ---------------------------------------------------------------------------

class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(
        db.DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    products = db.relationship("Product", backref="category", lazy="dynamic")

    def __repr__(self):
        return f"<Category {self.name}>"


# ---------------------------------------------------------------------------
# 4. Product
# ---------------------------------------------------------------------------

class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    price_per_unit = db.Column(db.Numeric(10, 2), nullable=False)
    unit = db.Column(db.String(20), nullable=False)          # kg, g, pcs, litre
    weight_grams = db.Column(db.Integer)                     # e.g. 500, 1000
    hsn_code = db.Column(db.String(20))
    gst_rate = db.Column(db.Numeric(4, 2), default=0)        # 0/5/12/18/28
    barcode = db.Column(db.String(100), index=True)
    image_path = db.Column(db.String(255))
    stock_qty = db.Column(db.Numeric(12, 3), default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    deleted_at = db.Column(db.DateTime(timezone=True))       # soft delete
    created_at = db.Column(
        db.DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self):
        return f"<Product {self.sku}: {self.name}>"


# ---------------------------------------------------------------------------
# 5. Customer
# ---------------------------------------------------------------------------

class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), unique=True, index=True)
    address = db.Column(db.Text)
    gstin = db.Column(db.String(20))
    state = db.Column(db.String(100))
    state_code = db.Column(db.String(5))
    loyalty_points = db.Column(db.Integer, default=0)
    deleted_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    bills = db.relationship("Bill", backref="customer", lazy="dynamic")

    def __repr__(self):
        return f"<Customer {self.name} ({self.phone})>"


# ---------------------------------------------------------------------------
# 6. Bill
# ---------------------------------------------------------------------------

class Bill(db.Model):
    __tablename__ = "bills"

    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    customer_id = db.Column(
        db.Integer, db.ForeignKey("customers.id"), nullable=True
    )  # NULL = walk-in
    operator_id = db.Column(
        db.Integer, db.ForeignKey("admin_users.id"), nullable=False
    )
    bill_date = db.Column(
        db.DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True
    )
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(12, 2), default=0)
    discount_type = db.Column(
        db.String(10),
        db.CheckConstraint("discount_type IN ('flat','percent')"),
        default="flat",
    )
    taxable_amount = db.Column(db.Numeric(12, 2), nullable=False)
    gst_amount = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), nullable=False)
    payment_mode = db.Column(
        db.String(10),
        db.CheckConstraint("payment_mode IN ('cash','upi','card','credit')"),
        nullable=False,
    )
    amount_paid = db.Column(db.Numeric(12, 2), default=0)
    change_returned = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)
    status = db.Column(
        db.String(15),
        db.CheckConstraint("status IN ('draft','confirmed','cancelled')"),
        default="confirmed",
    )
    cancelled_at = db.Column(db.DateTime(timezone=True))
    cancel_reason = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    items = db.relationship(
        "BillItem", backref="bill", lazy="joined", cascade="all, delete-orphan"
    )
    operator = db.relationship("AdminUser", foreign_keys=[operator_id])

    def __repr__(self):
        return f"<Bill {self.bill_number} ₹{self.grand_total}>"


# ---------------------------------------------------------------------------
# 7. BillItem  (line-item snapshot — critical for historical integrity)
# ---------------------------------------------------------------------------

class BillItem(db.Model):
    __tablename__ = "bill_items"

    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(
        db.Integer, db.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    # --- SNAPSHOTS (captured at billing time; never change after save) ---
    product_name = db.Column(db.String(200), nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    qty = db.Column(db.Numeric(10, 3), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    gst_rate = db.Column(db.Numeric(4, 2), default=0)
    hsn_code = db.Column(db.String(20))
    line_total = db.Column(db.Numeric(12, 2), nullable=False)

    product = db.relationship("Product")

    def __repr__(self):
        return f"<BillItem {self.product_name} x{self.qty}>"


# ---------------------------------------------------------------------------
# 8. DailySummary
# ---------------------------------------------------------------------------

class DailySummary(db.Model):
    __tablename__ = "daily_summary"

    id = db.Column(db.Integer, primary_key=True)
    summary_date = db.Column(db.Date, unique=True, nullable=False)
    total_bills = db.Column(db.Integer, default=0)
    total_revenue = db.Column(db.Numeric(12, 2), default=0)
    total_gst = db.Column(db.Numeric(12, 2), default=0)
    total_discount = db.Column(db.Numeric(12, 2), default=0)
    cash_total = db.Column(db.Numeric(12, 2), default=0)
    upi_total = db.Column(db.Numeric(12, 2), default=0)
    card_total = db.Column(db.Numeric(12, 2), default=0)
    computed_at = db.Column(
        db.DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    def __repr__(self):
        return f"<DailySummary {self.summary_date} ₹{self.total_revenue}>"


# ---------------------------------------------------------------------------
# 9. AuditLog
# ---------------------------------------------------------------------------

class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"))
    action = db.Column(db.String(50), nullable=False)   # CREATE, UPDATE, DELETE, etc.
    entity = db.Column(db.String(50), nullable=False)   # product, bill, customer, etc.
    entity_id = db.Column(db.Integer)
    old_value = db.Column(db.JSON)
    new_value = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(
        db.DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    actor = db.relationship("AdminUser")

    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity}#{self.entity_id}>"


# ---------------------------------------------------------------------------
# 10. InventoryTransaction
# ---------------------------------------------------------------------------

class InventoryTransaction(db.Model):
    __tablename__ = "inventory_transactions"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=False)
    change_qty = db.Column(db.Numeric(12, 3), nullable=False)
    before_qty = db.Column(db.Numeric(12, 3), nullable=False)
    after_qty = db.Column(db.Numeric(12, 3), nullable=False)
    reason = db.Column(db.String(30), nullable=False)  # sale, restock, adjust, cancel
    reference_type = db.Column(db.String(30))
    reference_id = db.Column(db.Integer)
    note = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    product = db.relationship("Product")
    actor = db.relationship("AdminUser")

    def __repr__(self):
        return f"<InventoryTransaction {self.product_id} {self.change_qty}>"
