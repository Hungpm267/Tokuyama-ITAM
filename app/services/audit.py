import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.audit import AuditLog

def log_audit(db: Session, table_name: str, record_id: int, action: str, user_id: int = None, user_name: str = None, changes: dict = None):
    """Immutable audit logging."""
    try:
        changes_str = json.dumps(changes, default=str) if changes else None
        log_entry = AuditLog(
            user_id=user_id,
            user_name=user_name,
            timestamp=datetime.utcnow(),
            table_name=table_name,
            record_id=record_id,
            action=action,
            changes_json=changes_str
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        # Non-blocking for primary transaction
        print(f"Audit log error: {e}")
