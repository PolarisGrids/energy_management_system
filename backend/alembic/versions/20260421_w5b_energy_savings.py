"""Energy Saving Analysis — org_unit + appliance + tou_tariff tables.

Revision ID: w5b_energy_savings
Revises: w5_der_consumer_inverter
Create Date: 2026-04-21

Adds a tiny org hierarchy (company > department > branch > customer), an
appliance reference catalog, per-customer appliance usage rows, and a TOU
tariff table seeded with the Eskom Megaflex baseline as the default row.

The Savings Analysis tab on /energy-monitoring consumes these tables via
``/api/v1/energy-savings/*``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w5b_energy_savings"
down_revision: Union[str, Sequence[str], None] = "w5_der_consumer_inverter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


_APPLIANCE_SEED = [
    # code,             category,      display,                     kW,   run_hrs, shift_hrs, desc
    ("ac_split_18k",    "ac",          "Split AC (18k BTU)",        1.80, 8.0,     2.0,
     "Residential split-unit AC — lightly shiftable (pre-cool off-peak)."),
    ("ac_central_5hp",  "ac",          "Central AC (5 HP)",         3.70, 6.0,     1.5,
     "Commercial central AC — partial pre-cool possible."),
    ("water_pump_1hp",  "water_pump",  "Booster pump (1 HP)",       0.75, 4.0,     3.0,
     "Domestic booster pump — fully shiftable via tank/storage."),
    ("water_pump_5hp",  "water_pump",  "Farm water pump (5 HP)",    3.70, 6.0,     5.0,
     "Irrigation pump — highly shiftable (schedule off-peak)."),
    ("ev_charger_l2",   "ev_charger",  "EV charger (Level 2, 7 kW)", 7.00, 3.0,    3.0,
     "Overnight EV charging is a poster-child load-shift."),
    ("ev_charger_dc",   "ev_charger",  "DC fast charger (50 kW)",   50.00, 1.5,   0.5,
     "DC fast session — partially shiftable via session scheduling."),
    ("geyser_3kw",      "geyser",      "Geyser (3 kW)",             3.00, 3.5,    3.0,
     "Electric hot-water cylinder — ripple control / timer friendly."),
    ("lighting_led",    "lighting",    "LED lighting bank (0.5 kW)", 0.50, 5.0,   0.5,
     "Lighting load — small shift only."),
]


def upgrade() -> None:
    # ── org_unit ──────────────────────────────────────────────────────────
    if not _has_table("org_unit"):
        op.create_table(
            "org_unit",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "parent_id",
                sa.String(36),
                sa.ForeignKey("org_unit.id"),
                nullable=True,
            ),
            sa.Column("level", sa.String(20), nullable=False),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("code", sa.String(40), nullable=True),
            sa.Column("meter_serial", sa.String(50), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
            sa.CheckConstraint(
                "level IN ('company','department','branch','customer')",
                name="ck_org_unit_level",
            ),
        )
        op.create_index("ix_org_unit_parent_id", "org_unit", ["parent_id"])
        op.create_index("ix_org_unit_level", "org_unit", ["level"])
        op.create_index("ix_org_unit_meter_serial", "org_unit", ["meter_serial"])

    # ── appliance_catalog ─────────────────────────────────────────────────
    if not _has_table("appliance_catalog"):
        op.create_table(
            "appliance_catalog",
            sa.Column("code", sa.String(40), primary_key=True),
            sa.Column("category", sa.String(30), nullable=False),
            sa.Column("display_name", sa.Text, nullable=False),
            sa.Column("typical_kw", sa.Numeric(8, 3), nullable=False),
            sa.Column("typical_running_hours", sa.Numeric(5, 2), nullable=False),
            sa.Column("shiftable_hours", sa.Numeric(5, 2), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
            sa.CheckConstraint(
                "category IN ('ac','water_pump','ev_charger','geyser','lighting','other')",
                name="ck_appliance_catalog_category",
            ),
        )
        op.create_index(
            "ix_appliance_catalog_category", "appliance_catalog", ["category"]
        )

        op.bulk_insert(
            sa.table(
                "appliance_catalog",
                sa.column("code", sa.String),
                sa.column("category", sa.String),
                sa.column("display_name", sa.Text),
                sa.column("typical_kw", sa.Numeric),
                sa.column("typical_running_hours", sa.Numeric),
                sa.column("shiftable_hours", sa.Numeric),
                sa.column("description", sa.Text),
            ),
            [
                {
                    "code": code,
                    "category": cat,
                    "display_name": dn,
                    "typical_kw": kw,
                    "typical_running_hours": rh,
                    "shiftable_hours": sh,
                    "description": desc,
                }
                for code, cat, dn, kw, rh, sh, desc in _APPLIANCE_SEED
            ],
        )

    # ── appliance_usage ───────────────────────────────────────────────────
    if not _has_table("appliance_usage"):
        op.create_table(
            "appliance_usage",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "org_unit_id",
                sa.String(36),
                sa.ForeignKey("org_unit.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "appliance_code",
                sa.String(40),
                sa.ForeignKey("appliance_catalog.code"),
                nullable=False,
            ),
            sa.Column("count", sa.Integer, nullable=False, server_default="1"),
            sa.Column("peak_hours", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("standard_hours", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("offpeak_hours", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column(
                "shiftable_peak_hours",
                sa.Numeric(5, 2),
                nullable=False,
                server_default="0",
            ),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                onupdate=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_appliance_usage_org_unit_id", "appliance_usage", ["org_unit_id"]
        )
        op.create_index(
            "ix_appliance_usage_appliance_code",
            "appliance_usage",
            ["appliance_code"],
        )

    # ── tou_tariff ────────────────────────────────────────────────────────
    if not _has_table("tou_tariff"):
        op.create_table(
            "tou_tariff",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("currency", sa.String(8), nullable=False, server_default="ZAR"),
            sa.Column("peak_rate", sa.Numeric(10, 4), nullable=False),
            sa.Column("standard_rate", sa.Numeric(10, 4), nullable=False),
            sa.Column("offpeak_rate", sa.Numeric(10, 4), nullable=False),
            sa.Column(
                "peak_windows",
                sa.String(60),
                nullable=False,
                server_default="06-09,17-20",
            ),
            sa.Column(
                "offpeak_windows",
                sa.String(60),
                nullable=False,
                server_default="22-06",
            ),
            sa.Column(
                "is_default", sa.Boolean, nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                onupdate=sa.text("now()"),
            ),
            sa.UniqueConstraint("name", name="uq_tou_tariff_name"),
        )
        op.create_index("ix_tou_tariff_is_default", "tou_tariff", ["is_default"])

        # Seed Megaflex baseline.
        op.bulk_insert(
            sa.table(
                "tou_tariff",
                sa.column("name", sa.String),
                sa.column("currency", sa.String),
                sa.column("peak_rate", sa.Numeric),
                sa.column("standard_rate", sa.Numeric),
                sa.column("offpeak_rate", sa.Numeric),
                sa.column("peak_windows", sa.String),
                sa.column("offpeak_windows", sa.String),
                sa.column("is_default", sa.Boolean),
            ),
            [
                {
                    "name": "Eskom Megaflex (baseline)",
                    "currency": "ZAR",
                    "peak_rate": 3.20,
                    "standard_rate": 1.80,
                    "offpeak_rate": 1.00,
                    "peak_windows": "06-09,17-20",
                    "offpeak_windows": "22-06",
                    "is_default": True,
                }
            ],
        )


def downgrade() -> None:
    for t in ("tou_tariff", "appliance_usage", "appliance_catalog", "org_unit"):
        if _has_table(t):
            op.drop_table(t)
