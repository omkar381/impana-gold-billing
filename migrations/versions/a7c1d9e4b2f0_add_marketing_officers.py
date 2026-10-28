"""add marketing officers

Revision ID: a7c1d9e4b2f0
Revises: 9add147b16f3
Create Date: 2026-10-28 19:30:00.000000

Idempotent: the app also applies this at startup (utils/schema.py), so every
step checks whether it is already done.
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7c1d9e4b2f0'
down_revision = '9add147b16f3'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())

    if 'marketing_officers' not in inspector.get_table_names():
        op.create_table(
            'marketing_officers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=120), nullable=False),
            sa.Column('phone', sa.String(length=30), nullable=True),
            sa.Column('is_default', sa.Boolean(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )

    existing = {c['name'] for c in inspector.get_columns('bills')}
    with op.batch_alter_table('bills', schema=None) as batch_op:
        if 'marketing_officer_name' not in existing:
            batch_op.add_column(sa.Column('marketing_officer_name', sa.String(length=120), nullable=True))
        if 'marketing_officer_phone' not in existing:
            batch_op.add_column(sa.Column('marketing_officer_phone', sa.String(length=30), nullable=True))


def downgrade():
    with op.batch_alter_table('bills', schema=None) as batch_op:
        batch_op.drop_column('marketing_officer_phone')
        batch_op.drop_column('marketing_officer_name')
    op.drop_table('marketing_officers')
