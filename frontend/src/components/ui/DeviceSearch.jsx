import { useCallback, useEffect, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import { devicesAPI } from '@/services/api'

/**
 * DeviceSearch — typeahead over /api/v1/devices/search.
 *
 * Spec 018 — "no-mock" cleanup (Wave 5). Replaces per-page hard-coded
 * meter/feeder/DTR dropdowns with a single typeahead backed by the real
 * CIS hierarchy via the EMS backend.
 *
 * Props:
 *   types         — array of device type filters, e.g. ['meter','feeder']
 *   onSelect(dev) — called with the picked device { id, type, label, meta }
 *   placeholder   — search-box placeholder
 *   value         — controlled display value (optional)
 *   minChars      — minimum characters before firing (default 2)
 */
export default function DeviceSearch({
  types = ['meter', 'consumer', 'dtr', 'feeder'],
  onSelect,
  placeholder = 'Search meter / DTR / feeder…',
  minChars = 2,
  value = '',
}) {
  const [query, setQuery] = useState(value)
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [source, setSource] = useState(null)
  const timerRef = useRef(null)
  const wrapRef = useRef(null)

  // 300 ms debounce.
  const runSearch = useCallback(async (q) => {
    if (!q || q.length < minChars) {
      setResults([])
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await devicesAPI.search({ q, type: types.join(',') })
      const payload = res.data || {}
      // Envelope: {ok, data, source, as_of}. Tolerate raw arrays too.
      const rows = Array.isArray(payload) ? payload : payload.data || []
      setResults(Array.isArray(rows) ? rows : [])
      setSource(payload.source || null)
      setOpen(true)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Device search unavailable')
      setResults([])
      setOpen(true)
    } finally {
      setLoading(false)
    }
  }, [types, minChars])

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => runSearch(query), 300)
    return () => clearTimeout(timerRef.current)
  }, [query, runSearch])

  // Close on outside click.
  useEffect(() => {
    const onClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const pick = (dev) => {
    setQuery(dev.label || dev.id)
    setOpen(false)
    onSelect?.(dev)
  }

  const clear = () => {
    setQuery('')
    setResults([])
    onSelect?.(null)
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative', minWidth: 260 }} data-testid="device-search">
      <div style={{ position: 'relative' }}>
        <Search
          size={13}
          style={{
            position: 'absolute',
            left: 9,
            top: '50%',
            transform: 'translateY(-50%)',
            color: '#ABC7FF88',
          }}
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          placeholder={placeholder}
          style={{
            width: '100%',
            paddingLeft: 28,
            paddingRight: 28,
            paddingTop: 8,
            paddingBottom: 8,
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid #ABC7FF22',
            borderRadius: 8,
            color: '#fff',
            fontSize: 13,
            outline: 'none',
          }}
        />
        {query && (
          <button
            type="button"
            onClick={clear}
            aria-label="Clear"
            style={{
              position: 'absolute',
              right: 6,
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'transparent',
              border: 0,
              color: '#ABC7FF88',
              cursor: 'pointer',
            }}
          >
            <X size={13} />
          </button>
        )}
      </div>

      {open && (
        <div
          className="glass-card"
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            maxHeight: 280,
            overflowY: 'auto',
            zIndex: 50,
            padding: 6,
          }}
        >
          {loading && (
            <div style={{ padding: 12, color: '#ABC7FF', fontSize: 12 }}>Searching…</div>
          )}
          {error && !loading && (
            <div style={{ padding: 12, color: '#E94B4B', fontSize: 12 }}>{error}</div>
          )}
          {!loading && !error && results.length === 0 && query.length >= minChars && (
            <div style={{ padding: 12, color: '#ABC7FF', fontSize: 12 }}>No matches.</div>
          )}
          {!loading && results.map((dev) => (
            <button
              key={`${dev.type || 'x'}-${dev.id || dev.label}`}
              type="button"
              onClick={() => pick(dev)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '7px 10px',
                borderRadius: 6,
                background: 'transparent',
                border: 0,
                color: '#fff',
                fontSize: 12,
                cursor: 'pointer',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(86,204,242,0.12)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <span style={{ color: '#56CCF2', fontFamily: 'monospace', marginRight: 8 }}>
                {dev.id}
              </span>
              <span>{dev.label || dev.name || dev.id}</span>
              {dev.type && (
                <span
                  style={{
                    marginLeft: 8,
                    padding: '1px 6px',
                    borderRadius: 4,
                    background: '#ABC7FF22',
                    color: '#ABC7FF',
                    fontSize: 10,
                    textTransform: 'uppercase',
                  }}
                >
                  {dev.type}
                </span>
              )}
            </button>
          ))}
          {source && source !== 'mdms' && results.length > 0 && (
            <div
              style={{
                padding: '6px 10px',
                color: '#F59E0B',
                fontSize: 10,
                borderTop: '1px solid rgba(171,199,255,0.1)',
                marginTop: 4,
              }}
            >
              Source: {source} — MDMS aggregate pending
            </div>
          )}
        </div>
      )}
    </div>
  )
}
