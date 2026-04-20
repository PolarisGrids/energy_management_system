import { useEffect, useState } from 'react'

export const BASE_STYLES = {
  dark: {
    label: 'Dark',
    style: {
      version: 8,
      sources: {
        dark: {
          type: 'raster',
          tiles: [
            'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
            'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
          ],
          tileSize: 256,
          attribution: '© OpenStreetMap contributors © CARTO',
        },
      },
      layers: [{ id: 'dark', type: 'raster', source: 'dark' }],
    },
  },
  street: {
    label: 'Street',
    style: {
      version: 8,
      sources: {
        osm: {
          type: 'raster',
          tiles: [
            'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
            'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
          ],
          tileSize: 256,
          attribution: '© OpenStreetMap contributors',
        },
      },
      layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
    },
  },
  satellite: {
    label: 'Satellite',
    style: {
      version: 8,
      sources: {
        sat: {
          type: 'raster',
          tiles: [
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          ],
          tileSize: 256,
          attribution: '© Esri World Imagery',
        },
      },
      layers: [{ id: 'sat', type: 'raster', source: 'sat' }],
    },
  },
}

const STORAGE_KEY = 'polaris.gis.baseLayer'

export default function BaseLayerSwitcher({ value, onChange }) {
  const [selected, setSelected] = useState(value || 'dark')

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && BASE_STYLES[saved]) {
      setSelected(saved)
      onChange?.(saved)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (k) => {
    setSelected(k)
    localStorage.setItem(STORAGE_KEY, k)
    onChange?.(k)
  }

  return (
    <div style={{
      position: 'absolute', top: 10, right: 10, zIndex: 500,
      display: 'flex', gap: 4, padding: 4,
      background: 'rgba(10,15,30,0.85)', borderRadius: 8,
      border: '1px solid rgba(171,199,255,0.15)',
    }}>
      {Object.entries(BASE_STYLES).map(([k, v]) => (
        <button key={k} onClick={() => pick(k)}
          style={{
            padding: '4px 10px', border: 'none', borderRadius: 6,
            background: selected === k ? 'rgba(86,204,242,0.25)' : 'transparent',
            color: selected === k ? '#56CCF2' : 'rgba(255,255,255,0.6)',
            fontSize: 11, fontWeight: 600, cursor: 'pointer',
          }}>
          {v.label}
        </button>
      ))}
    </div>
  )
}
