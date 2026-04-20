"""GIS models — ServiceLine, OutageArea, Zone, Pole.

Part of spec 014-gis-postgis (MVP). All geometries EPSG:4326.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from geoalchemy2 import Geometry

from app.db.base import Base


class ServiceLine(Base):
    __tablename__ = "service_lines"

    id = Column(Integer, primary_key=True, index=True)
    meter_serial = Column(String(50), nullable=True, index=True)
    transformer_id = Column(Integer, ForeignKey("transformers.id"), nullable=True)
    length_m = Column(Float, nullable=True)
    cable_type = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    geom = Column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=True)


class OutageArea(Base):
    __tablename__ = "outage_areas"

    id = Column(Integer, primary_key=True, index=True)
    network_event_id = Column(Integer, nullable=True)
    affected_customers = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    etr = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    polygon_geom = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    zone_type = Column(String(50), nullable=True)
    created_by = Column(String(100), nullable=True)
    rules = Column(JSONB, nullable=True)
    orphan = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    geom = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)


class Pole(Base):
    __tablename__ = "poles"

    id = Column(Integer, primary_key=True, index=True)
    feeder_id = Column(Integer, ForeignKey("feeders.id"), nullable=True)
    material = Column(String(50), nullable=True)
    height_m = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
