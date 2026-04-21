import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { hierarchyAPI } from '@/services/api'

// Keys mirror the mdms-analytics contract exactly — the upstream filter
// controller (controllers/hierarchy.js) reads these exact params and the MV
// WHERE clauses in the EGSM report handlers look for the same column names.
const LEVELS = [
  { key: 'zone',            label: 'Zone' },
  { key: 'circle',          label: 'Circle' },
  { key: 'division',        label: 'Division' },
  { key: 'subdivision',     label: 'Sub Division' },
  { key: 'substation_name', label: 'Substation' },
  { key: 'feeder_category', label: 'Feeder Category' },
  { key: 'feeder_name',     label: 'Feeder' },
  { key: 'dtr_name',        label: 'DTR' },
]

// Record-field → option-set projection. The upstream response returns a flat
// array of {zone, circle, division, ...} rows; we dedupe per level to build
// each dropdown's options. The set-key must match the MV column name used by
// the filter param (so option.value can be sent back as that param).
function projectOptions(records) {
  const buckets = Object.fromEntries(LEVELS.map((l) => [l.key, new Set()]))
  for (const row of records || []) {
    for (const l of LEVELS) {
      const v = row?.[l.key]
      if (v && typeof v === 'string' && v.trim()) buckets[l.key].add(v.trim())
    }
  }
  const out = {}
  for (const [k, s] of Object.entries(buckets)) out[k] = Array.from(s).sort()
  return out
}

export default function HierarchyFilter() {
  const [searchParams, setSearchParams] = useSearchParams()

  // Local selections — one Set<string> per level.
  const [sel, setSel] = useState(() => {
    const init = {}
    for (const l of LEVELS) init[l.key] = new Set(searchParams.getAll(l.key))
    return init
  })

  // Options are refetched whenever the upstream filter scope narrows. We pass
  // the current selection as params so MDMS filters the distinct list.
  const [opts, setOpts] = useState({})
  const [loading, setLoading] = useState(false)

  const fetchOptions = useCallback(async () => {
    const params = {}
    for (const l of LEVELS) {
      const vals = Array.from(sel[l.key])
      if (vals.length) params[l.key] = vals
    }
    setLoading(true)
    try {
      const res = await hierarchyAPI.data(params)
      const records = res?.data?.data?.records || []
      setOpts(projectOptions(records))
    } catch (err) {
      // leave opts as-is; user can still apply existing selections
      console.error('hierarchy-data fetch failed', err)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(Object.fromEntries(LEVELS.map((l) => [l.key, Array.from(sel[l.key]).sort()])))])

  useEffect(() => { fetchOptions() }, [fetchOptions])

  // Apply button — push the current selection into URL search params, keeping
  // existing non-hierarchy keys (e.g. from/to date range) untouched.
  const onApply = (e) => {
    e.preventDefault()
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const l of LEVELS) {
        next.delete(l.key)
        for (const v of sel[l.key]) next.append(l.key, v)
      }
      return next
    })
  }

  const onClear = () => {
    const empty = Object.fromEntries(LEVELS.map((l) => [l.key, new Set()]))
    setSel(empty)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const l of LEVELS) next.delete(l.key)
      return next
    })
  }

  const toggle = (key, value) => {
    setSel((prev) => {
      const s = new Set(prev[key])
      if (s.has(value)) s.delete(value)
      else s.add(value)
      return { ...prev, [key]: s }
    })
  }

  const summary = useMemo(() => {
    const n = LEVELS.reduce((a, l) => a + sel[l.key].size, 0)
    return n === 0 ? 'No filter' : `${n} filter${n > 1 ? 's' : ''} selected`
  }, [sel])

  return (
    <form onSubmit={onApply} className="glass-card" style={{ padding: 14 }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 10,
      }}>
        <div className="text-white font-semibold" style={{ fontSize: 13 }}>
          Hierarchy Filter
        </div>
        <div style={{ color: '#ABC7FF', fontSize: 11 }}>
          {loading ? 'Loading options…' : summary}
        </div>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 10,
      }}>
        {LEVELS.map((l) => (
          <LevelSelect
            key={l.key}
            label={l.label}
            options={opts[l.key] || []}
            selected={sel[l.key]}
            onToggle={(v) => toggle(l.key, v)}
          />
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button type="submit" className="btn-primary" style={{ height: 32, fontSize: 12 }}>
          Apply
        </button>
        <button type="button" onClick={onClear} className="btn-secondary" style={{ height: 32, fontSize: 12 }}>
          Clear
        </button>
      </div>
    </form>
  )
}

// Lightweight multi-select: a native HTML <select multiple> styled to match
// the rest of the Reports UI. Intentionally terse — keeps the whole filter
// self-contained (no react-select dependency).
function LevelSelect({ label, options, selected, onToggle }) {
  const sorted = useMemo(() => options.slice().sort(), [options])
  const values = Array.from(selected)

  const onChange = (e) => {
    const chosen = Array.from(e.target.selectedOptions).map((o) => o.value)
    // Compute diff so onToggle is called once per change.
    const was = new Set(selected)
    const will = new Set(chosen)
    for (const v of was) if (!will.has(v)) onToggle(v)
    for (const v of will) if (!was.has(v)) onToggle(v)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={{ color: '#ABC7FF', fontSize: 11 }}>
        {label}{values.length > 0 && <span style={{ color: '#02C9A8' }}> · {values.length}</span>}
      </label>
      <select
        multiple
        value={values}
        onChange={onChange}
        size={Math.min(6, Math.max(3, sorted.length))}
        style={{
          padding: '6px 8px', background: '#0A1628', border: '1px solid #ABC7FF22',
          borderRadius: 6, color: '#fff', fontSize: 12, outline: 'none',
        }}
      >
        {sorted.length === 0 && <option disabled>— none —</option>}
        {sorted.map((v) => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>
    </div>
  )
}
