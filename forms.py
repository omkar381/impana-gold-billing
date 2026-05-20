"""
forms.py — All WTForms form classes for Impana Gold Billing System.
Every form has CSRF protection via Flask-WTF (inherits FlaskForm).
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, SelectField, TextAreaField,
    DecimalField, IntegerField, BooleanField, HiddenField,
    RadioField,
)
from wtforms.validators import (
    DataRequired, Length, Optional, NumberRange,
    ValidationError, Email,
)


# ── Authentication ─────────────────────────────────────────────────────────

class LoginForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=50)],
        render_kw={"autofocus": True, "autocomplete": "username"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=6, max=128)],
        render_kw={"autocomplete": "current-password"},
    )


# ── Products ───────────────────────────────────────────────────────────────

class ProductForm(FlaskForm):
    name = StringField("Product Name", validators=[DataRequired(), Length(max=200)])
    sku = StringField("SKU", validators=[DataRequired(), Length(max=50)])
    category_id = SelectField("Category", coerce=int, validators=[Optional()])
    price_per_unit = DecimalField(
        "Price per Unit (₹)",
        places=2,
        validators=[DataRequired(), NumberRange(min=0.01)],
    )
    unit = SelectField(
        "Unit",
        choices=[("kg", "kg"), ("g", "g"), ("pcs", "pcs"), ("litre", "litre")],
        validators=[DataRequired()],
    )
    weight_grams = IntegerField(
        "Weight (grams)", validators=[Optional(), NumberRange(min=0)]
    )
    hsn_code = StringField("HSN Code", validators=[Optional(), Length(max=20)])
    gst_rate = SelectField(
        "GST Rate (%)",
        choices=[
            ("0", "0%"), ("5", "5%"), ("12", "12%"), ("18", "18%"), ("28", "28%")
        ],
        default="0",
    )
    barcode = StringField("Barcode", validators=[Optional(), Length(max=100)])
    initial_stock = DecimalField(
        "Initial Stock",
        places=3,
        validators=[Optional(), NumberRange(min=0)],
    )
    image = FileField(
        "Product Image",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only (jpg/png/webp)"),
        ],
    )
    is_active = BooleanField("Active", default=True)


# ── Customers ──────────────────────────────────────────────────────────────

class CustomerForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=200)])
    phone = StringField("Phone", validators=[Optional(), Length(max=20)])
    address = TextAreaField("Address", validators=[Optional(), Length(max=500)])
    gstin = StringField("GSTIN", validators=[Optional(), Length(max=20)])
    state = StringField("State", validators=[Optional(), Length(max=100)])
    state_code = StringField("State Code", validators=[Optional(), Length(max=5)])


# ── Bill Cancel ────────────────────────────────────────────────────────────

class BillCancelForm(FlaskForm):
    cancel_reason = TextAreaField(
        "Reason for Cancellation",
        validators=[DataRequired(), Length(min=5, max=500)],
    )


# ── Business Settings ──────────────────────────────────────────────────────

class BusinessSettingsForm(FlaskForm):
    # — Business Info —
    shop_name = StringField("Shop Name", validators=[DataRequired(), Length(max=200)])
    tagline = StringField("Tagline / Description", validators=[Optional(), Length(max=300)])
    address_line1 = StringField("Address Line 1", validators=[Optional(), Length(max=200)])
    address_line2 = StringField("Address Line 2", validators=[Optional(), Length(max=200)])
    city = StringField("City", validators=[Optional(), Length(max=100)])
    state = StringField("State", validators=[Optional(), Length(max=100)])
    state_code = StringField("State Code", validators=[Optional(), Length(max=5)])
    pincode = StringField("Pincode", validators=[Optional(), Length(max=10)])
    phone = StringField("Phone", validators=[Optional(), Length(max=20)])
    phone2 = StringField("Phone 2 (Alternate)", validators=[Optional(), Length(max=20)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=200)])
    website = StringField("Website", validators=[Optional(), Length(max=200)])

    # — Tax & Compliance —
    gstin = StringField("GSTIN", validators=[Optional(), Length(max=20)])
    fssai = StringField("FSSAI License No.", validators=[Optional(), Length(max=50)])
    iso_certification = StringField("ISO Certification No.", validators=[Optional(), Length(max=100)])
    gst_enabled = BooleanField("Enable GST on Bills", default=True)

    # — Bank Details (Optional) —
    bank_name = StringField("Bank Name", validators=[Optional(), Length(max=100)])
    bank_branch = StringField("Branch", validators=[Optional(), Length(max=100)])
    bank_account = StringField("Account Number", validators=[Optional(), Length(max=30)])
    bank_ifsc = StringField("IFSC Code", validators=[Optional(), Length(max=15)])
    upi_id = StringField("UPI ID", validators=[Optional(), Length(max=100)])

    # — Invoice Config —
    bill_prefix = StringField(
        "Bill Prefix",
        validators=[DataRequired(), Length(min=1, max=10)],
        default="IG",
    )
    bill_counter_reset = SelectField(
        "Bill Counter Reset",
        choices=[("never", "Never"), ("daily", "Daily"), ("monthly", "Monthly"), ("yearly", "Yearly (FY)")],
        default="daily",
    )
    terms_conditions = TextAreaField(
        "Terms & Conditions",
        validators=[Optional(), Length(max=2000)],
    )
    declaration = TextAreaField(
        "Declaration",
        validators=[Optional(), Length(max=500)],
    )
    signature_name = StringField(
        "Authorized Signatory Name",
        validators=[Optional(), Length(max=200)],
    )

    # — Branding & Certification Logos —
    logo = FileField(
        "Brand Logo",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only (jpg/png/webp)"),
        ],
    )
    fssai_logo = FileField(
        "FSSAI Certificate Logo",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only"),
        ],
    )
    iso_logo = FileField(
        "ISO Certificate Logo",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only"),
        ],
    )
    other_cert_logo = FileField(
        "Other Certification Logo",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only"),
        ],
    )


# ── Staff ──────────────────────────────────────────────────────────────────

class StaffAddForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=3, max=50)]
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    role = SelectField(
        "Role",
        choices=[("staff", "Staff")],  # UI cannot create superadmin
        default="staff",
    )


class StaffPasswordResetForm(FlaskForm):
    new_password = PasswordField(
        "New Password", validators=[DataRequired(), Length(min=8, max=128)]
    )


# ── Warehouse Stock ───────────────────────────────────────────────────────

class StockAdjustForm(FlaskForm):
    qty = DecimalField(
        "Quantity",
        places=3,
        validators=[DataRequired(), NumberRange(min=0.001)],
    )
    action = SelectField(
        "Action",
        choices=[("restock", "Restock"), ("deduct", "Deduct")],
        default="restock",
    )
    note = StringField(
        "Note",
        validators=[DataRequired(), Length(min=3, max=200)],
    )
