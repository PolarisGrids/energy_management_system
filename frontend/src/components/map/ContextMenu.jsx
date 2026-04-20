/**
 * Zoom-aware context menu for the GIS map (spec 018 W3.T6 / US-22).
 *
 * The action list is driven by the current map zoom + the asset the operator
 * right-clicked on. Each action returns a stable id the parent handles (no
 * business logic lives here).
 *
 * Zoom levels (aligned with `ZoomBreadcrumb`):
 *   < 10 — Regional / country       → Run regional report, Alarm heatmap
 *  10-13 — Feeder / DTR              → View downstream meters, View load profile
 *  >= 14 — Meter                     → Read register, Disconnect, View consumer
 */
import { Eye, Terminal, BarChart2, FileText, Zap, Users, Activity, PowerOff } from 'lucide-react'

export function buildContextActions({ zoom, asset }) {
  const layer = asset?.layer ?? asset?.type ?? ''

  // Country / region zoom
  if (zoom < 10) {
    return [
      { id: 'regional_report', icon: FileText, label: 'Run regional report', color: '#ABC7FF' },
      { id: 'alarm_heatmap',   icon: Activity, label: 'Show alarm heatmap',   color: '#E94B4B' },
    ]
  }

  // DTR / feeder zoom
  if (zoom < 14) {
    if (layer === 'dtr') {
      return [
        { id: 'dtr_downstream',    icon: Users,     label: 'View downstream meters', color: '#02C9A8' },
        { id: 'dtr_load_profile',  icon: BarChart2, label: 'View load profile',      color: '#56CCF2' },
        { id: 'dtr_energy_balance',icon: Zap,       label: 'Energy balance',         color: '#F59E0B' },
      ]
    }
    if (layer === 'feeder') {
      return [
        { id: 'feeder_load',    icon: BarChart2, label: 'View feeder load',   color: '#56CCF2' },
        { id: 'feeder_report',  icon: FileText,  label: 'Run feeder report',  color: '#ABC7FF' },
      ]
    }
    return [
      { id: 'details', icon: Eye, label: 'View details', color: '#ABC7FF' },
    ]
  }

  // Meter zoom
  if (layer === 'meter') {
    return [
      { id: 'meter_read',       icon: BarChart2, label: 'Read register',    color: '#56CCF2' },
      { id: 'meter_disconnect', icon: PowerOff,  label: 'Disconnect meter', color: '#E94B4B' },
      { id: 'meter_consumer',   icon: Users,     label: 'View consumer',    color: '#02C9A8' },
      { id: 'meter_command',    icon: Terminal,  label: 'Send HES command', color: '#F59E0B' },
    ]
  }
  return [
    { id: 'details', icon: Eye, label: 'View details', color: '#ABC7FF' },
  ]
}

export default function ContextMenu({ position, asset, zoom, onClose, onAction }) {
  if (!position || !asset) return null
  const actions = buildContextActions({ zoom, asset })

  return (
    <div
      data-testid="gis-context-menu"
      style={{
        position: 'fixed', left: position.x, top: position.y, zIndex: 10000,
        background: 'rgba(10,15,30,0.95)', backdropFilter: 'blur(12px)',
        border: '1px solid rgba(171,199,255,0.15)', borderRadius: 10,
        padding: 6, minWidth: 200, boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
      }}
    >
      <div
        style={{
          padding: '6px 10px',
          fontSize: 11,
          color: 'rgba(255,255,255,0.4)',
          fontWeight: 700,
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          marginBottom: 4,
          textTransform: 'uppercase',
          letterSpacing: 0.4,
        }}
      >
        {asset.serial || asset.name || asset.meter_serial || asset.layer || 'Asset'}
      </div>
      {actions.map((a) => (
        <button
          key={a.id}
          onClick={() => { onAction(a.id, asset); onClose() }}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 10px',
            border: 'none',
            borderRadius: 6,
            background: 'transparent',
            color: 'rgba(255,255,255,0.7)',
            fontSize: 12,
            fontWeight: 600,
            cursor: 'pointer',
            textAlign: 'left',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = `${a.color}20`
            e.currentTarget.style.color = a.color
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent'
            e.currentTarget.style.color = 'rgba(255,255,255,0.7)'
          }}
        >
          <a.icon size={13} style={{ flexShrink: 0 }} />
          {a.label}
        </button>
      ))}
    </div>
  )
}
