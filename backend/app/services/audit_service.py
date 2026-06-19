"""Small helper to write an audit_logs row from anywhere in the API layer."""
from sqlalchemy.orm import Session
from app.models.audit import AuditLog


def log_action(db: Session, user_id: str | None, action: str, resource_type: str = None,
               resource_id: str = None, details: dict = None, ip_address: str = None):
    entry = AuditLog(
        user_id=user_id, action=action, resource_type=resource_type,
        resource_id=resource_id, details=details or {}, ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    return entry
