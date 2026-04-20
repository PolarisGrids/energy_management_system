from sqlalchemy import Column, Integer, String, DateTime, JSON, Index
from app.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    user_name = Column(String(100), nullable=False)
    user_role = Column(String(50), nullable=False)
    event_type = Column(String(50), nullable=False)
    action = Column(String(200), nullable=False)
    resource = Column(String(200), nullable=True)
    ip_address = Column(String(50), nullable=True)
    result = Column(String(50), nullable=False, default="Success")
    details = Column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_audit_ts", "timestamp"),
        Index("idx_audit_type", "event_type"),
        Index("idx_audit_user", "user_name"),
    )
