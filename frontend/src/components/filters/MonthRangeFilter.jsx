import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

// Utility: return first-of-month ISO date for a given YYYY-MM-DD string.
// The mdms-analytics-service reads `from` / `to` as YYYY-MM-DD and converts
// each to timestamp bounds (inclusive-exclusive), so we always pass the
// first of the selected month.
function firstOfMonth(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-01`
}

// Utility: given a YYYY-MM-DD string, return the first of the *next* month.
// Used to build an exclusive end for date-range queries.
function firstOfNextMonth(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const year = d.getUTCFullYear()
  const month = d.getUTCMonth() // 0-indexed
  const next = new Date(Date.UTC(year, month + 1, 1))
  return `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, '0')}-01`
}

// Default range = last 5 months + current month, matching the Energy Audit
// landing page default in avdhaan_v2.
function defaultRange() {
  const today = new Date()
  const to = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() + 1, 1))
  const from = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - 4, 1))
  const iso = (d) => `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-01`
  return { from: iso(from), to: iso(to) }
}

export default function MonthRangeFilter({ showConsumerType = false }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const { from: defaultFrom, to: defaultTo } = useMemo(defaultRange, [])

  const [fromDate, setFromDate] = useState(() => searchParams.get('from') || defaultFrom)
  const [toDate, setToDate] = useState(() => searchParams.get('to') || defaultTo)
  const [consumerType, setConsumerType] = useState(
    () => searchParams.get('consumerType') || 'Feeder',
  )

  // Seed URL with defaults if unset (so downstream tables fetch immediately).
  useEffect(() => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (!next.get('from')) next.set('from', defaultFrom)
        if (!next.get('to')) next.set('to', defaultTo)
        if (showConsumerType && !next.get('consumerType')) {
          next.set('consumerType', 'Feeder')
        } else if (!showConsumerType) {
          next.delete('consumerType')
        }
        return next.toString() === prev.toString() ? prev : next
      },
      { replace: true },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultFrom, defaultTo, showConsumerType])

  // Keep local state in sync when URL params change via other components.
  useEffect(() => {
    const f = searchParams.get('from') || defaultFrom
    const t = searchParams.get('to') || defaultTo
    setFromDate(f)
    setToDate(t)
    if (showConsumerType) setConsumerType(searchParams.get('consumerType') || 'Feeder')
  }, [searchParams, defaultFrom, defaultTo, showConsumerType])

  const onApply = (e) => {
    e.preventDefault()
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('from', firstOfMonth(fromDate))
      // `to` is exclusive — if the user picked a whole month, push it to the
      // first of the following month so that whole-month rows are included.
      next.set('to', firstOfNextMonth(toDate))
      if (showConsumerType) next.set('consumerType', consumerType)
      return next
    })
  }

  const onReset = () => {
    setFromDate(defaultFrom)
    setToDate(defaultTo)
    setConsumerType('Feeder')
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('from', defaultFrom)
      next.set('to', defaultTo)
      if (showConsumerType) next.set('consumerType', 'Feeder')
      return next
    })
  }

  return (
    <form
      onSubmit={onApply}
      className="glass-card"
      style={{ padding: 12, display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: 12 }}
    >
      {showConsumerType && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <label style={{ color: '#ABC7FF', fontSize: 11 }}>Consumer Type</label>
          <select
            value={consumerType}
            onChange={(e) => setConsumerType(e.target.value)}
            style={{
              padding: '6px 10px', background: '#0A1628', border: '1px solid #ABC7FF22',
              borderRadius: 6, color: '#fff', fontSize: 12,
            }}
          >
            <option value="Feeder">Feeder</option>
            <option value="DTR">DTR</option>
          </select>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <label style={{ color: '#ABC7FF', fontSize: 11 }}>From (Month)</label>
        <input
          type="month"
          value={fromDate.slice(0, 7)}
          onChange={(e) => setFromDate(`${e.target.value}-01`)}
          style={{
            padding: '6px 10px', background: '#0A1628', border: '1px solid #ABC7FF22',
            borderRadius: 6, color: '#fff', fontSize: 12, colorScheme: 'dark',
          }}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <label style={{ color: '#ABC7FF', fontSize: 11 }}>To (Month)</label>
        <input
          type="month"
          value={toDate.slice(0, 7)}
          onChange={(e) => setToDate(`${e.target.value}-01`)}
          style={{
            padding: '6px 10px', background: '#0A1628', border: '1px solid #ABC7FF22',
            borderRadius: 6, color: '#fff', fontSize: 12, colorScheme: 'dark',
          }}
        />
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button type="submit" className="btn-primary" style={{ height: 32, fontSize: 12 }}>
          Apply
        </button>
        <button type="button" onClick={onReset} className="btn-secondary" style={{ height: 32, fontSize: 12 }}>
          Reset
        </button>
      </div>
    </form>
  )
}
