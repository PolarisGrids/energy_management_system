from sqlalchemy import Column, Integer, Float, Date, Index
from app.db.base import Base


class EnergyDailySummary(Base):
    __tablename__ = "energy_daily_summary"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True)
    total_import_kwh = Column(Float, default=0.0)
    total_export_kwh = Column(Float, default=0.0)
    net_kwh = Column(Float, default=0.0)
    peak_demand_kw = Column(Float, default=0.0)
    avg_power_factor = Column(Float, default=0.95)
    residential_import_kwh = Column(Float, default=0.0)
    commercial_import_kwh = Column(Float, default=0.0)
    prepaid_import_kwh = Column(Float, default=0.0)

    __table_args__ = (
        Index("idx_energy_daily_date", "date"),
    )
