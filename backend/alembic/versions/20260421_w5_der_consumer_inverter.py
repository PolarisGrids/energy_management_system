"""W5 DER consumer / type-catalog / metrology / inverter tables.

Revision ID: w5_der_consumer_inverter
Revises: w4a_userrole_enum
Create Date: 2026-04-21

Adds the consumer-facing + equipment dimension to the DER schema:

  * der_consumer            — owner/account record
  * der_type_catalog        — sub-type taxonomy (rooftop_pv, dc_fast_charger, …)
  * der_metrology           — billing-grade interval reads (per asset)
  * der_metrology_daily     — daily rollup for fast 30-day charts
  * der_inverter            — equipment record (one-to-many with der_asset)
  * der_inverter_telemetry  — per-inverter operational time-series (single
                              table at MVP; partition later if volume warrants)

Plus ALTER der_asset to add `consumer_id` (FK) and `type_code` (FK).

All adds are nullable so legacy rows keep working without a backfill.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "w5_der_consumer_inverter"
down_revision: Union[str, Sequence[str], None] = "w4a_userrole_enum"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


# ── Type catalog seed ─────────────────────────────────────────────────────────

_TYPE_CATALOG_SEED = [
    # PV
    ("pv_rooftop",          "pv",        "Rooftop PV",            "Residential / commercial rooftop solar",            1.0,    50.0,    "kW"),
    ("pv_ground_mount",     "pv",        "Ground-mount PV",       "Utility-scale ground array",                       100.0, 50000.0, "kW"),
    ("pv_floating",         "pv",        "Floating PV",           "Floating solar on water bodies",                   100.0,  5000.0, "kW"),
    ("pv_carport",          "pv",        "Carport PV",            "Solar canopy over parking",                          5.0,   500.0, "kW"),
    # BESS
    ("bess_lithium",        "bess",      "Lithium-ion BESS",      "LFP / NMC battery storage",                          5.0, 10000.0, "kWh"),
    ("bess_lead_acid",      "bess",      "Lead-acid BESS",        "Legacy lead-acid storage",                           5.0,   500.0, "kWh"),
    ("bess_flow",           "bess",      "Flow battery",          "Vanadium-redox / zinc-bromine",                    100.0, 10000.0, "kWh"),
    ("bess_hybrid",         "bess",      "Hybrid PV+BESS",        "Co-located PV + battery, single inverter",          5.0,  1000.0, "kWh"),
    # EV
    ("ev_ac_l2",            "ev",        "AC Level-2 charger",    "7-22 kW AC chargers (Type 2)",                       7.0,    22.0,  "kW"),
    ("ev_dc_fast",          "ev",        "DC fast charger",       "50-150 kW DC charging (CCS/CHAdeMO)",               50.0,   150.0,  "kW"),
    ("ev_dc_ultra",         "ev",        "DC ultra-fast charger", "150-350 kW DC ultra-fast",                         150.0,   350.0,  "kW"),
    ("ev_v2g",              "ev",        "V2G bidirectional",     "Vehicle-to-grid capable charger",                    7.0,    50.0,  "kW"),
    # Microgrid
    ("microgrid_hybrid",    "microgrid", "Hybrid microgrid",      "PV + BESS + diesel hybrid",                         50.0,  5000.0, "kW"),
    ("microgrid_diesel",    "microgrid", "Diesel-only microgrid", "Backup diesel genset cluster",                      50.0,  5000.0, "kW"),
]


def upgrade() -> None:
    # ── der_consumer ──────────────────────────────────────────────────────
    if not _has_table("der_consumer"):
        op.create_table(
            "der_consumer",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("account_no", sa.String(40), nullable=True),
            sa.Column("email", sa.String(200), nullable=True),
            sa.Column("phone", sa.String(40), nullable=True),
            sa.Column("premise_address", sa.Text, nullable=True),
            sa.Column("lat", sa.Numeric(10, 6), nullable=True),
            sa.Column("lon", sa.Numeric(10, 6), nullable=True),
            sa.Column("tariff_code", sa.String(20), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("onboarded_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("metadata", JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                onupdate=sa.text("now()"),
            ),
            sa.CheckConstraint(
                "status IN ('active','suspended','terminated','pending')",
                name="ck_der_consumer_status",
            ),
            sa.UniqueConstraint("account_no", name="uq_der_consumer_account_no"),
        )
        op.create_index("ix_der_consumer_name", "der_consumer", ["name"])
        op.create_index("ix_der_consumer_status", "der_consumer", ["status"])

    # ── der_type_catalog ──────────────────────────────────────────────────
    if not _has_table("der_type_catalog"):
        op.create_table(
            "der_type_catalog",
            sa.Column("code", sa.String(40), primary_key=True),
            sa.Column("category", sa.String(20), nullable=False),
            sa.Column("display_name", sa.Text, nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("typical_kw_min", sa.Numeric(12, 2), nullable=True),
            sa.Column("typical_kw_max", sa.Numeric(12, 2), nullable=True),
            sa.Column("default_unit", sa.String(10), nullable=False, server_default="kW"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.CheckConstraint(
                "category IN ('pv','bess','ev','microgrid','wind')",
                name="ck_der_type_catalog_category",
            ),
        )
        op.create_index("ix_der_type_catalog_category", "der_type_catalog", ["category"])

        # Seed taxonomy.
        op.bulk_insert(
            sa.table(
                "der_type_catalog",
                sa.column("code", sa.String),
                sa.column("category", sa.String),
                sa.column("display_name", sa.Text),
                sa.column("description", sa.Text),
                sa.column("typical_kw_min", sa.Numeric),
                sa.column("typical_kw_max", sa.Numeric),
                sa.column("default_unit", sa.String),
            ),
            [
                {
                    "code": code,
                    "category": cat,
                    "display_name": dn,
                    "description": desc,
                    "typical_kw_min": kmin,
                    "typical_kw_max": kmax,
                    "default_unit": unit,
                }
                for code, cat, dn, desc, kmin, kmax, unit in _TYPE_CATALOG_SEED
            ],
        )

    # ── der_metrology (interval) ──────────────────────────────────────────
    if not _has_table("der_metrology"):
        op.create_table(
            "der_metrology",
            sa.Column("asset_id", sa.String(100), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("energy_generated_kwh", sa.Numeric(14, 4), nullable=True),
            sa.Column("energy_exported_kwh", sa.Numeric(14, 4), nullable=True),
            sa.Column("energy_imported_kwh", sa.Numeric(14, 4), nullable=True),
            sa.Column("energy_self_consumed_kwh", sa.Numeric(14, 4), nullable=True),
            sa.Column("voltage_avg", sa.Numeric(8, 2), nullable=True),
            sa.Column("current_avg", sa.Numeric(10, 3), nullable=True),
            sa.Column("power_factor", sa.Numeric(4, 3), nullable=True),
            sa.Column("frequency_hz", sa.Numeric(6, 3), nullable=True),
            sa.Column("meter_serial", sa.String(50), nullable=True),
            sa.Column("quality", sa.String(16), nullable=False, server_default="raw"),
            sa.Column("source", sa.String(32), nullable=False, server_default="DER_TELEMETRY"),
            sa.Column("is_estimated", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column(
                "ingested_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("asset_id", "ts", name="pk_der_metrology_asset_ts"),
            sa.CheckConstraint(
                "quality IN ('valid','estimated','failed','raw')",
                name="ck_der_metrology_quality",
            ),
        )
        op.create_index("ix_der_metrology_asset_ts", "der_metrology", ["asset_id", "ts"])
        op.create_index("ix_der_metrology_meter_serial", "der_metrology", ["meter_serial"])
        op.create_index("ix_der_metrology_ingested_at", "der_metrology", ["ingested_at"])

    # ── der_metrology_daily (rollup) ──────────────────────────────────────
    if not _has_table("der_metrology_daily"):
        op.create_table(
            "der_metrology_daily",
            sa.Column("asset_id", sa.String(100), nullable=False),
            sa.Column("date", sa.Date, nullable=False),
            sa.Column("kwh_generated", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("kwh_exported", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("kwh_imported", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("kwh_self_consumed", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("peak_output_kw", sa.Numeric(12, 3), nullable=True),
            sa.Column("equivalent_hours", sa.Numeric(6, 3), nullable=True),
            sa.Column("achievement_pct", sa.Numeric(5, 2), nullable=True),
            sa.Column("reading_count", sa.Integer, nullable=True),
            sa.Column("estimated_count", sa.Integer, nullable=True),
            sa.Column("source", sa.String(32), nullable=False, server_default="DER_TELEMETRY"),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
                onupdate=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("asset_id", "date", name="pk_der_metrology_daily_asset_date"),
        )
        op.create_index("ix_der_metrology_daily_date", "der_metrology_daily", ["date"])

    # ── der_inverter ──────────────────────────────────────────────────────
    if not _has_table("der_inverter"):
        op.create_table(
            "der_inverter",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("asset_id", sa.String(100), nullable=False),
            sa.Column("manufacturer", sa.String(80), nullable=True),
            sa.Column("model", sa.String(80), nullable=True),
            sa.Column("serial_number", sa.String(80), nullable=True),
            sa.Column("firmware_version", sa.String(40), nullable=True),
            sa.Column("rated_ac_kw", sa.Numeric(10, 2), nullable=True),
            sa.Column("rated_dc_kw", sa.Numeric(10, 2), nullable=True),
            sa.Column("num_mppt_trackers", sa.SmallInteger, nullable=True),
            sa.Column("num_strings", sa.SmallInteger, nullable=True),
            sa.Column("phase_config", sa.String(10), nullable=True),
            sa.Column("ac_voltage_nominal_v", sa.Numeric(8, 2), nullable=True),
            sa.Column("comms_protocol", sa.String(20), nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("installation_date", sa.Date, nullable=True),
            sa.Column("commissioned_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("warranty_expires", sa.Date, nullable=True),
            sa.Column("last_firmware_update", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="online"),
            sa.Column("metadata", JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                onupdate=sa.text("now()"),
            ),
            sa.UniqueConstraint("serial_number", name="uq_der_inverter_serial_number"),
            sa.CheckConstraint(
                "status IN ('online','offline','fault','maintenance','commissioning')",
                name="ck_der_inverter_status",
            ),
            sa.CheckConstraint(
                "phase_config IS NULL OR phase_config IN ('single','three')",
                name="ck_der_inverter_phase_config",
            ),
        )
        op.create_index("ix_der_inverter_asset_id", "der_inverter", ["asset_id"])
        op.create_index("ix_der_inverter_status", "der_inverter", ["status"])
        op.create_index("ix_der_inverter_manufacturer", "der_inverter", ["manufacturer"])

    # ── der_inverter_telemetry ────────────────────────────────────────────
    if not _has_table("der_inverter_telemetry"):
        op.create_table(
            "der_inverter_telemetry",
            sa.Column("inverter_id", sa.String(36), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ac_voltage_v", sa.Numeric(8, 2), nullable=True),
            sa.Column("ac_current_a", sa.Numeric(10, 3), nullable=True),
            sa.Column("ac_power_kw", sa.Numeric(12, 3), nullable=True),
            sa.Column("ac_frequency_hz", sa.Numeric(6, 3), nullable=True),
            sa.Column("power_factor", sa.Numeric(4, 3), nullable=True),
            sa.Column("dc_voltage_v", sa.Numeric(8, 2), nullable=True),
            sa.Column("dc_current_a", sa.Numeric(10, 3), nullable=True),
            sa.Column("strings", JSONB, nullable=True),
            sa.Column("temperature_c", sa.Numeric(5, 2), nullable=True),
            sa.Column("efficiency_pct", sa.Numeric(5, 2), nullable=True),
            sa.Column("fault_code", sa.String(40), nullable=True),
            sa.Column("fault_description", sa.Text, nullable=True),
            sa.Column("state", sa.String(20), nullable=True),
            sa.Column(
                "ingested_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("inverter_id", "ts", name="pk_der_inverter_telemetry"),
        )
        op.create_index(
            "ix_der_inverter_telemetry_inv_ts",
            "der_inverter_telemetry",
            ["inverter_id", "ts"],
        )
        op.create_index(
            "ix_der_inverter_telemetry_fault",
            "der_inverter_telemetry",
            ["fault_code"],
        )

    # ── der_asset additions ───────────────────────────────────────────────
    # Both nullable so existing rows are valid without backfill.
    if _has_table("der_asset"):
        if not _has_column("der_asset", "consumer_id"):
            op.add_column(
                "der_asset",
                sa.Column("consumer_id", sa.String(36), nullable=True),
            )
            op.create_index("ix_der_asset_consumer_id", "der_asset", ["consumer_id"])
        if not _has_column("der_asset", "type_code"):
            op.add_column(
                "der_asset",
                sa.Column("type_code", sa.String(40), nullable=True),
            )
            op.create_index("ix_der_asset_type_code", "der_asset", ["type_code"])


def downgrade() -> None:
    # Reverse order of upgrade. ALTERs first, then drops.
    if _has_table("der_asset"):
        if _has_column("der_asset", "type_code"):
            op.drop_index("ix_der_asset_type_code", table_name="der_asset")
            op.drop_column("der_asset", "type_code")
        if _has_column("der_asset", "consumer_id"):
            op.drop_index("ix_der_asset_consumer_id", table_name="der_asset")
            op.drop_column("der_asset", "consumer_id")

    for t in (
        "der_inverter_telemetry",
        "der_inverter",
        "der_metrology_daily",
        "der_metrology",
        "der_type_catalog",
        "der_consumer",
    ):
        if _has_table(t):
            op.drop_table(t)
