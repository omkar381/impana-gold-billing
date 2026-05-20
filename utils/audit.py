"""
utils/audit.py — Audit log helper for Impana Gold.

Writes immutable records to the audit_log table for every admin mutation.
Usage:
    from utils.audit import log_action
    log_action(
        actor_id=current_user.id,
        action="UPDATE",
        entity="product",
        entity_id=product.id,
        old_val={"price": 50.0},
        new_val={"price": 55.0},
        ip_address=request.remote_addr,
    )
"""

from datetime import datetime
from typing import Optional, Any


def log_action(
    actor_id: int,
    action: str,
    entity: str,
    entity_id: Optional[int] = None,
    old_val: Optional[Any] = None,
    new_val: Optional[Any] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Insert a record into audit_log.

    Args:
        actor_id:   ID of the admin_users row performing the action.
        action:     One of: CREATE, UPDATE, DELETE, CANCEL, LOGIN, LOGOUT.
        entity:     Table/model name: product, bill, customer, staff, settings.
        entity_id:  Primary key of the affected row (nullable for LOGIN).
        old_val:    Dict of old field values (for UPDATE/DELETE).
        new_val:    Dict of new field values (for CREATE/UPDATE).
        ip_address: Requester's IP from request.remote_addr.
    """
    # Deferred import to avoid circular dependencies
    from extensions import db
    from models import AuditLog

    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        old_value=old_val,
        new_value=new_val,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
    )
    try:
        db.session.add(entry)
        db.session.flush()  # Write without committing (caller controls transaction)
    except Exception as exc:
        # Audit failures should never crash the main operation
        db.session.rollback()
        import logging
        logging.getLogger(__name__).error("Audit log write failed: %s", exc)
