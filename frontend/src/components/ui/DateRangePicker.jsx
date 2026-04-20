import { useEffect, useState } from 'react'
import { Calendar } from 'lucide-react'

/**
 * DateRangePicker — preset buttons + custom from/to range.
 *
 * Spec 018 — "no-mock" cleanup (Wave 5). Replaces stale hardcoded date
 * strings (AuditLog, Reports) with a shared, always-current picker.
 *
 * Props:
 *   value      — { from: 'YYYY-MM-DD', to: 'YYYY-MM-DD', preset: 'today'|'7d'|'30d'|'90d'|'custom' }
 *   onChange   — called with the same shape on every change
 *   presets    — override the preset list (defaults to Today/7d/30d/90d/Custom)
 */

const iso = (d) => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${dd}`
}

export const todayIso = () => iso(new Date())
export const daysAgoIso = (n) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return iso(d)
}

export const defaultRange = (preset = '7d') => {
  const to = todayIso()
  if (preset === 'today') return { from: to, to, preset }
  if (preset === '30d')   return { from: daysAgoIso(30), to, preset }
  if (preset === '90d')   return { from: daysAgoIso(90), to, preset }
  // default 7d
  return { from: daysAgoIso(7), to, preset: '7d' }
}

const DEFAULT_PRESETS = [
  { id: 'today', label: 'Today' },
  { id: '7d',    label: '7 d'   },
  { id: '30d',   label: '30 d'  },
  { id: '90d',   label: '90 d'  },
  { id: 'custom',label: 'Custom'},
]

export default function DateRangePicker({ value, onChange, presets = DEFAULT_PRESETS }) {
  const [state, setState] = useState(value || defaultRange('7d'))

  // Keep internal state in sync when parent pushes a new value.
  useEffect(() => {
    if (value && (value.from !== state.from || value.to !== state.to || value.preset !== state.preset)) {
      setState(value)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value?.from, value?.to, value?.preset])

  const update = (next) => {
    setState(next)
    onChange?.(next)
  }

  const handlePreset = (id) => {
    if (id === 'custom') {
      update({ ...state, preset: 'custom' })
      return
    }
    update(defaultRange(id))
  }

  const showCustom = state.preset === 'custom'

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}
         data-testid="date-range-picker">
      <Calendar size={13} style={{ color: '#ABC7FF' }} />
      <div
        style={{
          display: 'flex',
          background: 'rgba(255,255,255,0.04)',
          padding: 3,
          borderRadius: 8,
          gap: 2,
        }}
      >
        {presets.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => handlePreset(p.id)}
            data-testid={`date-preset-${p.id}`}
            style={{
              padding: '5px 10px',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              border: 0,
              background: state.preset === p.id ? 'rgba(86,204,242,0.15)' : 'transparent',
              color: state.preset === p.id ? '#56CCF2' : '#ABC7FF',
              transition: 'background 0.15s',
            }}
          >
            {p.label}
          </button>
        ))}
      </div>
      {showCustom && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="date"
            value={state.from}
            onChange={(e) => update({ ...state, from: e.target.value, preset: 'custom' })}
            style={{
              padding: '6px 8px',
              background: '#0A1628',
              border: '1px solid #ABC7FF22',
              borderRadius: 6,
              color: '#fff',
              fontSize: 12,
              colorScheme: 'dark',
            }}
          />
          <span style={{ color: '#ABC7FF', fontSize: 11 }}>to</span>
          <input
            type="date"
            value={state.to}
            onChange={(e) => update({ ...state, to: e.target.value, preset: 'custom' })}
            style={{
              padding: '6px 8px',
              background: '#0A1628',
              border: '1px solid #ABC7FF22',
              borderRadius: 6,
              color: '#fff',
              fontSize: 12,
              colorScheme: 'dark',
            }}
          />
        </div>
      )}
      {!showCustom && (
        <span style={{ color: '#ABC7FF88', fontSize: 11 }}>
          {state.from} → {state.to}
        </span>
      )}
    </div>
  )
}
