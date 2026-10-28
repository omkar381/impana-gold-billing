"""officer app: login fields, order requests

Revision ID: b8d2e5f6a1c3
Revises: a7c1d9e4b2f0
Create Date: 2026-10-29 10:00:00.000000

Idempotent: the app applies the same upgrade at startup (utils/schema.py).
"""
from alembic import op
import sqlalchemy as sa


revision = 'b8d2e5f6a1c3'
down_revision = 'a7c1d9e4b2f0'
branch_labels = None
depends_on = None


def _add_missing(table, columns):
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    with op.batch_alter_table(table, schema=None) as batch_op:
        for column in columns:
            if column.name not in existing:
                batch_op.add_column(column)


def upgrade():
    _add_missing('bills', [sa.Column('marketing_officer_id', sa.Integer(), nullable=True)])
    _add_missing('marketing_officers', [
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('photo_path', sa.String(length=255), nullable=True),
        sa.Column('photo_data', sa.LargeBinary(), nullable=True),
        sa.Column('monthly_target', sa.Numeric(12, 2), nullable=True),
        sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    ])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if 'order_requests' not in tables:
        op.create_table(
            'order_requests',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('request_number', sa.String(length=30), nullable=False),
            sa.Column('officer_id', sa.Integer(), nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=True),
            sa.Column('new_customer_name', sa.String(length=200), nullable=True),
            sa.Column('new_customer_phone', sa.String(length=20), nullable=True),
            sa.Column('new_customer_address', sa.Text(), nullable=True),
            sa.Column('new_customer_gstin', sa.String(length=20), nullable=True),
            sa.Column('payment_mode', sa.String(length=10), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('estimated_total', sa.Numeric(12, 2), nullable=True),
            sa.Column('status', sa.String(length=12), nullable=False),
            sa.Column('decision_reason', sa.Text(), nullable=True),
            sa.Column('decided_by', sa.Integer(), nullable=True),
            sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('bill_id', sa.Integer(), nullable=True),
            sa.Column('seen_by_officer', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['officer_id'], ['marketing_officers.id']),
            sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
            sa.ForeignKeyConstraint(['decided_by'], ['admin_users.id']),
            sa.ForeignKeyConstraint(['bill_id'], ['bills.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_order_requests_request_number', 'order_requests', ['request_number'], unique=True)
        op.create_index('ix_order_requests_officer_id', 'order_requests', ['officer_id'])
        op.create_index('ix_order_requests_status', 'order_requests', ['status'])
        op.create_index('ix_order_requests_created_at', 'order_requests', ['created_at'])

    if 'order_request_items' not in tables:
        op.create_table(
            'order_request_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('product_name', sa.String(length=200), nullable=False),
            sa.Column('unit', sa.String(length=10), nullable=False),
            sa.Column('qty', sa.Numeric(12, 3), nullable=False),
            sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
            sa.Column('line_total', sa.Numeric(12, 2), nullable=False),
            sa.ForeignKeyConstraint(['order_id'], ['order_requests.id']),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_order_request_items_order_id', 'order_request_items', ['order_id'])


def downgrade():
    op.drop_table('order_request_items')
    op.drop_table('order_requests')
    with op.batch_alter_table('marketing_officers', schema=None) as batch_op:
        for name in ('last_login', 'locked_until', 'failed_login_count', 'monthly_target', 'photo_data', 'photo_path', 'password_hash'):
            batch_op.drop_column(name)
    with op.batch_alter_table('bills', schema=None) as batch_op:
        batch_op.drop_column('marketing_officer_id')
