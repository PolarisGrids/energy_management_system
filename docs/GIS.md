# Polaris EMS — GIS Module (Target Architecture)

> Current state is **15% of production utility-GIS feature set** (see `docs/GAPS.md §3`). This document is the target design — everything below is either partially built or to-be-built.

## 1. Goals

A production-grade GIS module for SMOC must:

1. Render the full electrical topology (substation → PSS → feeder → DTR → pole → meter → service line) on an interactive map, at any zoom.
2. Overlay **live operational state** (alarms, outages, load, voltage, DER output, sensor status) without page refresh.
3. Support **control-room workflows**: outage triage, FLISR, dispatch, asset inspection, geofenced monitoring.
4. Be usable on a 4K video wall **and** a field tablet / mobile (responsive, offline tile cache).
5. Integrate with HES (device status), MDMS (readings), WFM (crew location), and Notifications (alerts).

## 2. Architecture

```
┌──────────────────────────┐      ┌──────────────────────────┐
│  MapLibre GL JS frontend │◄────►│  FastAPI /gis/* endpoints │
│  - vector + raster tiles │      │  - GeoJSON, MVT           │
│  - WebSocket/SSE live    │      │  - PostGIS spatial queries│
│  - Deck.gl for heatmaps  │      │  - Redis cache (10 min)   │
└────────────┬─────────────┘      └────────────┬──────────────┘
             │                                 │
             ▼                                 ▼
    ┌────────────────┐               ┌──────────────────┐
    │ TileServer GL  │               │ PostgreSQL +     │
    │ (MVT cache)    │               │ PostGIS 3.4      │
    └────────────────┘               └──────────────────┘
```

### 2.1 Backend

- **PostGIS** extension enabled on the main DB. Add `geometry(Point, 4326)` / `geometry(LineString, 4326)` columns to `feeders`, `service_lines`, `transformers`, `poles`, `meters`, `der_assets`, `network_events`, `outage_areas`, `zones`.
- **Spatial indexes**: `CREATE INDEX ... USING GIST (geom)` on every geometry column.
- **GeoJSON endpoints** under `/api/v1/gis/`:
  - `GET /gis/layers/{layer}?bbox=&zoom=` — FeatureCollection (meters, alarms, der, outages, feeders, transformers, poles, zones, crews)
  - `GET /gis/tiles/{layer}/{z}/{x}/{y}.mvt` — Mapbox Vector Tile served by TileServer GL or proxied from `ST_AsMVT`
  - `GET /gis/search?q=<serial|address|consumer|feeder>` — reverse geocode + asset search
  - `POST /gis/zones` — CRUD geofenced polygons (used for alarm filters, reports)
  - `POST /gis/annotations` — operator annotations (damage markers, inspection points)
  - `POST /gis/export?format=kml|geojson|png&bbox=` — snapshot export
- **Redis** 10-minute TTL cache for topology and outage polygons.
- **SSE/WebSocket fan-out**: push `meter.status`, `alarm.triggered`, `outage.area.changed`, `der.output`, `crew.position` deltas so the map recolours markers without re-fetching layers.

### 2.2 Frontend

- Migrate from **Leaflet → MapLibre GL JS** for:
  - Native vector-tile rendering (millions of assets at 60fps)
  - Built-in clustering, data-driven styling, 3D terrain
  - WebGL-accelerated heatmaps (or deck.gl overlay)
- Component tree under `src/components/map/`:
  - `MapCanvas` (root, holds map instance and style)
  - `BaseLayerSwitcher` (street / satellite / terrain / dark)
  - `LayerPanel` (topology, assets, telemetry, overlays, crews)
  - `Legend`, `Scale`, `Compass`, `Geolocate`
  - `DrawTools` (geofence, measurement, annotations)
  - `TimeSlider` (replay mode)
  - `SearchBox` (geocode + asset)
  - `AssetInspector` (right-drawer on feature click)
  - `MiniMap`, `Overview`, `Print`, `ExportMenu`
- Zustand store slice `useGisStore` subscribes to SSE and mutates feature properties in place.
- Asset detail drawer ties to existing API for readings / alarms / commands.

