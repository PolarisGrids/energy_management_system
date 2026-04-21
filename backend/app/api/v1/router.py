from fastapi import APIRouter
from app.api.v1.endpoints import auth, meters, alarms, der, readings, simulation, sse, teams, sensors
from app.api.v1.endpoints import energy, reports, audit, hes_mirror, mdms_mirror
from app.api.v1.endpoints import hes_proxy, mdms_proxy, health
# Phase-b (017) — admin RBAC, metrology admin, reliability, notifications.
from app.api.v1.endpoints import admin_users, admin_metrology, reliability, notifications
# Spec 018 no-mock-data closure — metrology + device search endpoints.
from app.api.v1.endpoints import consumption as consumption_ep
from app.api.v1.endpoints import devices as devices_ep
# Spec 018 W2B — outbound command / FOTA / DER bulk-import
from app.api.v1.endpoints import der_bulk, fota
# Spec 018 W3 — GIS topology layers + NTL dashboard (GIS/NTL/energy-balance track)
from app.api.v1.endpoints import gis, ntl
from app.api.v1.endpoints import system_management as system_management_ep
# Spec 018 W3 — DER telemetry read + feeder aggregation + scenario proxy + reverse-flow
from app.api.v1.endpoints import der_telemetry as der_telemetry_ep
# W5 — consumer + type-catalog, inverter equipment + telemetry, DER metrology.
from app.api.v1.endpoints import (
    der_consumer as der_consumer_ep,
    der_inverter as der_inverter_ep,
    der_metrology as der_metrology_ep,
)
from app.api.v1.endpoints import simulation_proxy, reverse_flow
# Spec 018 W3 — outage management + outage GIS overlay
from app.api.v1.endpoints import outage as outage_ep
from app.api.v1.endpoints import gis_outages
# Spec 018 W4 — virtual object groups + alarm rules track
from app.api.v1.endpoints import groups as groups_ep
from app.api.v1.endpoints import alarm_rules as alarm_rules_ep
# Spec 018 W4.T6/T7 — AppBuilder CRUD + algorithm sandbox + scheduled reports.
from app.api.v1.endpoints import app_builder as app_builder_ep
from app.api.v1.endpoints import reports_egsm as reports_egsm_ep
from app.api.v1.endpoints import scheduled_reports as scheduled_reports_ep

api_router = APIRouter()

api_router.include_router(auth.router,         prefix="/auth",       tags=["auth"])
# Phase-b RBAC admin routes (017).
api_router.include_router(admin_users.router,     prefix="/admin/users",     tags=["admin-users"])
api_router.include_router(admin_metrology.router, prefix="/admin/metrology", tags=["admin-metrology"])
api_router.include_router(meters.router,       prefix="/meters",     tags=["meters"])
api_router.include_router(alarms.router,       prefix="/alarms",     tags=["alarms"])
api_router.include_router(der.router,          prefix="/der",        tags=["der"])
# DER bulk-import from simulator — uses bearer SIMULATOR_API_KEY, not JWT.
api_router.include_router(der_bulk.router,     prefix="/der",        tags=["der-bulk-import"])
api_router.include_router(fota.router,         prefix="/fota",       tags=["fota"])
api_router.include_router(readings.router,     prefix="/readings",   tags=["readings"])
api_router.include_router(simulation.router,   prefix="/simulation", tags=["simulation"])
api_router.include_router(sensors.router,      prefix="/sensors",    tags=["sensors"])
api_router.include_router(sse.router,          prefix="/events",     tags=["sse"])
api_router.include_router(teams.router,        prefix="/teams",      tags=["teams"])
api_router.include_router(energy.router,       prefix="/energy",     tags=["energy"])
api_router.include_router(reports.router,      prefix="/reports",    tags=["reports"])
api_router.include_router(audit.router,        prefix="/audit",      tags=["audit"])
api_router.include_router(health.router,       prefix="",            tags=["health"])

# Legacy DB-backed mirrors (spec 018 Wave 1 transition: kept under new prefix while
# the frontend migrates to the SSOT proxy). Will be deleted at end of Wave 2.
api_router.include_router(hes_mirror.router,   prefix="/hes-mirror",  tags=["hes-mirror"])
api_router.include_router(mdms_mirror.router,  prefix="/mdms-mirror", tags=["mdms-mirror"])

# SSOT proxies — /api/v1/hes/* + /api/v1/mdms/* pass straight through to HES /
# MDMS upstreams with trace-context propagation and feature-flag gating.
api_router.include_router(hes_proxy.router,    prefix="/hes",         tags=["hes-proxy"])
api_router.include_router(mdms_proxy.router,   prefix="/mdms",        tags=["mdms-proxy"])

# Spec 018 W3 — GIS GeoJSON layers + NTL dashboard endpoints.
api_router.include_router(gis.router,          prefix="/gis",         tags=["gis"])
api_router.include_router(ntl.router,          prefix="/ntl",         tags=["ntl"])

# SMOC-12 — system management registry + performance pages.
api_router.include_router(
    system_management_ep.router,
    prefix="/system-management",
    tags=["system-management"],
)

