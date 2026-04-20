from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Index
from app.db.base import Base


class HESDCU(Base):
    __tablename__ = "hes_dcus"

    id = Column(String(50), primary_key=True)
    location = Column(String(200), nullable=False)
    total_meters = Column(Integer, default=0)
    online_meters = Column(Integer, default=0)
    last_comm = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="online")
    firmware_version = Column(String(50), nullable=True)
    comm_tech = Column(String(50), default="GPRS")


class HESCommandLog(Base):
    __tablename__ = "hes_command_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    meter_serial = Column(String(50), nullable=False)
    command_type = Column(String(100), nullable=False)
    status = Column(String(20), default="ok")
    operator = Column(String(100), nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_hescmd_ts", "timestamp"),
    )


class HESFOTAJob(Base):
    __tablename__ = "hes_fota_jobs"

    id = Column(String(50), primary_key=True)
    target_description = Column(String(200), nullable=False)
    total_meters = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    status = Column(String(20), default="scheduled")
    firmware_from = Column(String(50), nullable=True)
    firmware_to = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
