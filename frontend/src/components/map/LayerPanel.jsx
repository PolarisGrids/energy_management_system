// Layer visibility panel with feature counts (spec 014-gis-postgis MVP).
import { Layers } from 'lucide-react'

const LAYERS = [
  { key: 'feeders',      label: 'Feeders',      color: '#56CCF2' },
  { key: 'transformers', label: 'Transformers', color: '#ABC7FF' },
  { key: 'meters',       label: 'Meters',       color: '#02C9A8' },
  { key: 'der',          label: 'DER',          color: '#F59E0B' },
  { key: 'alarms',       label: 'Alarms',       color: '#E94B4B' },
  { key: 'outage_areas', label: 'Outages',      color: '#F97316' },
  { key: 'service_lines',label: 'Service Lines',color: '#FFFFFF', defaultOff: true },
  { key: 'poles',        label: 'Poles',        color: '#999999', defaultOff: true },
  { key: 'zones',        label: 'Zones',        color: '#ABC7FF', defaultOff: true },
]

export default function LayerPanel({ visible, onToggle, counts = {} }) {
  return (
    <div className="glass-card p-3 flex items-center gap-2 flex-wrap">
      <Layers size={14} className="text-accent-blue" />
      {LAYERS.map(({ key, label, color }) => {
        const on = !!visible[key]
        const count = counts[key]
        return (
          <button key={key} onClick={() => onToggle(key)}
            className="flex items-center gap-2 px-2.5 py-1 rounded-md text-xs"
            style={{
              background: on ? `${color}20` : 'rgba(255,255,255,0.04)',
              color: on ? color : 'rgba(255,255,255,0.4)',
              border: `1px solid ${on ? `${color}40` : 'rgba(255,255,255,0.08)'}`,
            }}>
            <span className="w-2 h-2 rounded-full" style={{ background: color }} />
            {label}{typeof count === 'number' ? ` (${count})` : ''}
          </button>
        )
      })}
    </div>
  )
}

export { LAYERS }
