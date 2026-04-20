from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class DERType(str, enum.Enum):
    PV = "pv"
    BESS = "bess"
    EV_CHARGER = "ev_charger"
    MICROGRID = "microgrid"
    WIND = "wind"


class DERStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    CURTAILED = "curtailed"
    CHARGING = "charging"
    DISCHARGING = "discharging"
    IDLE = "idle"


class DERAsset(Base):
    __tablename__ = "der_assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    asset_type = Column(Enum(DERType), nullable=False)
    status = Column(Enum(DERStatus), default=DERStatus.ONLINE)
    transformer_id = Column(Integer, ForeignKey("transformers.id"), nullable=True)
    meter_serial = Column(String(50), nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # Capacity
    rated_capacity_kw = Column(Float, nullable=False)
    current_output_kw = Column(Float, default=0.0)

    # PV specific
    panel_area_m2 = Column(Float, nullable=True)
    inverter_efficiency = Column(Float, nullable=True)
    generation_today_kwh = Column(Float, default=0.0)
    generation_achievement_rate = Column(Float, default=0.0)

    # BESS specific
    capacity_kwh = Column(Float, nullable=True)
    state_of_charge = Column(Float, nullable=True)  # 0-100%
    charge_cycles = Column(Integer, default=0)
    revenue_today = Column(Float, default=0.0)

    # EV Charger specific
    num_ports = Column(Integer, nullable=True)
    active_sessions = Column(Integer, default=0)
    energy_dispensed_today_kwh = Column(Float, default=0.0)
    fee_collected_today = Column(Float, default=0.0)

    # Microgrid specific
    islanded = Column(Boolean, default=False)
    reverse_power_flow = Column(Boolean, default=False)

    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    metadata_ = Column("metadata", JSON, nullable=True)
