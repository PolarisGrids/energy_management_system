from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class MeterType(str, enum.Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    PREPAID = "prepaid"


class MeterStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    TAMPER = "tamper"
    DISCONNECTED = "disconnected"


class RelayState(str, enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class Feeder(Base):
    __tablename__ = "feeders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    substation = Column(String(100), nullable=False)
    voltage_kv = Column(Float, default=11.0)
    capacity_kva = Column(Float, nullable=False)
    current_load_kw = Column(Float, default=0.0)
    geojson = Column(JSON, nullable=True)
    transformers = relationship("Transformer", back_populates="feeder")


class Transformer(Base):
    __tablename__ = "transformers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    feeder_id = Column(Integer, ForeignKey("feeders.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    capacity_kva = Column(Float, nullable=False)
    current_load_kw = Column(Float, default=0.0)
    loading_percent = Column(Float, default=0.0)
    voltage_pu = Column(Float, default=1.0)
    phase = Column(String(10), default="3ph")
    feeder = relationship("Feeder", back_populates="transformers")
    meters = relationship("Meter", back_populates="transformer")
    sensors = relationship("TransformerSensor", back_populates="transformer")


class Meter(Base):
    __tablename__ = "meters"

    id = Column(Integer, primary_key=True, index=True)
    serial = Column(String(50), unique=True, nullable=False, index=True)
    transformer_id = Column(Integer, ForeignKey("transformers.id"), nullable=False)
    meter_type = Column(Enum(MeterType), default=MeterType.RESIDENTIAL)
    status = Column(Enum(MeterStatus), default=MeterStatus.ONLINE)
    relay_state = Column(Enum(RelayState), default=RelayState.CONNECTED)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(String(255), nullable=True)
    customer_name = Column(String(255), nullable=True)
    account_number = Column(String(50), nullable=True)
    tariff_class = Column(String(50), default="Residential")
    prepaid_balance = Column(Float, nullable=True)
    firmware_version = Column(String(20), default="v2.1.4")
    comm_tech = Column(String(20), default="PLC")
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    installed_at = Column(DateTime(timezone=True), server_default=func.now())
    # Spec 018 W2.T4 — populated by the `hesv2.command.status` consumer on
    # CONFIRMED; lets the meter page render the most recent command id without
    # joining into `command_log`.
    last_command_id = Column(String(64), nullable=True, index=True)
    transformer = relationship("Transformer", back_populates="meters")
