"""dcu_health_cache — spec 018 W2.T6.

One row per DCU, upserted by the `hesv2.network.health` consumer. Reads enforce
a 5-minute TTL (`last_reported_at >= now() - interval '5 minutes'`) — rows
older than that are treated as stale / offline.
"""
from sqlalchemy import Column, DateTime, Integer, Numeric, String
from sqlalchemy.sql import func

from app.db.base import Base


class DCUHealthCache(Base):
    __tablename__ = "dcu_health_cache"

    dcu_id = Column(String(100), primary_key=True)
    status = Column(String(20), nullable=False)
    rssi_dbm = Column(Numeric(6, 2), nullable=True)
    success_rate_pct = Column(Numeric(5, 2), nullable=True)
    retry_count_last_hour = Column(Integer, nullable=True)
    meters_connected = Column(Integer, nullable=True)
    last_reported_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