# Spec 018 W3 DER/Scenario track — telemetry reads under /der, scenario proxy
# under /simulation-proxy to avoid clashing with the local /simulation engine.
api_router.include_router(der_telemetry_ep.router, prefix="/der",              tags=["der-telemetry"])
# W5 — consumer + type-catalog, inverter equipment + telemetry, DER metrology.
api_router.include_router(der_consumer_ep.router,   prefix="/der",              tags=["der-consumer"])
api_router.include_router(der_inverter_ep.router,   prefix="/der",              tags=["der-inverter"])
api_router.include_router(der_metrology_ep.router,  prefix="/der",              tags=["der-metrology"])
api_router.include_router(simulation_proxy.router, prefix="/simulation-proxy", tags=["simulation-proxy"])
api_router.include_router(reverse_flow.router,     prefix="/reverse-flow",     tags=["reverse-flow"])

# Spec 018 W3 — outage management (list/detail/acknowledge/dispatch/note, FLISR)
api_router.include_router(outage_ep.router,        prefix="/outages",           tags=["outages"])
# Outage GIS overlay lives in its own module to avoid touching endpoints/gis.py.
# Its route is `/outages` within the /gis prefix (full path: /api/v1/gis/outages).
api_router.include_router(gis_outages.router,      prefix="/gis",               tags=["gis-outages"])

# Spec 018 W4 — virtual object groups + alarm-rule CRUD.
api_router.include_router(groups_ep.router,        prefix="/groups",            tags=["groups"])
api_router.include_router(alarm_rules_ep.router,   prefix="/alarm-rules",       tags=["alarm-rules"])


# Spec 018 W4.T6 — AppBuilder CRUD (/apps, /app-rules, /algorithms). Each
# sub-router already declares its own prefix so no extra prefix here.
api_router.include_router(app_builder_ep.apps_router)
api_router.include_router(app_builder_ep.rules_router)
api_router.include_router(app_builder_ep.algos_router)
api_router.include_router(app_builder_ep.widget_sources_router)

# Spec 018 W4.T9 — MDMS EGSM reports proxy under /api/v1/reports/egsm/*.
# Kept distinct from the legacy /reports router which serves local EMS reports.
api_router.include_router(reports_egsm_ep.router,  prefix="/reports",           tags=["reports-egsm"])

# Spec 018 W4.T10 — scheduled report CRUD + run-now.
api_router.include_router(scheduled_reports_ep.router, prefix="/reports/scheduled", tags=["reports-scheduled"])

# Spec 018 W4.T11 — saved dashboard layouts.
from app.api.v1.endpoints import dashboards as dashboards_ep  # noqa: E402
api_router.include_router(dashboards_ep.router,    prefix="/dashboards",         tags=["dashboards"])

# Spec 018 W4.T14 — Data Accuracy console.
from app.api.v1.endpoints import data_accuracy as data_accuracy_ep  # noqa: E402
api_router.include_router(data_accuracy_ep.router, prefix="/data-accuracy",      tags=["data-accuracy"])

# Phase-b (017) — SAIDI/SAIFI reliability metrics + notification channels.
# Note: outages are already handled by outage_ep above (eskom_dev's richer
# /outages router including FLISR/dispatch/note). 017's outages.py is redundant
# and intentionally not mounted to avoid route collisions on GET /outages.
api_router.include_router(reliability.router,    prefix="/reliability",   tags=["reliability"])
api_router.include_router(notifications.router,  prefix="/notifications", tags=["notifications"])

# Spec 018 no-mock-data closure — MDMS-backed consumption aggregates + unified
# device / consumer / DTR / feeder search. Each endpoint returns a
# {ok, data, source, as_of} envelope with source ∈ {mdms, ems-local, partial}.
api_router.include_router(consumption_ep.router,   prefix="/consumption",        tags=["consumption"])
api_router.include_router(devices_ep.router,       prefix="/devices",            tags=["devices"])

# Alert Management (2026-04-21) — MDMS CIS consumers + local site-type tags +
# default-groups seeder. Late-imported to mirror the dashboards / data-accuracy
# pattern above so the top-level import block stays stable.
from app.api.v1.endpoints import cis_consumers as cis_consumers_ep  # noqa: E402
from app.api.v1.endpoints import alert_defaults as alert_defaults_ep  # noqa: E402
api_router.include_router(cis_consumers_ep.router, prefix="/cis",                tags=["cis-consumers"])
api_router.include_router(alert_defaults_ep.router, prefix="/alert-mgmt",        tags=["alert-mgmt"])

# W5b — Energy Saving Analysis (org hierarchy + appliance shift scenarios).
from app.api.v1.endpoints import energy_savings as energy_savings_ep  # noqa: E402
api_router.include_router(energy_savings_ep.router, prefix="/energy-savings",    tags=["energy-savings"])

# SLA KPIs (2026-04-21) — MDMS validation_rules.data_availability → month-to-date
# SLA per metrology profile (Billing / Daily Load / Blockload) plus device counts.
from app.api.v1.endpoints import sla as sla_ep  # noqa: E402
api_router.include_router(sla_ep.router, prefix="/sla", tags=["sla"])

# MDMS-sourced dashboard widgets (2026-04-21) — KPI row, load profile and
# alarm feed all come straight from MDMS (db_cis + validation_rules + gp_hes).
from app.api.v1.endpoints import mdms_dashboard as mdms_dashboard_ep  # noqa: E402
api_router.include_router(mdms_dashboard_ep.router, prefix="/mdms-dashboard", tags=["mdms-dashboard"])

# Theft Analysis (2026-04-21) — MDMS-sourced NTL scoring per meter.
from app.api.v1.endpoints import theft as theft_ep  # noqa: E402
api_router.include_router(theft_ep.router, prefix="/theft", tags=["theft"])
