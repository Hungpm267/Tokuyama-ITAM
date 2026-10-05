from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    user_name = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)
    table_name = Column(String(50), nullable=False, index=True)
    record_id = Column(Integer, nullable=False)
    action = Column(String(20), nullable=False)  # 'create', 'update', 'delete', 'restore'
    changes_json = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AuditLog #{self.id} {self.action} on {self.table_name}:{self.record_id}>"
