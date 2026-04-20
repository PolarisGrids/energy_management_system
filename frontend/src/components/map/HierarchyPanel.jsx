/**
 * HierarchyPanel — glass-card overlay that renders the current node of the
 * 8-level admin hierarchy (zone → consumer), its stats grid, drill-down
 * children list, breadcrumb path, and per-level command palette.
 *
 * Self-contained: the parent owns the fetch + state and calls back into the
 * map via onDrill / onBreadcrumbClick / onReset / onCommand.
 */
import { useEffect, useState } from 'react'
import { ChevronRight, RotateCcw } from 'lucide-react'

const LEVEL_COLORS = {
  zone:        '#ABC7FF',
  circle:      '#ABC7FF',
  division:    '#56CCF2',
  subdivision: '#56CCF2',
  substation:  '#02C9A8',
  feeder:      '#02C9A8',
  dtr:         '#F59E0B',
  consumer:    '#E94B4B',
}

const UNIT_SUFFIX = (key) => {
  const k = key.toLowerCase()
  if (k.endsWith('_pct') || k === 'loading_pct') return '%'
  if (k.endsWith('_kva')) return ' kVA'
  if (k.endsWith('_kw')) return ' kW'
  if (k.endsWith('_v')) return ' V'
  return ''
}

const fmtValue = (key, value) => {
  if (value == null) return '—'
  if (typeof value === 'number') {
    const rounded = Number.isInteger(value) ? value : value.toFixed(1)
    return `${rounded}${UNIT_SUFFIX(key)}`
  }
  return String(value)
}

const fmtKey = (key) => key.replace(/_/g, ' ').toUpperCase()

const isCritical = (key, value) => {
  if (typeof value !== 'number') return false
  if (key === 'critical_alarms' && value > 0) return true
  if (key === 'loading_pct' && value > 80) return true
  return false
}

function LevelPill({ level }) {
  const color = LEVEL_COLORS[level] ?? '#ABC7FF'
  return (
    <span style={{
      padding: '2px 8px',
      borderRadius: 999,
      background: `${color}30`,
      color,
      border: `1px solid ${color}60`,
      fontSize: 10,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: 0.5,
    }}>{level}</span>
  )
}