## 3. Feature List

Grouped by operator workflow. ✅ already present, 🟡 partial, ⬜ to build.

### 3.1 Base maps & navigation
- ⬜ Street base layer (OSM / Mapbox)
- ⬜ Satellite base layer
- ⬜ Terrain / topo layer
- ✅ Dark / night-mode base layer (CartoDB)
- ⬜ Base-layer switcher control
- ⬜ User-pref persistence of last viewport & layer selection per-user
- ✅ Pinch/touch zoom (Leaflet default)
- ⬜ Keyboard shortcuts (pan/zoom/search)
- ⬜ Scale bar
- ⬜ Compass / bearing indicator
- ⬜ Locate-me (`navigator.geolocation`)

### 3.2 Network topology
- ⬜ Substation symbols with capacity bar
- ⬜ PSS (Primary Sub-Substation) symbols
- ⬜ MV feeder polylines, coloured by loading %
- ⬜ DTR (distribution transformer) markers with load / temperature halo
- ⬜ Pole markers (optional, zoom ≥18 only)
- ✅ Meter markers (clustered at zoom <14, individual after)
- ⬜ LT service-line polylines (meter ↔ DTR)
- ⬜ Upstream / downstream trace on click (highlight path to source)
- ⬜ Switch / recloser / breaker state symbology (open / closed / auto)
- ⬜ Hierarchical drill-down: click substation → feeders → DTRs → meters

### 3.3 Assets
- ✅ DER markers (PV / BESS / EV / microgrid) with type-colour
- 🟡 DER status ring (online / curtailed / charging / islanded) — data exists, not rendered
- ⬜ BESS state-of-charge halo
- ⬜ EV charger port-status mini-gauge
- ⬜ Synchronous-condenser / generator symbol
- ⬜ Capacitor bank / voltage regulator symbols

### 3.4 Operational overlays
- ✅ Active-alarm pulse animation
- 🟡 Alarm cluster with severity breakdown (partial)
- ⬜ **Outage area polygons** with affected-customer count
- ⬜ FLISR (Fault Location, Isolation, Service Restoration) animated sequence
- ⬜ "Service restoration" before/after overlay
- ⬜ Load-flow heatmap on feeder polylines (kW / capacity)
- ⬜ Voltage-profile colouring (p.u.) on lines
- ⬜ NTL-hotspot heatmap from `ntl_suspects`
- ⬜ Consumption-density heatmap (deck.gl HeatmapLayer)
- ⬜ PQ (power-quality) hotspots from `power_quality_zones`

### 3.5 Field & crew
- ⬜ Live crew position pins (WFM integration)
- ⬜ Crew breadcrumb trail (last 4h)
- ⬜ Route planning (OSRM / GraphHopper) from nearest crew to asset
- ⬜ Dispatch action from map (create work order from a clicked alarm)
- ⬜ Asset inspection photos pinned to location

### 3.6 Analysis & tools
- ⬜ Measurement tool (distance / area)
- ⬜ Geofence drawing (polygon, rectangle, circle)
- ⬜ Zone CRUD with alarm-subscription
- ⬜ Buffer analysis (assets within X m of selected feature)
- ⬜ Isochrone (5/10/15 min travel time from substation)
- ⬜ Time-slider — replay alarms/outages over last 24h / 7d / 30d
- ⬜ Snapshot compare (before/after toggle)

### 3.7 Search & selection
- ⬜ Global search (meter serial / consumer name / account / feeder / address)
- ⬜ Geocoding (Nominatim / Mapbox)
- ⬜ Reverse geocoding on right-click
- ⬜ Multi-select (shift+click, lasso, box)
- ⬜ Bulk-command panel (disconnect selected, send read, schedule)

### 3.8 Export & reporting
- ⬜ Export current view to PNG (screenshot)
- ⬜ Export visible features to GeoJSON
- ⬜ Export to KML
- ⬜ Print / PDF report with legend + metadata
- ⬜ Share deep link (encodes bbox, layers, filters)

