# HES & MDMS Integration with SMOC — Proposed Integration Architecture

**Tender Reference:** E2136DXLP
**Document Purpose:** Proposed integration approach for SMOC team to integrate their platform with our HES and MDMS systems
**Date:** 2026-03-25
**Status:** Draft — Pending SMOC Team Review and Alignment

---

## 1. Overview

The Smart Metering Operations Centre (SMOC) requires real-time and near-real-time data from two upstream systems:

- **HES (Head End System)** — owns the meter communication layer: meter registry, raw readings, events/alarms, command execution, and network health.
- **MDMS (Meter Data Management System)** — owns the data processing layer: VEE-processed interval data, billing determinants, prepaid engine, analytics, consumer/premise enrichment, and reporting.

SMOC is the **operational dashboard and command centre** that aggregates and presents data from both systems, and may also initiate commands back through HES/MDMS.

This document proposes a standard, industry-aligned integration architecture. It is intended as a starting point for alignment between the SMOC team and the HES/MDMS team before demo integration begins.

---

## 2. Integration Architecture — Proposed Model

```
┌──────────────────────────────────────────────────────────────────┐
│                            SMOC                                  │
│  (Dashboard · GIS · DER Simulation · A/V Control · Analytics)   │
└────────────┬──────────────────────────────────┬─────────────────┘
             │  Northbound APIs / Event Streams  │
    ┌────────▼────────┐                ┌─────────▼────────┐
    │      HES        │                │      MDMS        │
    │ (Meter Comms /  │◄──────────────►│ (Data Processing │
    │  Command Exec)  │  Internal Sync │  / Analytics)    │
    └────────┬────────┘                └─────────┬────────┘
             │                                   │
         Meters / DCUs                    Billing / CIS
```

### Integration Layers

| Layer | Direction | Technology | Purpose |
|-------|-----------|------------|---------|
| **Real-Time Events** | HES → SMOC | Apache Kafka  | Alarms, tamper, outage, power quality events |
| **REST APIs (Query)** | SMOC → HES/MDMS | HTTPS REST (JSON) | On-demand data fetch: readings, device status, meter info |
| **REST APIs (Command)** | SMOC → HES/MDMS | HTTPS REST (JSON) | RC/DC, FOTA, tariff push, load limit commands |
| **Batch/Scheduled Data** | MDMS → SMOC | REST or SFTP | Daily billing determinants, VEE reports, analytics exports |

---

## 3. HES Northbound Interface — What HES Provides to SMOC

### 3.1 REST API Endpoints (HES → SMOC, query)

| API | Method | Description |
|-----|--------|-------------|
| `/api/v1/meters` | GET | Meter inventory — serial, type, communication tech, install status, geo-coordinates |
| `/api/v1/meters/{serial}/status` | GET | Current meter status: online/offline, last seen, relay state, battery health |
| `/api/v1/meters/{serial}/readings/latest` | GET | Latest interval reading (kWh import/export, demand, voltage, current) |
| `/api/v1/meters/{serial}/events` | GET | Event log — tamper, outage, power quality, ACD triggers |
| `/api/v1/meters/{serial}/commands/history` | GET | Command history — RC/DC, FOTA, tariff, time sync |
| `/api/v1/network/health` | GET | Network KPIs — active meters, offline count, comm success rate |
| `/api/v1/dcus` | GET | Data Concentrator Unit inventory and status |
| `/api/v1/alarms/active` | GET | All currently active alarms across the meter estate |

### 3.2 Event Stream (HES → SMOC, push)

HES publishes the following events to a **Kafka topic** (or MQTT broker if Kafka is not supported by SMOC):

| Topic / Subject | Event Types | Payload Format |
|-----------------|-------------|----------------|
| `hes.meter.events` | Tamper detected, power outage, power restore, cover open | JSON |
| `hes.meter.alarms` | Over/undervoltage, over-current, battery low, communication loss | JSON |
| `hes.meter.status` | Online/offline transitions, relay state change | JSON |
| `hes.network.health` | Periodic network KPI snapshot (configurable interval) | JSON |

### 3.3 Command API (SMOC → HES, southbound)

If SMOC initiates commands directly via HES:

| API | Method | Description |
|-----|--------|-------------|
| `/api/v1/meters/{serial}/commands/connect` | POST | Remote Connect |
| `/api/v1/meters/{serial}/commands/disconnect` | POST | Remote Disconnect |
| `/api/v1/meters/{serial}/commands/fota` | POST | Initiate firmware upgrade |
| `/api/v1/meters/{serial}/commands/timesync` | POST | Synchronise meter clock |
| `/api/v1/meters/{serial}/commands/read` | POST | On-demand meter read |

