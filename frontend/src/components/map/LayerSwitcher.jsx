/**
 * Layer switcher — toggles visibility of the five GIS layers
 * (feeder / DTR / pole / meter / outage) + optional overlays (alarm heatmap,
 * NTL suspects). Pure presentation; parent owns layer state.
 */
import { Layers } from 'lucide-react'

const LAYER_CONFIG = [
  { key: 'feeder',       label: 'Feeders',            color: '#ABC7FF' },
  { key: 'dtr',          label: 'DTRs',               color: '#56CCF2' },
  { key: 'pole',         label: 'Poles',              color: '#93C5FD' },
  { key: 'meter',        label: 'Meters',             color: '#02C9A8' },
  { key: 'outage',       label: 'Outages',            color: '#E94B4B' },
  { key: 'alarm_heat',   label: 'Alarm heatmap',      color: '#F97316' },
  { key: 'ntl_suspects', label: 'NTL suspects',       color: '#F59E0B' },
  // SMOC-FUNC-026-FR-03 — colour meters by consumption quartile.
  { key: 'consumption',  label: 'Consumption',        color: '#EF4444' },
]

export default function LayerSwitcher({ layers, onToggle }) {
  return (
    <div className="glass-card p-3 flex items-center gap-3 flex-wrap">
      <Layers size={14} className="text-accent-blue" />
      {LAYER_CONFIG.map(({ key, label, color }) => (
        <button
          key={key}
          data-testid={`layer-toggle-${key}`}
          onClick={() => onToggle(key)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors text-sm"
          style={{
            background: layers[key] ? `${color}20` : 'rgba(255,255,255,0.04)',
            color: layers[key] ? color : 'rgba(255,255,255,0.4)',
            border: `1px solid ${layers[key] ? `${color}40` : 'rgba(255,255,255,0.08)'}`,
          }}
        >
          <span className="w-2 h-2 rounded-full" style={{ background: color }} />
          {label}
        </button>
      ))}
    </div>
  )
}
