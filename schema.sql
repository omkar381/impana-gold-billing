-- Impana Gold Billing System - PostgreSQL schema
-- This schema matches the SQLAlchemy models in models.py.

CREATE TABLE IF NOT EXISTS admin_users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(50) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'staff',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  last_login TIMESTAMPTZ,
  failed_login_count INTEGER NOT NULL DEFAULT 0,
  locked_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_admin_role CHECK (role IN ('superadmin','staff'))
);

CREATE TABLE IF NOT EXISTS business_settings (
  id SERIAL PRIMARY KEY,
  key VARCHAR(100) UNIQUE NOT NULL,
  value TEXT,
  updated_by INTEGER REFERENCES admin_users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categories (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  sort_order INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  sku VARCHAR(50) UNIQUE NOT NULL,
  category_id INTEGER REFERENCES categories(id),
  price_per_unit NUMERIC(10,2) NOT NULL,
  unit VARCHAR(20) NOT NULL,
  weight_grams INTEGER,
  hsn_code VARCHAR(20),
  gst_rate NUMERIC(4,2) DEFAULT 0,
  barcode VARCHAR(100),
  image_path VARCHAR(255),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stock_qty NUMERIC(12,3) DEFAULT 0,
);

CREATE TABLE IF NOT EXISTS customers (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  phone VARCHAR(20) UNIQUE,
  address TEXT,
  gstin VARCHAR(20),
  loyalty_points INTEGER DEFAULT 0,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bills (
  id SERIAL PRIMARY KEY,
  bill_number VARCHAR(30) UNIQUE NOT NULL,
  customer_id INTEGER REFERENCES customers(id),
  operator_id INTEGER NOT NULL REFERENCES admin_users(id),
  bill_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  subtotal NUMERIC(12,2) NOT NULL,
  discount_amount NUMERIC(12,2) DEFAULT 0,
  discount_type VARCHAR(10) DEFAULT 'flat',
  taxable_amount NUMERIC(12,2) NOT NULL,
  gst_amount NUMERIC(12,2) DEFAULT 0,
  grand_total NUMERIC(12,2) NOT NULL,
  payment_mode VARCHAR(10) NOT NULL,
  amount_paid NUMERIC(12,2) DEFAULT 0,
  change_returned NUMERIC(12,2) DEFAULT 0,
  notes TEXT,
  status VARCHAR(15) DEFAULT 'confirmed',
  cancelled_at TIMESTAMPTZ,
  cancel_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_discount_type CHECK (discount_type IN ('flat','percent')),
  CONSTRAINT chk_payment_mode CHECK (payment_mode IN ('cash','upi','card','credit')),
  CONSTRAINT chk_bill_status CHECK (status IN ('draft','confirmed','cancelled'))
);

CREATE TABLE IF NOT EXISTS bill_items (
  id SERIAL PRIMARY KEY,
  bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(id),
  product_name VARCHAR(200) NOT NULL,
  unit_price NUMERIC(10,2) NOT NULL,
  qty NUMERIC(10,3) NOT NULL,
  unit VARCHAR(20) NOT NULL,
  gst_rate NUMERIC(4,2) DEFAULT 0,
  hsn_code VARCHAR(20),
  line_total NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_summary (
  id SERIAL PRIMARY KEY,
  summary_date DATE UNIQUE NOT NULL,
  total_bills INTEGER DEFAULT 0,
  total_revenue NUMERIC(12,2) DEFAULT 0,
  total_gst NUMERIC(12,2) DEFAULT 0,
  total_discount NUMERIC(12,2) DEFAULT 0,
  cash_total NUMERIC(12,2) DEFAULT 0,
  upi_total NUMERIC(12,2) DEFAULT 0,
  card_total NUMERIC(12,2) DEFAULT 0,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
  id SERIAL PRIMARY KEY,
  actor_id INTEGER REFERENCES admin_users(id),
  action VARCHAR(50) NOT NULL,
  entity VARCHAR(50) NOT NULL,
  entity_id INTEGER,
  old_value JSONB,
  new_value JSONB,
  ip_address VARCHAR(45),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inventory_transactions (
  id SERIAL PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  actor_id INTEGER NOT NULL REFERENCES admin_users(id),
  change_qty NUMERIC(12,3) NOT NULL,
  before_qty NUMERIC(12,3) NOT NULL,
  after_qty NUMERIC(12,3) NOT NULL,
  reason VARCHAR(30) NOT NULL,
  reference_type VARCHAR(30),
  reference_id INTEGER,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_products_name ON products (name);
CREATE INDEX IF NOT EXISTS idx_products_barcode ON products (barcode);
CREATE INDEX IF NOT EXISTS idx_products_sku ON products (sku);
CREATE INDEX IF NOT EXISTS idx_bills_number ON bills (bill_number);
CREATE INDEX IF NOT EXISTS idx_bills_date ON bills (bill_date);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (phone);

-- Updated-at trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_admin_users_updated
BEFORE UPDATE ON admin_users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_business_settings_updated
BEFORE UPDATE ON business_settings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_products_updated
BEFORE UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_customers_updated
BEFORE UPDATE ON customers
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_bills_updated
BEFORE UPDATE ON bills
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
