from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class SoftDeleteMixin:
    """Provides the 8 standard fields for auditing and soft delete."""
    created_at = Column(DateTime, default=utc_now, nullable=False)
    created_by_id = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    updated_by_id = Column(Integer, nullable=True)
    is_deleted = Column(Boolean, default=False, index=True, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by_id = Column(Integer, nullable=True)
    delete_reason = Column(String(255), nullable=True)

    def soft_delete(self, user_id=None, reason=None):
        self.is_deleted = True
        self.deleted_at = utc_now()
        self.deleted_by_id = user_id
        self.delete_reason = reason

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by_id = None
        self.delete_reason = None
