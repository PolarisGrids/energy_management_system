import { useState, useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Polyline,
  Popup,
  LayerGroup,
  Rectangle,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { ChevronRight } from 'lucide-react'
import { alarmsAPI, metersAPI, derAPI, gisAPI, ntlAPI, outagesAPI, hesAPI } from '@/services/api'
import LayerSwitcher from '@/components/map/LayerSwitcher'
import ContextMenu from '@/components/map/ContextMenu'

// ── Colour tables ─────────────────────────────────────────────────────────────

const STATUS_COLOR = {
  online:       '#02C9A8',
  offline:      '#6B7280',
  tamper:       '#E94B4B',
  disconnected: '#F97316',
}

const DER_COLOR = {
  pv:          '#F59E0B',
  bess:        '#56CCF2',
  ev_charger:  '#02C9A8',
  microgrid:   '#ABC7FF',
}

const FEEDER_LOADING_COLOR = (pct) =>
  pct == null ? '#ABC7FF' : pct >= 80 ? '#E94B4B' : pct >= 60 ? '#F59E0B' : '#02C9A8'

// ── Map helpers ──────────────────────────────────────────────────────────────

function ZoomTracker({ onZoomChange }) {
  const map = useMapEvents({ zoomend: () => onZoomChange(map.getZoom()) })
  return null
}

function BoundsTracker({ onBoundsChange }) {
  const map = useMapEvents({
    moveend: () => {
      const b = map.getBounds()
      onBoundsChange([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(','))
    },
  })
  return null
}

function FitBounds({ points }) {
  const map = useMap()
  useEffect(() => {
    if (points.length >= 2) {
      const lats = points.map(p => p[0])
      const lons = points.map(p => p[1])
      map.fitBounds([
        [Math.min(...lats), Math.min(...lons)],
        [Math.max(...lats), Math.max(...lons)],
      ], { padding: [40, 40] })
    }
  }, [points.length])
  return null
}

// ── Zoom Breadcrumb ──────────────────────────────────────────────────────────

function ZoomBreadcrumb({ zoom }) {
  const levels = [
    { min: 0,  max: 9,  label: 'Regional',           color: '#ABC7FF' },
    { min: 10, max: 13, label: 'Feeder / DTR',       color: '#56CCF2' },
    { min: 14, max: 22, label: 'Meter',              color: '#02C9A8' },
  ]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
      {levels.map((level, i) => {
        const active = zoom >= level.min && zoom <= level.max
        return (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {i > 0 && <ChevronRight size={12} style={{ color: 'rgba(255,255,255,0.2)' }} />}
            <span style={{
              padding: '3px 8px', borderRadius: 6, fontWeight: 700,
              background: active ? `${level.color}20` : 'transparent',
              color: active ? level.color : 'rgba(255,255,255,0.25)',
              border: active ? `1px solid ${level.color}40` : '1px solid transparent',
            }}>{level.label}</span>
          </span>
        )
      })}
      <span style={{ marginLeft: 8, color: 'rgba(255,255,255,0.3)', fontSize: 11 }}>Zoom: {zoom}</span>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function GISMap() {
  const navigate = useNavigate()
  const [zoom, setZoom] = useState(6)
  const [bbox, setBbox] = useState(null)

  // Layer visibility flags — default set reflects the US-22 "start broad" view.
  const [layers, setLayers] = useState({
    feeder: true,
    dtr: true,
    pole: false,
    meter: true,
    outage: false,
    alarm_heat: false,
    ntl_suspects: false,
  })

  // Data
  const [feederFC, setFeederFC] = useState({ features: [] })
  const [dtrFC, setDtrFC] = useState({ features: [] })
  const [meterFC, setMeterFC] = useState({ features: [] })
  const [heatmap, setHeatmap] = useState({ cells: [] })
  const [ntlSuspectsFC, setNtlSuspectsFC] = useState({ features: [] })
  const [outageOverlay, setOutageOverlay] = useState({ features: [] })
  const [ders, setDers] = useState([])
  const [loading, setLoading] = useState(true)

  // Context menu state
  const [contextMenu, setContextMenu] = useState(null)
  const [selectedAsset, setSelectedAsset] = useState(null)

  const safeGet = async (fn) => {
    try { return await fn() } catch (e) { return null }
  }

  // Initial load — pull every layer we might show. Page stays small (~1–5k
  // features); the backend clips heavy layers by bbox on subsequent refetches.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const [feeder, dtr, meter, dersResp] = await Promise.all([
        safeGet(() => gisAPI.layer('feeder')),
        safeGet(() => gisAPI.layer('dtr')),
        safeGet(() => gisAPI.layer('meter')),
        safeGet(() => derAPI.list()),
      ])
      if (cancelled) return
      setFeederFC(feeder?.data ?? { features: [] })
      setDtrFC(dtr?.data ?? { features: [] })
      setMeterFC(meter?.data ?? { features: [] })
      setDers(dersResp?.data ?? [])
      setLoading(false)
    })()
    return () => { cancelled = true }
  }, [])

  // Alarm heatmap — only fetched when the layer is toggled on.
  useEffect(() => {
    if (!layers.alarm_heat) return
    safeGet(() => gisAPI.heatmapAlarms(bbox)).then(r => r && setHeatmap(r.data))
  }, [layers.alarm_heat, bbox])

  // NTL suspects overlay — lazy.
  useEffect(() => {
    if (!layers.ntl_suspects) return
    safeGet(() => ntlAPI.suspectsGeoJson(bbox)).then(r => r && setNtlSuspectsFC(r.data))
  }, [layers.ntl_suspects, bbox])

  // Outage overlay (Agent H's `/api/v1/gis/outages`) — lazy.
  useEffect(() => {
    if (!layers.outage) return
    safeGet(() => outagesAPI.gisOverlay({ bbox })).then(r => r && setOutageOverlay(r.data ?? { features: [] }))
  }, [layers.outage, bbox])

  // Click-outside closes the context menu.
  useEffect(() => {
    const close = () => setContextMenu(null)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [])

  // ── Context menu handlers ──
  const handleContextMenu = useCallback((e, asset) => {
    e.originalEvent?.preventDefault?.()
    const { clientX: x, clientY: y } = e.originalEvent || e
    setContextMenu({ x, y })
    setSelectedAsset(asset)
  }, [])

  const handleContextAction = useCallback(async (action, asset) => {
    switch (action) {
      case 'regional_report':
        navigate('/reports')
        break
      case 'alarm_heatmap':
        setLayers(l => ({ ...l, alarm_heat: true }))
        break
      case 'dtr_downstream':
        navigate(`/meters?transformer_id=${asset.id}`)
        break
      case 'dtr_load_profile':
        navigate(`/energy?dtr=${asset.id}`)
        break
      case 'dtr_energy_balance':
        navigate(`/ntl?tab=energy_balance&dtr=${asset.id}`)
        break
      case 'feeder_load':
      case 'feeder_report':
        navigate('/energy')
        break
      case 'meter_read':
        // Trigger a meter read via HES proxy; UX: log the command dispatch.
        if (asset.serial) {
          await safeGet(() => hesAPI.postCommand({ type: 'READ_REGISTER', meter_serial: asset.serial }))
        }
        break
      case 'meter_disconnect':
        if (asset.serial && window.confirm(`Disconnect ${asset.serial}?`)) {
          await safeGet(() => metersAPI.disconnect(asset.serial))
        }
        break
      case 'meter_consumer':
        if (asset.account_number) navigate(`/mdms?account=${asset.account_number}`)
        break
      case 'meter_command':
        navigate(`/hes?meter=${asset.serial || ''}`)
        break
      case 'details':
      default:
        navigate('/')
    }
  }, [navigate])

  const toggleLayer = useCallback((key) => setLayers(l => ({ ...l, [key]: !l[key] })), [])

  // ── Derived map sizing ──
  const allCoords = useMemo(() => {
    const pts = []
    meterFC.features?.forEach(f => {
      const [lon, lat] = f.geometry?.coordinates ?? []
      if (lat != null && lon != null) pts.push([lat, lon])
    })
    dtrFC.features?.forEach(f => {
      const [lon, lat] = f.geometry?.coordinates ?? []
      if (lat != null && lon != null) pts.push([lat, lon])
    })
    return pts
  }, [meterFC, dtrFC])

  const meterCount = meterFC.features?.length ?? 0
  const dtrCount = dtrFC.features?.length ?? 0
  const feederCount = feederFC.features?.length ?? 0
  const alarmCellCount = heatmap.cells?.length ?? 0
  const suspectCount = ntlSuspectsFC.features?.length ?? 0

  return (
    <div className="flex flex-col gap-3 h-full animate-slide-up" data-testid="gis-map-page">
      <LayerSwitcher layers={layers} onToggle={toggleLayer} />

      <div className="glass-card overflow-hidden flex-1" style={{ minHeight: 500, position: 'relative' }}>
        {loading ? (
          <div className="flex items-center justify-center h-full text-white/40">Loading map data…</div>
        ) : (
          <MapContainer center={[-29.0, 26.0]} zoom={6} style={{ height: '100%', width: '100%', minHeight: 500 }} zoomControl>
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; OpenStreetMap &copy; CARTO'
            />
            <FitBounds points={allCoords} />
            <ZoomTracker onZoomChange={setZoom} />
            <BoundsTracker onBoundsChange={setBbox} />

            {/* Feeder LineStrings */}
            {layers.feeder && (
              <LayerGroup>
                {feederFC.features.map((f, i) => {
                  const coords = (f.geometry?.coordinates ?? []).map(([lon, lat]) => [lat, lon])
                  if (coords.length < 2) return null
                  const loadingPct = f.properties?.loading_pct
                  const color = FEEDER_LOADING_COLOR(loadingPct)
                  return (
                    <Polyline key={`feeder-${i}`} positions={coords}
                      pathOptions={{ color, weight: 3, opacity: 0.8 }}
                      eventHandlers={{ contextmenu: (e) => handleContextMenu(e, { ...f.properties, type: 'feeder' }) }}>
                      <Popup>
                        <div style={{ fontFamily: 'Satoshi, sans-serif' }}>
                          <b>{f.properties?.name}</b><br />
                          Substation: {f.properties?.substation}<br />
                          Voltage: {f.properties?.voltage_kv} kV<br />
                          Loading: {loadingPct ?? '—'}%
                        </div>
                      </Popup>
                    </Polyline>
                  )
                })}
              </LayerGroup>
            )}

            {/* DTR points */}
            {layers.dtr && (
              <LayerGroup>
                {dtrFC.features.map((f, i) => {
                  const [lon, lat] = f.geometry?.coordinates ?? []
                  if (lat == null || lon == null) return null
                  const pct = f.properties?.loading_pct
                  const color = FEEDER_LOADING_COLOR(pct)
                  return (
                    <CircleMarker key={`dtr-${i}`} center={[lat, lon]} radius={8}
                      pathOptions={{ color, fillColor: color, fillOpacity: 0.7, weight: 2 }}
                      eventHandlers={{ contextmenu: (e) => handleContextMenu(e, { ...f.properties, type: 'dtr' }) }}>
                      <Popup>
                        <div style={{ fontFamily: 'Satoshi, sans-serif' }}>
                          <b>{f.properties?.name}</b><br />
                          Load: {pct ?? '—'}%<br />
                          Capacity: {f.properties?.capacity_kva} kVA
                        </div>
                      </Popup>
                    </CircleMarker>
                  )
                })}
              </LayerGroup>
            )}

            {/* Meter points (individual at zoom >= 14) */}
            {layers.meter && zoom >= 14 && (
              <LayerGroup>
                {meterFC.features.map((f, i) => {
                  const [lon, lat] = f.geometry?.coordinates ?? []
                  if (lat == null || lon == null) return null
                  const p = f.properties || {}
                  const color = STATUS_COLOR[p.status] ?? '#6B7280'
                  return (
                    <CircleMarker key={`m-${i}`} center={[lat, lon]} radius={5}
                      pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: 1 }}
                      eventHandlers={{ contextmenu: (e) => handleContextMenu(e, { ...p, type: 'meter' }) }}>
                      <Popup>
                        <div style={{ fontFamily: 'Satoshi, sans-serif', minWidth: 200 }}>
                          <b>{p.serial}</b><br />
                          {p.customer_name}<br />
                          <span style={{ color }}>● {p.status}</span> · {p.meter_type}<br />
                          <span style={{ fontSize: 11, color: '#999' }}>Right-click for actions</span>
                        </div>
                      </Popup>
                    </CircleMarker>
                  )
                })}
              </LayerGroup>
            )}

            {/* Alarm heatmap — rectangles keyed by grid cell. */}
            {layers.alarm_heat && (
              <LayerGroup>
                {heatmap.cells?.map((c, i) => {
                  const half = (heatmap.grid_deg ?? 0.1) / 2
                  const intensity = Math.min(1, c.count / 20)
                  const color = c.critical > 0 ? '#E94B4B' : c.high > 0 ? '#F97316' : '#F59E0B'
                  return (
                    <Rectangle
                      key={`heat-${i}`}
                      bounds={[[c.lat - half, c.lon - half], [c.lat + half, c.lon + half]]}
                      pathOptions={{
                        color,
                        weight: 0,
                        fillColor: color,
                        fillOpacity: 0.15 + 0.45 * intensity,
                      }}>
                      <Popup>
                        <b>{c.count}</b> alarms in this cell
                        {c.critical > 0 && <><br /><span style={{ color: '#E94B4B' }}>{c.critical} critical</span></>}
                      </Popup>
                    </Rectangle>
                  )
                })}
              </LayerGroup>
            )}

            {/* NTL suspects overlay */}
            {layers.ntl_suspects && (
              <LayerGroup>
                {ntlSuspectsFC.features?.map((f, i) => {
                  const [lon, lat] = f.geometry?.coordinates ?? []
                  if (lat == null || lon == null) return null
                  const p = f.properties || {}
                  return (
                    <CircleMarker key={`ntl-${i}`} center={[lat, lon]} radius={9}
                      pathOptions={{ color: '#F59E0B', fillColor: '#F59E0B', fillOpacity: 0.35, weight: 2, dashArray: '3 3' }}
                      eventHandlers={{ contextmenu: (e) => handleContextMenu(e, { ...p, type: 'meter' }) }}>
                      <Popup>
                        <b>{p.meter_serial}</b><br />
                        NTL score: <b style={{ color: '#F59E0B' }}>{p.score}</b><br />
                        Last event: {p.last_event_type}<br />
                        DTR: {p.dtr_name ?? '—'}
                      </Popup>
                    </CircleMarker>
                  )
                })}
              </LayerGroup>
            )}

            {/* Outage overlay (from Agent H `/api/v1/gis/outages`) */}
            {layers.outage && outageOverlay.features?.map((f, i) => {
              const [lon, lat] = f.geometry?.coordinates ?? []
              if (lat == null || lon == null) return null
              return (
                <CircleMarker key={`out-${i}`} center={[lat, lon]} radius={14}
                  pathOptions={{ color: '#E94B4B', fillColor: '#E94B4B', fillOpacity: 0.2, weight: 3, className: 'alarm-pulse' }}>
                  <Popup>
                    <b style={{ color: '#E94B4B' }}>Outage {f.properties?.id}</b><br />
                    Confidence: {f.properties?.confidence_pct}%<br />
                    Affected meters: {f.properties?.affected_meter_count}
                  </Popup>
                </CircleMarker>
              )
            })}

            {/* DER assets (always-on overlay) */}
            <LayerGroup>
              {ders.map(d => (
                <CircleMarker key={`der-${d.id}`} center={[d.latitude, d.longitude]} radius={zoom >= 14 ? 10 : 8}
                  pathOptions={{
                    color: DER_COLOR[d.asset_type] ?? '#ABC7FF',
                    fillColor: DER_COLOR[d.asset_type] ?? '#ABC7FF',
                    fillOpacity: 0.9, weight: 2,
                  }}
                  eventHandlers={{ contextmenu: (e) => handleContextMenu(e, { ...d, type: 'der' }) }}>
                  <Popup>
                    <b>{d.name}</b><br />
                    Type: {d.asset_type?.replace(/_/g, ' ')}<br />
                    Output: {d.current_output_kw} kW
                  </Popup>
                </CircleMarker>
              ))}
            </LayerGroup>
          </MapContainer>
        )}
      </div>

      <div className="glass-card p-3 flex flex-wrap gap-5 items-center">
        <span className="text-white/40 text-xs font-bold uppercase">Stats</span>
        <span className="text-xs text-white/60" data-testid="gis-feeder-count">{feederCount} feeders</span>
        <span className="text-xs text-white/60" data-testid="gis-dtr-count">{dtrCount} DTRs</span>
        <span className="text-xs text-white/60" data-testid="gis-meter-count">{meterCount} meters</span>
        {layers.alarm_heat && (
          <span className="text-xs text-white/60">{alarmCellCount} alarm cells</span>
        )}
        {layers.ntl_suspects && (
          <span className="text-xs text-white/60">{suspectCount} NTL suspects</span>
        )}
        <div className="ml-auto"><ZoomBreadcrumb zoom={zoom} /></div>
      </div>

      <ContextMenu
        position={contextMenu}
        asset={selectedAsset}
        zoom={zoom}
        onClose={() => setContextMenu(null)}
        onAction={handleContextAction}
      />

      <style>{`
        .alarm-pulse { animation: alarm-ring 2s ease-out infinite; }
        @keyframes alarm-ring { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
      `}</style>
    </div>
  )
}