export default function HierarchyPanel({
  currentNode,
  stats = {},
  children = [],
  commands = [],
  breadcrumb = [],
  onDrill,
  onBreadcrumbClick,
  onReset,
  onCommand,
}) {
  const [toast, setToast] = useState(null)

  useEffect(() => {
    if (!toast) return undefined
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])

  if (!currentNode) {
    return (
      <div
        className="glass-card p-4"
        data-testid="hierarchy-panel"
        style={{
          position: 'absolute',
          top: 12,
          right: 12,
          zIndex: 500,
          width: 340,
          color: 'rgba(255,255,255,0.4)',
          fontSize: 12,
        }}
      >
        Loading hierarchy…
      </div>
    )
  }

  const handleCommand = async (cmd) => {
    try {
      const res = await onCommand?.(cmd)
      if (res?.message) setToast(res.message)
      else setToast(`${cmd} dispatched`)
    } catch (err) {
      setToast(`Error: ${err?.message ?? 'command failed'}`)
    }
  }

  return (
    <div
      className="glass-card p-4"
      data-testid="hierarchy-panel"
      style={{
        position: 'absolute',
        top: 12,
        right: 12,
        zIndex: 500,
        width: 340,
        maxHeight: 'calc(100% - 24px)',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
      onWheel={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Header: breadcrumb + reset */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <div
          data-testid="hierarchy-breadcrumb"
          style={{
            flex: 1,
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 2,
            fontSize: 11,
            color: 'rgba(255,255,255,0.55)',
          }}
        >
          {breadcrumb.length === 0 && <span style={{ color: 'rgba(255,255,255,0.35)' }}>Root</span>}
          {breadcrumb.map((crumb, i) => {
            const last = i === breadcrumb.length - 1
            return (
              <span key={crumb.id ?? i} style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
                {i > 0 && <ChevronRight size={11} style={{ color: 'rgba(255,255,255,0.25)' }} />}
                <button
                  onClick={() => onBreadcrumbClick?.(crumb.id)}
                  disabled={last}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    padding: '2px 4px',
                    color: last ? '#fff' : 'rgba(255,255,255,0.6)',
                    cursor: last ? 'default' : 'pointer',
                    fontWeight: last ? 700 : 500,
                    fontSize: 11,
                  }}
                >{crumb.name}</button>
              </span>
            )
          })}
        </div>
        <button
          onClick={onReset}
          title="Reset hierarchy"
          data-testid="hierarchy-reset"
          style={{
            background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 6,
            padding: 4,
            color: 'rgba(255,255,255,0.6)',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 3,
            fontSize: 10,
          }}
        >
          <RotateCcw size={11} /> Reset
        </button>
      </div>

      {/* Current node header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>
          {currentNode.name}
        </span>
        <LevelPill level={currentNode.level} />
      </div>

      {/* Stats grid */}
      {Object.keys(stats).length > 0 && (
        <div
          style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}
          data-testid="hierarchy-stats"
        >
          {Object.entries(stats).map(([k, v]) => {
            const critical = isCritical(k, v)
            return (
              <div
                key={k}
                style={{
                  background: critical ? 'rgba(233,75,75,0.10)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${critical ? 'rgba(233,75,75,0.35)' : 'rgba(255,255,255,0.08)'}`,
                  borderRadius: 6,
                  padding: '6px 8px',
                }}
              >
                <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.45)', letterSpacing: 0.4 }}>
                  {fmtKey(k)}
                </div>
                <div style={{
                  fontSize: 13,
                  fontWeight: 700,
                  color: critical ? '#E94B4B' : '#fff',
                  marginTop: 2,
                }}>
                  {fmtValue(k, v)}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Children list */}
      {children.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }} data-testid="hierarchy-children">
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', fontWeight: 700, letterSpacing: 0.5 }}>
            CHILDREN ({children.length})
          </div>
          {children.map((child) => {
            const cs = child.stats ?? {}
            const alarms = cs.critical_alarms ?? cs.alarms ?? 0
            const meters = cs.meters ?? cs.meter_count ?? cs.consumer_count
            const crit = (typeof alarms === 'number' && alarms > 0) ||
                         (typeof cs.loading_pct === 'number' && cs.loading_pct > 80)
            return (
              <button
                key={child.id}
                onClick={() => onDrill?.(child)}
                disabled={child.has_children === false}
                data-testid={`hierarchy-child-${child.id}`}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                  textAlign: 'left',
                  padding: '6px 8px',
                  borderRadius: 6,
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  color: '#fff',
                  cursor: child.has_children === false ? 'default' : 'pointer',
                  transition: 'border-color 120ms ease, background 120ms ease',
                }}
                onMouseEnter={(e) => {
                  if (child.has_children !== false) {
                    e.currentTarget.style.borderColor = '#02C9A8'
                    e.currentTarget.style.background = 'rgba(2,201,168,0.08)'
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'
                  e.currentTarget.style.background = 'rgba(255,255,255,0.03)'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>{child.name}</span>
                  <LevelPill level={child.level} />
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {meters != null && (
                    <span style={{
                      fontSize: 10, padding: '1px 6px', borderRadius: 4,
                      background: 'rgba(2,201,168,0.12)', color: '#02C9A8',
                    }}>{meters} meters</span>
                  )}
                  {typeof alarms === 'number' && alarms > 0 && (
                    <span style={{
                      fontSize: 10, padding: '1px 6px', borderRadius: 4,
                      background: 'rgba(233,75,75,0.15)', color: '#E94B4B',
                    }}>{alarms} alarms</span>
                  )}
                  {crit && alarms === 0 && (
                    <span style={{
                      fontSize: 10, padding: '1px 6px', borderRadius: 4,
                      background: 'rgba(233,75,75,0.15)', color: '#E94B4B',
                    }}>overloaded</span>
                  )}
                </div>
              </button>
            )
          })}
        </div>
      )}

      {/* Commands palette */}
      {commands.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }} data-testid="hierarchy-commands">
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', fontWeight: 700, letterSpacing: 0.5 }}>
            COMMANDS
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {commands.map((c) => (
              <button
                key={c.cmd}
                onClick={() => handleCommand(c.cmd)}
                className="btn-secondary"
                data-testid={`hierarchy-cmd-${c.cmd}`}
                style={{
                  fontSize: 11,
                  padding: '4px 10px',
                  borderRadius: 999,
                  background: 'rgba(86,204,242,0.10)',
                  color: '#56CCF2',
                  border: '1px solid rgba(86,204,242,0.35)',
                  cursor: 'pointer',
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div
          data-testid="hierarchy-toast"
          style={{
            position: 'absolute',
            left: 12,
            right: 12,
            bottom: 12,
            padding: '8px 10px',
            borderRadius: 6,
            background: 'rgba(2,201,168,0.15)',
            border: '1px solid rgba(2,201,168,0.45)',
            color: '#02C9A8',
            fontSize: 11,
            fontWeight: 600,
            boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
          }}
        >
          {toast}
        </div>
      )}
    </div>
  )
}
