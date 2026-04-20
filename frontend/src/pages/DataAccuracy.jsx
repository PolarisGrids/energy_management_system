// Spec 018 W4.T14 — Data Accuracy console.
// Reads the /api/v1/data-accuracy cache and renders a filter + badge table.
// Per-row "reconcile" button creates an issue (audit-log token).

import { useEffect, useMemo, useState } from 'react'
import { RefreshCw, Wrench, Search } from 'lucide-react'
import useAuthStore from '@/stores/authStore'
import { hasPermission, P_DATA_ACCURACY_RECONCILE } from '@/auth/permissions'
import api from '@/services/api'

const STATUSES = ['all', 'healthy', 'lagging', 'missing_mdms', 'missing_cis', 'stale']

const BADGE_CLASS = {
  healthy:       'badge-ok',
  lagging:       'badge-medium',
  stale:         'badge-medium',
  missing_mdms:  'badge-critical',
  missing_cis:   'badge-critical',
  unknown:       'badge-info',
}

function fmt(ts) {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString()
  } catch { return ts }
}

function Badge({ status }) {
  const cls = BADGE_CLASS[status] || 'badge-info'
  return <span className={cls}>{status.replace(/_/g, ' ')}</span>
}

export default function DataAccuracy() {
  const { permissions } = useAuthStore()
  const canReconcile = hasPermission(permissions, P_DATA_ACCURACY_RECONCILE)

  const [rows, setRows] = useState([])
  const [counts, setCounts] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [lastRefresh, setLastRefresh] = useState(null)
  const [toasts, setToasts] = useState([])

  function pushToast(t) {
    const id = Math.random().toString(36).slice(2)
    setToasts((prev) => [...prev, { id, ...t }])
    setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), 4000)
  }

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params = {}
      if (filter !== 'all') params.status = filter
      if (search) params.meter_serial = search
      const { data } = await api.get('/data-accuracy', { params })
      setRows(data.rows || [])
      setCounts(data.counts_by_status || {})
      setLastRefresh(new Date())
    } catch (err) {
      setError(err?.response?.data?.detail ?? err?.message ?? 'Unavailable')
    } finally {
      setLoading(false)
    }
  }

  async function forceRefresh() {
    if (!canReconcile) return
    setRefreshing(true)
    try {
      await api.post('/data-accuracy/refresh')
      pushToast({ kind: 'ok', msg: 'Refresh started' })
      await load()
    } catch (err) {
      pushToast({ kind: 'err', msg: err?.response?.data?.detail ?? 'Refresh failed' })
    } finally {
      setRefreshing(false)
    }
  }

  async function reconcile(serial) {
    try {
      const { data } = await api.post(`/data-accuracy/${serial}/reconcile`)
      pushToast({ kind: 'ok', msg: `Reconcile queued: ${data.issue_id.slice(0, 8)}…` })
    } catch (err) {
      pushToast({ kind: 'err', msg: err?.response?.data?.detail ?? 'Reconcile failed' })
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter])

  const countEntries = useMemo(() => Object.entries(counts), [counts])

  return (
    <div className="space-y-4" data-testid="data-accuracy-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-white font-black text-xl">Data Accuracy</div>
          <div className="text-white/50 text-sm">
            HES ↔ MDMS ↔ CIS freshness per meter (refreshed every 5 min by the
            source_status scheduler).
          </div>
        </div>
        <div className="flex gap-2 items-center">
          <div className="relative">
            <Search size={14} className="absolute top-2 left-2 text-white/40" />
            <input
              className="bg-white/5 border border-white/10 rounded pl-7 pr-2 py-1.5 text-white placeholder:text-white/30 text-sm"
              placeholder="Meter serial"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && load()}
            />
          </div>
          <select
            className="bg-white/5 border border-white/10 rounded px-2 py-1.5 text-white text-sm"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <button
            onClick={load}
            className="btn-secondary flex items-center gap-2"
            style={{ padding: '6px 10px', fontSize: 12 }}
            disabled={loading}
            data-testid="data-accuracy-reload"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Reload
          </button>
          {canReconcile && (
            <button
              onClick={forceRefresh}
              className="btn-primary flex items-center gap-2"
              style={{ padding: '6px 10px', fontSize: 12 }}
              disabled={refreshing}
              data-testid="data-accuracy-force-refresh"
            >
              <Wrench size={12} /> Force refresh
            </button>
          )}
        </div>
      </div>

      {countEntries.length > 0 && (
        <div className="flex gap-3 flex-wrap" data-testid="data-accuracy-counts">
          {countEntries.map(([k, v]) => (
            <div key={k} className="glass-card px-3 py-2 flex items-center gap-2">
              <Badge status={k} />
              <span className="text-white font-bold">{v}</span>
            </div>
          ))}
        </div>
      )}

      {lastRefresh && (
        <div className="text-white/40 text-xs">Last loaded at {lastRefresh.toLocaleTimeString()}</div>
      )}

      {error && (
        <div className="glass-card p-4 border" style={{ borderColor: 'rgba(233,75,75,0.3)' }}>
          <div className="text-status-critical font-bold">Data Accuracy unavailable</div>
          <div className="text-white/60 text-sm mt-1">{error}</div>
        </div>
      )}

      <div className="glass-card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              <th>Meter</th>
              <th>Status</th>
              <th>HES last seen</th>
              <th>MDMS validated</th>
              <th>CIS billing</th>
              <th>Updated</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && !loading && !error && (
              <tr><td colSpan={7} className="text-center text-white/50 py-8">No rows match the current filter.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.meter_serial} data-testid={`row-${r.meter_serial}`}>
                <td className="font-mono text-white">{r.meter_serial}</td>
                <td><Badge status={r.status} /></td>
                <td className="text-white/60 text-xs">{fmt(r.hes_last_seen)}</td>
                <td className="text-white/60 text-xs">{fmt(r.mdms_last_validated)}</td>
                <td className="text-white/60 text-xs">{fmt(r.cis_last_billing)}</td>
                <td className="text-white/40 text-xs">{fmt(r.updated_at)}</td>
                <td className="text-right">
                  {canReconcile && (
                    <button
                      onClick={() => reconcile(r.meter_serial)}
                      className="btn-secondary"
                      style={{ padding: '4px 8px', fontSize: 11 }}
                    >
                      Reconcile
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Minimal toast stack */}
      <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="glass-card px-3 py-2 text-sm"
            style={{
              borderColor: t.kind === 'ok' ? 'rgba(2,201,168,0.4)' : 'rgba(233,75,75,0.4)',
              color: t.kind === 'ok' ? '#02C9A8' : '#E94B4B',
            }}
          >
            {t.msg}
          </div>
        ))}
      </div>
    </div>
  )
}
