// MapCanvas — MapLibre GL JS + react-map-gl (spec 014-gis-postgis US1).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Map, { Source, Layer, NavigationControl, ScaleControl, AttributionControl } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import { BASE_STYLES } from './BaseLayerSwitcher'

const STATUS_TO_COLOR = {
  online: '#02C9A8', offline: '#6B7280', tamper: '#E94B4B',
  disconnected: '#F97316', discovered: '#ABC7FF', provisional: '#56CCF2',
}

const DER_COLOR = { pv: '#F59E0B', bess: '#56CCF2', ev_charger: '#02C9A8', microgrid: '#ABC7FF', wind: '#56CCF2' }

function debounce(fn, ms) {
  let t
  return (...args) => {
    clearTimeout(t)
    t = setTimeout(() => fn(...args), ms)
  }
}

/**
 * Props:
 *   initialView     — { longitude, latitude, zoom }
 *   baseStyle       — 'dark' | 'street' | 'satellite'
 *   visibleLayers   — { [layer]: boolean }
 *   fetchLayer      — (name, {bbox, zoom}) => Promise<FeatureCollection>
 *   onCounts        — (counts) => void
 *   onFeatureClick  — (feature, event) => void
 *   onFeatureContextMenu — (feature, event) => void
 */
export default function MapCanvas({
  initialView = { longitude: 26, latitude: -29, zoom: 5 },
  baseStyle = 'dark',
  visibleLayers = {},
  fetchLayer,
  onCounts,
  onFeatureClick,
  onFeatureContextMenu,
}) {
  const mapRef = useRef(null)
  const [viewState, setViewState] = useState(initialView)
  const [layerData, setLayerData] = useState({})

  const refetchAll = useCallback(async () => {
    if (!mapRef.current || !fetchLayer) return
    const map = mapRef.current.getMap()
    const b = map.getBounds()
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
    const zoom = map.getZoom()
    const active = Object.entries(visibleLayers).filter(([, v]) => v).map(([k]) => k)
    const results = await Promise.allSettled(active.map((name) => fetchLayer(name, { bbox, zoom }).then((fc) => [name, fc])))
    const next = {}
    const counts = {}
    for (const r of results) {
      if (r.status === 'fulfilled') {
        const [name, fc] = r.value
        next[name] = fc
        counts[name] = fc?.features?.length ?? 0
      }
    }
    setLayerData((prev) => ({ ...prev, ...next }))
    onCounts?.(counts)
  }, [visibleLayers, fetchLayer, onCounts])

  // Re-fetch on view or layer toggle changes (debounced).
  const debouncedFetch = useMemo(() => debounce(refetchAll, 350), [refetchAll])
  useEffect(() => { debouncedFetch() }, [viewState, visibleLayers, debouncedFetch])

  const handleFeatureClick = useCallback((e) => {
    const f = e.features?.[0]
    if (!f) return
    onFeatureClick?.(f, e)
  }, [onFeatureClick])

  const handleContextMenu = useCallback((e) => {
    e.preventDefault?.()
    const map = mapRef.current?.getMap()
    if (!map) return
    const features = map.queryRenderedFeatures([e.point?.x ?? 0, e.point?.y ?? 0])
    onFeatureContextMenu?.(features?.[0] ?? null, e)
  }, [onFeatureContextMenu])

  useEffect(() => {
    const map = mapRef.current?.getMap()
    if (!map) return
    const handler = (e) => handleContextMenu(e)
    map.on('contextmenu', handler)
    return () => map.off('contextmenu', handler)
  }, [handleContextMenu])

  const interactive = useMemo(() => ['meters-pt', 'meters-cluster', 'transformers-pt', 'der-pt', 'alarms-pt', 'feeders-ln', 'outage_areas-fill', 'zones-fill', 'service_lines-ln', 'poles-pt'], [])

  return (
    <Map
      ref={mapRef}
      {...viewState}
      onMove={(evt) => setViewState(evt.viewState)}
      mapStyle={BASE_STYLES[baseStyle]?.style ?? BASE_STYLES.dark.style}
      style={{ width: '100%', height: '100%' }}
      interactiveLayerIds={interactive}
      onClick={handleFeatureClick}
      attributionControl={false}
    >
      <NavigationControl position="top-left" />
      <ScaleControl position="bottom-left" />
      <AttributionControl position="bottom-right" compact customAttribution="© OpenStreetMap contributors" />

      {/* Feeders (LineString) */}
      {visibleLayers.feeders && layerData.feeders && (
        <Source id="feeders-src" type="geojson" data={layerData.feeders}>
          <Layer id="feeders-ln" type="line" paint={{ 'line-color': '#56CCF2', 'line-width': 2, 'line-opacity': 0.8 }} />
        </Source>
      )}

      {/* Service lines */}
      {visibleLayers.service_lines && layerData.service_lines && (
        <Source id="service_lines-src" type="geojson" data={layerData.service_lines}>
          <Layer id="service_lines-ln" type="line" paint={{ 'line-color': '#FFFFFF', 'line-opacity': 0.35, 'line-width': 1 }} />
        </Source>
      )}

      {/* Outage areas (Polygon) */}
      {visibleLayers.outage_areas && layerData.outage_areas && (
        <Source id="outage_areas-src" type="geojson" data={layerData.outage_areas}>
          <Layer id="outage_areas-fill" type="fill" paint={{ 'fill-color': '#F97316', 'fill-opacity': 0.2 }} />
          <Layer id="outage_areas-line" type="line" paint={{ 'line-color': '#F97316', 'line-width': 1.5, 'line-dasharray': [2, 2] }} />
        </Source>
      )}

      {/* Zones (Polygon) */}
      {visibleLayers.zones && layerData.zones && (
        <Source id="zones-src" type="geojson" data={layerData.zones}>
          <Layer id="zones-fill" type="fill" paint={{ 'fill-color': '#ABC7FF', 'fill-opacity': 0.15 }} />
          <Layer id="zones-line" type="line" paint={{ 'line-color': '#ABC7FF', 'line-width': 1 }} />
        </Source>
      )}

      {/* Transformers (Point) */}
      {visibleLayers.transformers && layerData.transformers && (
        <Source id="transformers-src" type="geojson" data={layerData.transformers}>
          <Layer id="transformers-pt" type="circle" paint={{
            'circle-radius': 5,
            'circle-color': '#ABC7FF',
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1,
          }} />
        </Source>
      )}

      {/* Meters (Point OR cluster) */}
      {visibleLayers.meters && layerData.meters && (
        <Source id="meters-src" type="geojson" data={layerData.meters}>
          {/* Clustered (point_count) */}
          <Layer id="meters-cluster" type="circle"
            filter={['==', ['get', 'cluster'], true]}
            paint={{
              'circle-radius': ['interpolate', ['linear'], ['get', 'point_count'],
                1, 8, 20, 14, 100, 20, 500, 28],
              'circle-color': '#02C9A8',
              'circle-opacity': 0.55,
              'circle-stroke-color': '#02C9A8',
              'circle-stroke-width': 2,
            }}
          />
          <Layer id="meters-cluster-label" type="symbol"
            filter={['==', ['get', 'cluster'], true]}
            layout={{
              'text-field': ['get', 'point_count'],
              'text-size': 11,
              'text-font': ['Noto Sans Regular'],
            }}
            paint={{ 'text-color': '#ffffff', 'text-halo-color': '#000000', 'text-halo-width': 1 }}
          />
          {/* Individual meters */}
          <Layer id="meters-pt" type="circle"
            filter={['!=', ['get', 'cluster'], true]}
            paint={{
              'circle-radius': 4,
              'circle-color': [
                'match', ['get', 'status'],
                'online', STATUS_TO_COLOR.online,
                'offline', STATUS_TO_COLOR.offline,
                'tamper', STATUS_TO_COLOR.tamper,
                'disconnected', STATUS_TO_COLOR.disconnected,
                STATUS_TO_COLOR.online,
              ],
              'circle-stroke-color': '#ffffff',
              'circle-stroke-width': 0.5,
              'circle-opacity': 0.9,
            }}
          />
        </Source>
      )}

      {/* DER (Point) */}
      {visibleLayers.der && layerData.der && (
        <Source id="der-src" type="geojson" data={layerData.der}>
          <Layer id="der-pt" type="circle" paint={{
            'circle-radius': 7,
            'circle-color': [
              'match', ['get', 'asset_type'],
              'pv', DER_COLOR.pv, 'bess', DER_COLOR.bess,
              'ev_charger', DER_COLOR.ev_charger, 'microgrid', DER_COLOR.microgrid,
              DER_COLOR.pv,
            ],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1.5,
          }} />
        </Source>
      )}

      {/* Alarms (Point) */}
      {visibleLayers.alarms && layerData.alarms && (
        <Source id="alarms-src" type="geojson" data={layerData.alarms}>
          <Layer id="alarms-pt" type="circle" paint={{
            'circle-radius': 8,
            'circle-color': '#E94B4B',
            'circle-opacity': 0.25,
            'circle-stroke-color': '#E94B4B',
            'circle-stroke-width': 2,
          }} />
        </Source>
      )}

      {/* Poles (Point) */}
      {visibleLayers.poles && layerData.poles && (
        <Source id="poles-src" type="geojson" data={layerData.poles}>
          <Layer id="poles-pt" type="circle" paint={{
            'circle-radius': 3, 'circle-color': '#999',
            'circle-stroke-color': '#fff', 'circle-stroke-width': 0.5,
          }} />
        </Source>
      )}
    </Map>
  )
}