---

## 4. MDMS Northbound Interface — What MDMS Provides to SMOC

### 4.1 REST API Endpoints (MDMS → SMOC, query)

| API | Method | Description |
|-----|--------|-------------|
| `/api/v1/readings/interval/{serial}` | GET | VEE-processed interval data (15-min / 30-min / hourly) |
| `/api/v1/readings/daily/{serial}` | GET | Daily consumption totals (import, export, net) |
| `/api/v1/billing/determinants/{serial}` | GET | Monthly billing determinants (TOU, peak/off-peak, demand) |
| `/api/v1/consumers/{account}` | GET | Consumer/premise data (name, address, tariff class, account type) |
| `/api/v1/prepaid/{serial}/balance` | GET | Current prepaid credit balance and ACD status |
| `/api/v1/powerquality/{serial}` | GET | Power quality data: voltage deviation, THD, flicker, NRS 048 events |
| `/api/v1/analytics/noncommunicating` | GET | List of non-communicating meters with last known geo-location |
| `/api/v1/analytics/outages` | GET | Outage events with affected consumers, duration, geo-coordinates |
| `/api/v1/vee/exceptions` | GET | VEE exception list — failed validation, estimated readings |
| `/api/v1/reports/{report_type}` | GET | On-demand report generation (EGSM, TOU, power quality, etc.) | 



### 4.2 Command API (SMOC → MDMS, southbound)

| API | Method | Description |
|-----|--------|-------------|
| `/api/v1/consumers/{account}/tokens` | POST | Issue prepaid token / credit top-up |
| `/api/v1/meters/{serial}/tariff` | POST | Update tariff configuration (TOU, CPP) |
| `/api/v1/meters/{serial}/loadlimit` | POST | Set or update load limit threshold |
| `/api/v1/meters/{serial}/paymentmode` | POST | Switch between prepaid / credit mode |

---

## 5. Security and Authentication

All integration endpoints use the following security model:

| Layer | Mechanism |
|-------|-----------|
| **Authentication** | Congnito Token |
| **Event stream auth** | SASL/SSL for Kafka; username/password + TLS for MQTT |
| **Network** | Private network segment or VPN between SMOC, HES, and MDMS for demo environment |

> For the demo environment, if a shared identity provider is not feasible, API keys with IP whitelisting are an acceptable fallback for the demo only.

---

## 6. Data Format Standard

All APIs use **JSON over HTTPS**. A standard envelope format is proposed:

```json
{
    "success": true,
    "data": {
        "records": [],
        "count": 10,
        "cursor": {
            "after": "WzU0MTA0NTI0ODk3XQ==",
            "before": null
        }
    },
    "error": null,
    "requestID": "da44ae61-71d8-4b23-ada7-e72891d2441f"
}
```

Event stream messages follow the same envelope wrapped in a Kafka message or MQTT payload.

---

## 7. GIS and Topology Data

For SMOC map views (outage pinpointing, non-communicating meters, feeder-level drill-down):

- HES provides **meter geo-coordinates** (latitude, longitude) and **DCU-to-meter association** via the `/api/v1/meters` endpoint.
- MDMS provides **outage event data** with affected meter lists and coordinates via `/api/v1/analytics/outages`.
- If SMOC's GIS platform requires a **network topology feed** (feeder → transformer → meter hierarchy), HES/MDMS can supply this as a structured JSON hierarchy or as a GeoJSON feature collection.
- The GIS platform used by SMOC needs to be confirmed (ArcGIS, QGIS, Leaflet, Google Maps, etc.) to determine the exact format required.

---

## 8. Demo Environment Integration Plan

For the 20–21 April 2026 demonstration, the following integration sequence is proposed:

| Day | Activity |
|-----|----------|
| **T-3 weeks (by 1 Apr)** | API specifications exchanged and agreed; sandbox credentials shared |
| **T-2 weeks (by 7 Apr)** | SMOC team connects to HES/MDMS sandbox; first end-to-end data flow test |
| **T-1 week (by 14 Apr)** | Integration dry run — all SMOC views populated with HES/MDMS data |
| **20 Apr (Setup Day)** | Full system setup at Megawatt Park; integration verified on-site hardware |
| **21 Apr (Demo Day)** | Live demonstration — all SMOC views driven by live HES/MDMS data |

---
**Note** - Detailed API Documention will be shared subsequently 