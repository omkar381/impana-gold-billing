"""
utils/schema.py — Idempotent schema upgrade for the Marketing Officer feature.

Production runs `gunicorn app:app` and migrations are not applied
automatically, so deploying code that reads new columns before someone runs
`flask db upgrade` would break bill saving. This runs once at startup and only
adds what is missing (new table, two bill columns, the default officer), so it
is safe to run repeatedly and alongside the Alembic migration.
"""

import logging

from sqlalchemy import inspect, text

log = logging.getLogger(__name__)

DEFAULT_OFFICER_NAME = "Siddalingayya Hiremath"
DEFAULT_OFFICER_PHONE = "+91 87470 04801"

_COLUMNS = {
    "bills": {
        "marketing_officer_name": "VARCHAR(120)",
        "marketing_officer_phone": "VARCHAR(30)",
        "marketing_officer_id": "INTEGER",
    },
    "marketing_officers": {
        "password_hash": "VARCHAR(255)",
        "photo_path": "VARCHAR(255)",
        "photo_data": "BLOB",  # becomes BYTEA on PostgreSQL (see _ddl)
        "monthly_target": "NUMERIC(12, 2) DEFAULT 0",
        "failed_login_count": "INTEGER DEFAULT 0 NOT NULL",
        "locked_until": "TIMESTAMP WITH TIME ZONE",
        "last_login": "TIMESTAMP WITH TIME ZONE",
    },
}


def ensure_marketing_officer_schema(db) -> None:
    from models import MarketingOfficer

    try:
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        if "bills" not in tables:
            return  # brand-new database: create_all / migrations will handle it

        if "marketing_officers" not in tables:
            MarketingOfficer.__table__.create(db.engine, checkfirst=True)
            inspector = inspect(db.engine)

        for table, columns in _COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    if ddl == "BLOB" and db.engine.dialect.name == "postgresql":
                        ddl = "BYTEA"
                    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        db.session.commit()

        # Officer order requests (new tables only; never touches existing ones)
        db.create_all()

        if MarketingOfficer.query.count() == 0:
            db.session.add(
                MarketingOfficer(
                    name=DEFAULT_OFFICER_NAME,
                    phone=DEFAULT_OFFICER_PHONE,
                    is_default=True,
                )
            )
            db.session.commit()
    except Exception:  # never stop the app from booting
        db.session.rollback()
        log.exception("Marketing officer schema check failed")
