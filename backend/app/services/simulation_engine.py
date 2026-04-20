"""
Live simulation engine for DER scenarios.
Applies network-model calculations step-by-step.
"""
import math
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.simulation import SimulationScenario, SimulationStep, ScenarioStatus, ScenarioType
from app.models.alarm import Alarm, AlarmType, AlarmSeverity, AlarmStatus
from app.models.meter import Feeder, Transformer, Meter, MeterStatus
from app.models.der import DERAsset, DERStatus
from app.models.network import NetworkEvent, EventType
from app.models.sensor import TransformerSensor, SensorStatus


class SimulationEngine:
    """Applies physics-based network state calculations for each simulation step."""

    def __init__(self, db: Session):
        self.db = db

    def apply_step(self, scenario: SimulationScenario):
        steps = scenario.steps
        if not steps:
            scenario.status = ScenarioStatus.COMPLETED
            return

        if scenario.current_step >= len(steps):
            scenario.status = ScenarioStatus.COMPLETED
            scenario.completed_at = datetime.now(timezone.utc)
            return

        step = steps[scenario.current_step]
        scenario.current_step += 1

        if scenario.scenario_type == ScenarioType.SOLAR_OVERVOLTAGE:
            self._apply_solar_overvoltage_step(scenario, step)
        elif scenario.scenario_type == ScenarioType.EV_FAST_CHARGING:
            self._apply_ev_charging_step(scenario, step)
        elif scenario.scenario_type == ScenarioType.PEAKING_MICROGRID:
            self._apply_microgrid_step(scenario, step)
        elif scenario.scenario_type == ScenarioType.NETWORK_FAULT:
            self._apply_fault_step(scenario, step)
        elif scenario.scenario_type == ScenarioType.SENSOR_ASSET:
            self._apply_sensor_step(scenario, step)

        if scenario.current_step >= len(steps):
            scenario.status = ScenarioStatus.COMPLETED
            scenario.completed_at = datetime.now(timezone.utc)

    def _apply_solar_overvoltage_step(self, scenario: SimulationScenario, step: SimulationStep):
        """Solar export builds up, voltage rises, inverter curtailment triggered."""
        state = step.network_state or {}
        voltage_pu = state.get("voltage_pu", 1.0)
        pv_output_kw = state.get("pv_output_kw", 0.0)

        if scenario.der_asset_id:
            asset = self.db.query(DERAsset).filter(DERAsset.id == scenario.der_asset_id).first()
            if asset:
                asset.current_output_kw = pv_output_kw
                if voltage_pu > 1.10:
                    asset.status = DERStatus.CURTAILED

        if scenario.transformer_id:
            transformer = self.db.query(Transformer).filter(
                Transformer.id == scenario.transformer_id
            ).first()
            if transformer:
                transformer.voltage_pu = voltage_pu
                transformer.current_load_kw = state.get("load_kw", transformer.current_load_kw)

        if voltage_pu > 1.10 and step.alarms_triggered:
            self._create_alarm(
                AlarmType.OVERVOLTAGE,
                AlarmSeverity.CRITICAL,
                f"Overvoltage detected: {voltage_pu:.3f} pu on feeder (limit: 1.10 pu)",
                scenario.transformer_id,
                value=voltage_pu,
                threshold=1.10,
                unit="pu",
            )

    def _apply_ev_charging_step(self, scenario: SimulationScenario, step: SimulationStep):
        """EV fast charger load impacts transformer; curtailment prevents overload."""
        state = step.network_state or {}
        loading_pct = state.get("loading_percent", 0.0)
        ev_demand_kw = state.get("ev_demand_kw", 0.0)

        if scenario.der_asset_id:
            asset = self.db.query(DERAsset).filter(DERAsset.id == scenario.der_asset_id).first()
            if asset:
                asset.current_output_kw = ev_demand_kw
                asset.active_sessions = state.get("active_sessions", 0)

        if scenario.transformer_id:
            transformer = self.db.query(Transformer).filter(
                Transformer.id == scenario.transformer_id
            ).first()
            if transformer:
                transformer.loading_percent = loading_pct
                transformer.current_load_kw = state.get("transformer_load_kw", transformer.current_load_kw)

        if loading_pct > 100.0 and step.alarms_triggered:
            self._create_alarm(
                AlarmType.TRANSFORMER_OVERLOAD,
                AlarmSeverity.CRITICAL,
                f"Transformer overload: {loading_pct:.1f}% loading (limit: 100%)",
                scenario.transformer_id,
                value=loading_pct,
                threshold=100.0,
                unit="%",
            )
        elif loading_pct > 80.0 and step.alarms_triggered:
            self._create_alarm(
                AlarmType.TRANSFORMER_OVERLOAD,
                AlarmSeverity.HIGH,
                f"Transformer high loading warning: {loading_pct:.1f}%",
                scenario.transformer_id,
                value=loading_pct,
                threshold=80.0,
                unit="%",
            )

    def _apply_microgrid_step(self, scenario: SimulationScenario, step: SimulationStep):
        """Peaking microgrid comes online, causes reverse power flow."""
        state = step.network_state or {}
        reverse_power = state.get("reverse_power_kw", 0.0)
        islanded = state.get("islanded", False)

        if scenario.der_asset_id:
            asset = self.db.query(DERAsset).filter(DERAsset.id == scenario.der_asset_id).first()
            if asset:
                asset.current_output_kw = state.get("output_kw", 0.0)
                asset.reverse_power_flow = reverse_power > 0
                asset.islanded = islanded

        if reverse_power > 0 and step.alarms_triggered:
            self._create_alarm(
                AlarmType.REVERSE_POWER,
                AlarmSeverity.HIGH,
                f"Reverse power flow detected: {reverse_power:.1f} kW on feeder",
                scenario.transformer_id,
                value=reverse_power,
                threshold=0.0,
                unit="kW",
            )

    def _apply_fault_step(self, scenario: SimulationScenario, step: SimulationStep):
        """Network fault, isolation, and FLISR — full 8-step scenario."""
        state = step.network_state or {}
        step_phase = state.get("phase", "normal")
        affected_customers = state.get("affected_customers", 0)
        restored_customers = state.get("restored_customers", 0)
        feeder_id = scenario.feeder_id
        fault_feeder_id = state.get("fault_feeder_id", feeder_id)

        # --- Phase: normal ---
        if step_phase == "normal":
            # Ensure all meters on feeder are online
            if feeder_id:
                meters = (
                    self.db.query(Meter)
                    .join(Transformer)
                    .filter(Transformer.feeder_id == feeder_id)
                    .all()
                )
                for m in meters:
                    m.status = MeterStatus.ONLINE
                    m.last_seen = datetime.now(timezone.utc)
            # Resolve any lingering fault alarms from previous runs
            old_alarms = (
                self.db.query(Alarm)
                .filter(Alarm.scenario_id == scenario.id, Alarm.status == AlarmStatus.ACTIVE)
                .all()
            )
            for a in old_alarms:
                a.status = AlarmStatus.RESOLVED
                a.resolved_at = datetime.now(timezone.utc)

        # --- Phase: fault_occurs ---
        elif step_phase == "fault_occurs":
            fault_type = state.get("fault_type", "LV cable fault")
            current_spike_factor = state.get("current_spike_factor", 3.0)

            # Spike feeder current (protection relay will trip)
            if feeder_id:
                feeder = self.db.query(Feeder).filter(Feeder.id == feeder_id).first()
                if feeder:
                    feeder.current_load_kw = feeder.current_load_kw * current_spike_factor

            # Take downstream meters offline
            downstream_transformers = state.get("downstream_transformer_ids", [])
            if downstream_transformers:
                offline_meters = (
                    self.db.query(Meter)
                    .filter(Meter.transformer_id.in_(downstream_transformers))
                    .all()
                )
                for m in offline_meters:
                    m.status = MeterStatus.OFFLINE
            elif feeder_id:
                # Fall back to all meters on feeder
                offline_meters = (
                    self.db.query(Meter)
                    .join(Transformer)
                    .filter(Transformer.feeder_id == feeder_id)
                    .all()
                )
                for m in offline_meters:
                    m.status = MeterStatus.OFFLINE

            # Create FAULT_DETECTED alarm
            if step.alarms_triggered:
                self._create_alarm(
                    AlarmType.FAULT_DETECTED,
                    AlarmSeverity.CRITICAL,
                    f"Fault detected on Feeder F-003: {fault_type} — current spike {current_spike_factor}x normal. "
                    f"{affected_customers} customers affected.",
                    scenario.transformer_id,
                    scenario_id=scenario.id,
                )
                # Create OUTAGE alarms for affected area
                self._create_alarm(
                    AlarmType.OUTAGE,
                    AlarmSeverity.CRITICAL,
                    f"Mass outage: {affected_customers} meters lost supply on Feeder F-003",
                    scenario.transformer_id,
                    scenario_id=scenario.id,
                )

            # Log network event
            self.db.add(NetworkEvent(
                event_type=EventType.FAULT,
                feeder_id=feeder_id,
                transformer_id=scenario.transformer_id,
                description=f"Fault detected between T-012 and T-015 — protection relay tripped. "
                            f"{affected_customers} customers affected.",
                affected_customers=affected_customers,
                event_data=state,
                scenario_id=scenario.id,
            ))

        # --- Phase: fault_detection ---
        elif step_phase == "fault_detection":
            first_dark_meter = state.get("first_dark_meter")
            fault_location = state.get("fault_location", {})

            # Create COMM_LOSS alarms for all offline meters
            if step.alarms_triggered:
                self._create_alarm(
                    AlarmType.COMM_LOSS,
                    AlarmSeverity.HIGH,
                    f"Communication loss: {affected_customers} meters offline downstream of fault. "
                    f"First dark meter: {first_dark_meter or 'unknown'}. "
                    f"Fault located between {fault_location.get('upstream', 'T-012')} and "
                    f"{fault_location.get('downstream', 'T-015')}.",
                    scenario.transformer_id,
                    scenario_id=scenario.id,
                )

            self.db.add(NetworkEvent(
                event_type=EventType.FAULT,
                feeder_id=feeder_id,
                transformer_id=scenario.transformer_id,
                description=f"Fault location identified via first-dark-meter analysis. "
                            f"First dark: {first_dark_meter}. "
                            f"Fault between {fault_location.get('upstream', 'T-012')} and "
                            f"{fault_location.get('downstream', 'T-015')}.",
                affected_customers=affected_customers,
                event_data=state,
                scenario_id=scenario.id,
            ))

        # --- Phase: fault_isolation ---
        elif step_phase == "fault_isolation":
            # Open sectionalizer switches to isolate fault segment
            self.db.add(NetworkEvent(
                event_type=EventType.SWITCHING,
                feeder_id=feeder_id,
                transformer_id=scenario.transformer_id,
                description="Sectionalizer switches opened — fault segment isolated between T-012 and T-015.",
                affected_customers=affected_customers,
                event_data={**state, "switch_action": "open", "switches": ["SW-012-UP", "SW-015-DN"]},
                scenario_id=scenario.id,
            ))

        # --- Phase: restore_phase1 ---
        elif step_phase == "restore_phase1":
            # Close tie switch to alternate feeder — partial restoration
            restored = state.get("restored_customers", 0)
            remaining = affected_customers - restored

            # Bring some meters back online (downstream of tie switch)
            restore_transformer_ids = state.get("restore_transformer_ids", [])
            if restore_transformer_ids:
                restored_meters = (
                    self.db.query(Meter)
                    .filter(
                        Meter.transformer_id.in_(restore_transformer_ids),
                        Meter.status == MeterStatus.OFFLINE,
                    )
                    .all()
                )
                for m in restored_meters:
                    m.status = MeterStatus.ONLINE
                    m.last_seen = datetime.now(timezone.utc)

            self.db.add(NetworkEvent(
                event_type=EventType.RESTORE,
                feeder_id=feeder_id,
                transformer_id=scenario.transformer_id,
                description=f"Tie switch closed to alternate feeder — {restored} customers restored "
                            f"({remaining} still affected).",
                affected_customers=remaining,
                event_data=state,
                scenario_id=scenario.id,
            ))

        # --- Phase: restore_phase2 ---
        elif step_phase == "restore_phase2":
            restored = state.get("restored_customers", 0)
            remaining = affected_customers - restored

            # Bring more meters back online
            restore_transformer_ids = state.get("restore_transformer_ids", [])
            if restore_transformer_ids:
                restored_meters = (
                    self.db.query(Meter)
                    .filter(
                        Meter.transformer_id.in_(restore_transformer_ids),
                        Meter.status == MeterStatus.OFFLINE,
                    )
                    .all()
                )
                for m in restored_meters:
                    m.status = MeterStatus.ONLINE
                    m.last_seen = datetime.now(timezone.utc)

            self.db.add(NetworkEvent(
                event_type=EventType.RESTORE,
                feeder_id=feeder_id,
                transformer_id=scenario.transformer_id,
                description=f"Remaining switches reconfigured — {restored} total customers restored "
                            f"({remaining} in fault segment awaiting repair).",
                affected_customers=remaining,
                event_data=state,
                scenario_id=scenario.id,
            ))

        # --- Phase: crew_dispatch ---
        elif step_phase == "crew_dispatch":
            if step.alarms_triggered:
                self._create_alarm(
                    AlarmType.FAULT_DETECTED,
                    AlarmSeverity.MEDIUM,
                    f"Maintenance work order WO-{scenario.id:04d} generated for fault segment repair. "
                    f"Crew dispatched to fault location between T-012 and T-015. "
                    f"{affected_customers} customers on alternate feed.",
                    scenario.transformer_id,
                    scenario_id=scenario.id,
                )

            self.db.add(NetworkEvent(
                event_type=EventType.FAULT,
                feeder_id=feeder_id,
                transformer_id=scenario.transformer_id,
                description=f"Work order WO-{scenario.id:04d} generated. "
                            f"Repair crew dispatched. Network stable on alternate feed.",
                affected_customers=affected_customers,
                event_data={**state, "work_order": f"WO-{scenario.id:04d}"},
                scenario_id=scenario.id,
            ))

        # --- Phase: fully_restored ---
        elif step_phase == "fully_restored":
            # Bring all remaining meters back online
            if feeder_id:
                remaining_offline = (
                    self.db.query(Meter)
                    .join(Transformer)
                    .filter(
                        Transformer.feeder_id == feeder_id,
                        Meter.status == MeterStatus.OFFLINE,
                    )
                    .all()
                )
                for m in remaining_offline:
                    m.status = MeterStatus.ONLINE
                    m.last_seen = datetime.now(timezone.utc)

            # Resolve all active alarms for this scenario
            active_alarms = (
                self.db.query(Alarm)
                .filter(Alarm.scenario_id == scenario.id, Alarm.status == AlarmStatus.ACTIVE)
                .all()
            )
            for a in active_alarms:
                a.status = AlarmStatus.RESOLVED
                a.resolved_at = datetime.now(timezone.utc)

            # Reset feeder current to normal
            if feeder_id:
                feeder = self.db.query(Feeder).filter(Feeder.id == feeder_id).first()
                if feeder:
                    feeder.current_load_kw = state.get("normal_load_kw", feeder.capacity_kva * 0.4)

            self.db.add(NetworkEvent(
                event_type=EventType.RESTORE,
                feeder_id=feeder_id,
                transformer_id=scenario.transformer_id,
                description="Fault repaired, original switching restored. "
                            "All meters online, all alarms resolved. Normal topology restored.",
                affected_customers=0,
                resolved=True,
                event_data=state,
                scenario_id=scenario.id,
            ))

    async def _correlate_fault_location(self, feeder_id: int) -> dict:
        """Find fault location using meter last-seen analysis (first-dark-meter method)."""
        # Query meters on the feeder ordered by last_seen ASC (first to go dark = closest to fault)
        meters = (
            self.db.query(Meter)
            .join(Transformer)
            .filter(Transformer.feeder_id == feeder_id, Meter.status == MeterStatus.OFFLINE)
            .order_by(Meter.last_seen.asc())
            .all()
        )

        if not meters:
            return {"fault_between": [], "first_dark_meter": None}

        first_dark = meters[0]
        transformer = self.db.query(Transformer).filter(
            Transformer.id == first_dark.transformer_id
        ).first()

        # Find the adjacent transformer upstream
        upstream_transformers = (
            self.db.query(Transformer)
            .filter(
                Transformer.feeder_id == feeder_id,
                Transformer.id != transformer.id,
            )
            .order_by(Transformer.id)
            .all()
        )

        upstream = None
        for t in upstream_transformers:
            if t.id < transformer.id:
                upstream = t

        return {
            "fault_between": [
                upstream.name if upstream else "Substation",
                transformer.name,
            ],
            "first_dark_meter": first_dark.serial,
            "first_dark_transformer": transformer.name,
            "total_offline": len(meters),
        }

    def _apply_sensor_step(self, scenario: SimulationScenario, step: SimulationStep):
        """Transformer sensor monitoring — temperature, oil, vibration anomaly lifecycle."""
        state = step.network_state or {}
        sensor_values = state.get("sensor_values", {})
        loading_pct = state.get("loading_percent", None)

        if scenario.transformer_id:
            transformer = self.db.query(Transformer).filter(
                Transformer.id == scenario.transformer_id
            ).first()
            if transformer and loading_pct is not None:
                transformer.loading_percent = loading_pct
                transformer.current_load_kw = (loading_pct / 100.0) * transformer.capacity_kva

            # Update sensor values from step state
            sensors = (
                self.db.query(TransformerSensor)
                .filter(TransformerSensor.transformer_id == scenario.transformer_id)
                .all()
            )
            for sensor in sensors:
                if sensor.sensor_type in sensor_values:
                    new_val = sensor_values[sensor.sensor_type]
                    sensor.value = new_val
                    sensor.last_updated = datetime.now(timezone.utc)

                    # Evaluate thresholds
                    if sensor.sensor_type == "oil_level":
                        # Oil level: warning when BELOW threshold
                        if sensor.threshold_critical and new_val <= sensor.threshold_critical:
                            sensor.status = SensorStatus.CRITICAL
                        elif sensor.threshold_warning and new_val <= sensor.threshold_warning:
                            sensor.status = SensorStatus.WARNING
                        else:
                            sensor.status = SensorStatus.NORMAL
                    else:
                        # Other sensors: warning when ABOVE threshold
                        if sensor.threshold_critical and new_val >= sensor.threshold_critical:
                            sensor.status = SensorStatus.CRITICAL
                        elif sensor.threshold_warning and new_val >= sensor.threshold_warning:
                            sensor.status = SensorStatus.WARNING
                        else:
                            sensor.status = SensorStatus.NORMAL

        # Create alarms based on step alarm triggers
        if step.alarms_triggered:
            for alarm_def in step.alarms_triggered:
                alarm_severity_str = alarm_def.get("severity", "high")
                severity_map = {
                    "info": AlarmSeverity.INFO,
                    "low": AlarmSeverity.LOW,
                    "medium": AlarmSeverity.MEDIUM,
                    "high": AlarmSeverity.HIGH,
                    "critical": AlarmSeverity.CRITICAL,
                }
                severity = severity_map.get(alarm_severity_str, AlarmSeverity.HIGH)

                alarm_type_str = alarm_def.get("type", "transformer_overload")
                alarm_type_map = {
                    "transformer_overload": AlarmType.TRANSFORMER_OVERLOAD,
                    "overcurrent": AlarmType.OVERCURRENT,
                    "overvoltage": AlarmType.OVERVOLTAGE,
                    "comm_loss": AlarmType.COMM_LOSS,
                }
                alarm_type = alarm_type_map.get(alarm_type_str, AlarmType.TRANSFORMER_OVERLOAD)

                self._create_alarm(
                    alarm_type,
                    severity,
                    alarm_def.get("message", "Transformer sensor alarm"),
                    scenario.transformer_id,
                    value=alarm_def.get("value"),
                    threshold=alarm_def.get("threshold"),
                    unit=alarm_def.get("unit"),
                    scenario_id=scenario.id,
                )

        # Resolve alarms if step says so
        if state.get("resolve_alarms"):
            active_alarms = (
                self.db.query(Alarm)
                .filter(Alarm.scenario_id == scenario.id, Alarm.status == AlarmStatus.ACTIVE)
                .all()
            )
            for a in active_alarms:
                a.status = AlarmStatus.RESOLVED
                a.resolved_at = datetime.now(timezone.utc)

    def _create_alarm(
        self,
        alarm_type: AlarmType,
        severity: AlarmSeverity,
        description: str,
        transformer_id: Optional[int],
        value: Optional[float] = None,
        threshold: Optional[float] = None,
        unit: Optional[str] = None,
        scenario_id: Optional[int] = None,
    ):
        transformer = None
        lat, lon = None, None
        if transformer_id:
            transformer = self.db.query(Transformer).filter(Transformer.id == transformer_id).first()
            if transformer:
                lat, lon = transformer.latitude, transformer.longitude

        alarm = Alarm(
            alarm_type=alarm_type,
            severity=severity,
            status=AlarmStatus.ACTIVE,
            transformer_id=transformer_id,
            title=alarm_type.value.replace("_", " ").title(),
            description=description,
            latitude=lat,
            longitude=lon,
            value=value,
            threshold=threshold,
            unit=unit,
            scenario_id=scenario_id,
        )
        self.db.add(alarm)

    def apply_command(
        self,
        scenario: SimulationScenario,
        command: str,
        target_id: Optional[int],
        value: Optional[float],
    ) -> dict:
        """Process operator commands during a live simulation."""
        if command == "curtail_inverter" and target_id:
            asset = self.db.query(DERAsset).filter(DERAsset.id == target_id).first()
            if asset:
                curtailed_to = value or (asset.rated_capacity_kw * 0.5)
                asset.current_output_kw = curtailed_to
                asset.status = DERStatus.CURTAILED
                return {"action": "curtailed", "asset_id": target_id, "output_kw": curtailed_to}

        if command == "open_switch_upstream":
            # FLISR: Open upstream sectionalizer switch
            self.db.add(NetworkEvent(
                event_type=EventType.SWITCHING,
                feeder_id=scenario.feeder_id,
                description="Upstream sectionalizer switch opened by operator command.",
                affected_customers=0,
                event_data={"command": "open_switch_upstream", "switch": "SW-012-UP"},
                scenario_id=scenario.id,
            ))
            return {"action": "switch_opened", "switch": "SW-012-UP", "direction": "upstream"}

        if command == "open_switch_downstream":
            # FLISR: Open downstream sectionalizer switch
            self.db.add(NetworkEvent(
                event_type=EventType.SWITCHING,
                feeder_id=scenario.feeder_id,
                description="Downstream sectionalizer switch opened by operator command.",
                affected_customers=0,
                event_data={"command": "open_switch_downstream", "switch": "SW-015-DN"},
                scenario_id=scenario.id,
            ))
            return {"action": "switch_opened", "switch": "SW-015-DN", "direction": "downstream"}

        if command == "isolate_feeder" and target_id:
            # Mark all meters on feeder as offline (fault isolation)
            meters = (
                self.db.query(Meter)
                .join(Transformer)
                .filter(Transformer.feeder_id == target_id)
                .all()
            )
            for m in meters:
                m.status = MeterStatus.OFFLINE
            return {"action": "isolated", "feeder_id": target_id, "affected": len(meters)}

        if command == "restore_feeder" and target_id:
            meters = (
                self.db.query(Meter)
                .join(Transformer)
                .filter(Transformer.feeder_id == target_id, Meter.status == MeterStatus.OFFLINE)
                .all()
            )
            for m in meters:
                m.status = MeterStatus.ONLINE
            return {"action": "restored", "feeder_id": target_id, "restored": len(meters)}

        if command == "curtail_ev_charger" and target_id:
            asset = self.db.query(DERAsset).filter(DERAsset.id == target_id).first()
            if asset:
                new_power = value or (asset.current_output_kw * 0.6)
                asset.current_output_kw = new_power
                return {"action": "curtailed", "asset_id": target_id, "new_power_kw": new_power}

        if command == "reduce_load" and target_id:
            transformer = self.db.query(Transformer).filter(Transformer.id == target_id).first()
            if transformer:
                transformer.loading_percent = min(transformer.loading_percent * 0.75, 75.0)
                transformer.current_load_kw = (transformer.loading_percent / 100.0) * transformer.capacity_kva
                return {"action": "load_reduced", "transformer_id": target_id, "new_loading": transformer.loading_percent}

        if command == "emergency_load_transfer" and target_id:
            transformer = self.db.query(Transformer).filter(Transformer.id == target_id).first()
            if transformer:
                transformer.loading_percent = 0.0
                transformer.current_load_kw = 0.0
                # Set all sensors to normal/offline
                sensors = self.db.query(TransformerSensor).filter(TransformerSensor.transformer_id == target_id).all()
                for s in sensors:
                    s.status = SensorStatus.NORMAL
                return {"action": "load_transferred", "transformer_id": target_id, "status": "de-energized"}

        if command == "schedule_maintenance" and target_id:
            return {"action": "maintenance_scheduled", "transformer_id": target_id, "work_order": f"WO-TX-{target_id:04d}"}

        if command == "crew_dispatch" and target_id:
            return {"action": "crew_dispatched", "transformer_id": target_id, "eta_minutes": 45}

        return {"action": "unknown_command", "command": command}
