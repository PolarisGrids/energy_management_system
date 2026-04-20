"""Sensor API endpoints — REQ-25 Transformer Sensor Assets.

Spec 018 W2B.T11 — `/{sensor_id}/history` no longer synthesises values with
`random.uniform`. It reads from `transformer_sensor_reading` (populated by the
W2A Kafka consumer). When the table is empty and SSOT_MODE != strict we return
an empty history with a `banner` field so the UI can render a "waiting for
Kafka stream" notice. In strict mode, an empty table returns 503.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.config import SSOTMode, settings
from app.core.deps import get_current_user
from app.core.rbac import require_permission, P_SENSOR_MANAGE
from app.db.base import get_db
from app.models.meter import Transformer
from app.models.sensor import SensorStatus, TransformerSensor
from app.models.sensor_reading import TransformerSensorReading
from app.models.user import User
from app.schemas.sensor import (
    SensorHistoryOut,
    SensorHistoryPoint,
    SensorThresholdUpdate,
    TransformerSensorOut,
)

try:
    from otel_common.audit import audit  # type: ignore
except ImportError:  # pragma: no cover
    async def audit(**kwargs): pass

router = APIRouter()


@router.get("/", response_model=List[TransformerSensorOut])
def list_sensors(
    transformer_id: Optional[int] = Query(None),
    sensor_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """List all transformer sensors, with optional filters."""
    q = db.query(TransformerSensor)
    if transformer_id:
        q = q.filter(TransformerSensor.transformer_id == transformer_id)
    if sensor_type:
        q = q.filter(TransformerSensor.sensor_type == sensor_type)
    if status:
        q = q.filter(TransformerSensor.status == status)
    return q.order_by(TransformerSensor.transformer_id, TransformerSensor.sensor_type).all()


@router.get("/transformer/{transformer_id}", response_model=List[TransformerSensorOut])
def get_transformer_sensors(
    transformer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Get all sensors for a specific transformer."""
    transformer = db.query(Transformer).filter(Transformer.id == transformer_id).first()
    if not transformer:
        raise HTTPException(status_code=404, detail="Transformer not found")
    return (
        db.query(TransformerSensor)
        .filter(TransformerSensor.transformer_id == transformer_id)
        .order_by(TransformerSensor.sensor_type)
        .all()
    )


def _sensor_reading_table_exists(db: Session) -> bool:
    try:
        bind = db.get_bind()
        return sa_inspect(bind).has_table("transformer_sensor_reading")
    except Exception:  # pragma: no cover
        return False


@router.get("/{sensor_id}/history", response_model=SensorHistoryOut)
def get_sensor_history(
    sensor_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return historical readings from the Kafka-fed `transformer_sensor_reading` table.

    Empty-table behaviour:
      * SSOT_MODE=strict  → 503 with `no_data_for_sensor`
      * otherwise         → empty history + `banner` hint string
    Never synthesises values — that was the W2B.T11 deliverable.
    """
    sensor = db.query(TransformerSensor).filter(TransformerSensor.id == sensor_id).first()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    history: List[SensorHistoryPoint] = []
    empty_reason: Optional[str] = None

    # The key used to join sensor → reading is the transformer sensor's
    # `sensor_code` (VARCHAR) OR, when absent, the sensor's primary key as str.
    match_key = getattr(sensor, "sensor_code", None) or str(sensor.id)

    if _sensor_reading_table_exists(db):
        rows = (
            db.query(TransformerSensorReading)
            .filter(
                TransformerSensorReading.sensor_id == match_key,
                TransformerSensorReading.ts >= cutoff,
            )
            .order_by(TransformerSensorReading.ts.asc())
            .all()
        )
        for r in rows:
            history.append(
                SensorHistoryPoint(
                    timestamp=r.ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    value=round(float(r.value) if r.value is not None else 0.0, 2),
                )
            )
        if not rows:
            empty_reason = (
                "No historical sensor data — waiting for Kafka stream on "
                "hesv2.sensor.readings"
            )
    else:
        empty_reason = (
            "transformer_sensor_reading table not yet provisioned (W2A migration "
            "pending)"
        )

    if empty_reason and settings.SSOT_MODE == SSOTMode.strict:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "no_data_for_sensor",
                "sensor_id": sensor_id,
                "message": empty_reason,
            },
        )

    return SensorHistoryOut(
        sensor_id=sensor.id,
        sensor_type=sensor.sensor_type,
        unit=sensor.unit,
        history=history,
        banner=empty_reason,
    )


@router.post(
    "/{sensor_id}/threshold",
    response_model=TransformerSensorOut,
    dependencies=[Depends(require_permission(P_SENSOR_MANAGE))],
)
async def update_threshold(
    sensor_id: int,
    payload: SensorThresholdUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update warning/critical thresholds for a sensor."""
    sensor = db.query(TransformerSensor).filter(TransformerSensor.id == sensor_id).first()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    if payload.threshold_warning is not None:
        sensor.threshold_warning = payload.threshold_warning
    if payload.threshold_critical is not None:
        sensor.threshold_critical = payload.threshold_critical
    db.commit()
    db.refresh(sensor)
    await audit(
        action_type="WRITE",
        action_name="update_sensor_threshold",
        entity_type="TransformerSensor",
        entity_id=str(sensor.id),
        request_data=payload.model_dump(),
        status=200,
        method="POST",
        path=f"/api/v1/sensors/{sensor_id}/threshold",
        user_id=str(current_user.id),
    )
    return sensor