### 3.9 Interactions
- ✅ Right-click context menu
- ⬜ Asset-inspector right drawer on click
- ⬜ Hover tooltip (lightweight metrics)
- ⬜ Keyboard nav (tab through visible features)
- ⬜ Accessibility (ARIA roles on custom controls)

### 3.10 Performance & ops
- ⬜ Server-side MVT tile cache (TileServer GL / pg_tileserv)
- ⬜ Client IndexedDB tile cache for offline control-room large screens
- ⬜ WebGL renderer (MapLibre) for >50k visible features
- ⬜ Incremental SSE diffs (don't re-fetch layers on each update)
- ⬜ Debounced pan/zoom to avoid tile thrash

### 3.11 3D / advanced
- ⬜ 3D terrain toggle (MapLibre)
- ⬜ 3D substation buildings (extrusions)
- ⬜ Underground cable view (2.5D transparent plane)
- ⬜ Animated energy-flow particles along MV feeders

## 4. Data model additions

```sql
ALTER TABLE feeders ADD COLUMN geom geometry(LineString, 4326);
CREATE INDEX ix_feeders_geom ON feeders USING GIST (geom);

CREATE TABLE service_lines (
  id SERIAL PRIMARY KEY,
  meter_serial VARCHAR(50) REFERENCES meters(serial),
  transformer_id INTEGER REFERENCES transformers(id),
  geom geometry(LineString, 4326) NOT NULL,
  length_m NUMERIC,
  cable_type VARCHAR(50)
);
CREATE INDEX ix_service_lines_geom ON service_lines USING GIST (geom);

CREATE TABLE poles (
  id SERIAL PRIMARY KEY,
  feeder_id INTEGER REFERENCES feeders(id),
  geom geometry(Point, 4326) NOT NULL,
  material VARCHAR(20),
  height_m NUMERIC
);

CREATE TABLE outage_areas (
  id SERIAL PRIMARY KEY,
  event_id INTEGER REFERENCES network_events(id),
  geom geometry(Polygon, 4326) NOT NULL,
  affected_customers INTEGER,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ
);

CREATE TABLE zones (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200),
  zone_type VARCHAR(30),
  created_by VARCHAR(100),
  geom geometry(Polygon, 4326) NOT NULL,
  rules JSONB
);

CREATE TABLE crew_positions (
  id SERIAL PRIMARY KEY,
  crew_id VARCHAR(50),
  geom geometry(Point, 4326),
  heading_deg NUMERIC,
  reported_at TIMESTAMPTZ
);
CREATE INDEX ix_crew_positions_time ON crew_positions (crew_id, reported_at DESC);
```

## 5. Phased roadmap

| Phase | Weeks | Scope |
|---|---|---|
| **P0 Restore** | 1 | Fix `meter.py` / schemas / `App.jsx`; re-register `/map` route; commit Alembic baseline. |
| **P1 PostGIS foundation** | 2–3 | Add `postgis` extension, geometry columns, GeoJSON endpoints, seeded topology. |
| **P2 MapLibre migration** | 4–6 | Swap Leaflet → MapLibre; base-layer switcher; feeder polylines; drill-down. |
| **P3 Operational overlays** | 7–9 | Outage polygons, FLISR, load-flow heatmap, voltage profile, NTL hotspots. |
| **P4 Tools & export** | 10–11 | Draw, geofence, measurement, time-slider, PNG/KML/GeoJSON export, print. |
| **P5 Field & WFM** | 12–14 | Crew pins, routing, dispatch from map, inspection photos. |
| **P6 Scale & offline** | 15–17 | MVT tile server, IndexedDB offline cache, 4K video-wall profile. |
| **P7 3D (optional)** | 18+ | Terrain, building extrusions, animated energy-flow. |

## 6. Dependencies unlocked by this module

- **WFM** (work-order dispatch from the map) — requires `wfm_client.py` + `crew_positions` table
- **Outage management** — requires `outage_areas` polygons + event-driven SSE push
- **Mobile field app** — needs offline tile cache + compact layer profile
- **Public outage portal** — can reuse `/gis/layers/outages` as a sanitized public feed
