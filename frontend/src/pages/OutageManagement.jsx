/**
 * Outage Management — spec 018 W3.T4.
 *
 * Lists spec-018 `outage_incident` rows (distinct from the spec-016
 * feeder-scoped outage_incidents table). Operators can acknowledge,
 * dispatch a crew, or trigger FLISR actions via the detail view.
 */
import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle, RefreshCw, Filter, ChevronRight,
  Activity, CheckCircle2, Clock, Zap,
} from 'lucide-react'
import { outagesAPI } from '@/services/api'
import useAuthStore from '@/stores/authStore'
import { useToast } from '@/components/ui/Toast'

const STATUS_BADGE = {
  DETECTED: 'badge-critical',
  INVESTIGATING: 'badge-high',
  DISPATCHED: 'badge-medium',
  RESTORED: 'badge-ok',
  CLOSED: 'badge-low',
}

const fmt = (v, decimals = 0) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: decimals })

const fmtTime = (v) => (v ? new Date(v).toLocaleString('en-ZA') : '—')


function KPITile({ icon: Icon, label, value, color = '#02C9A8', sub }) {
  return (
    <div className="glass-card p-5 flex items-center gap-4">
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: `${color}20` }}
      >
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <div className="text-white font-black" style={{ fontSize: 26 }}>{value}</div>
        <div className="text-white/50 font-medium" style={{ fontSize: 13 }}>{label}</div>
        {sub && <div style={{ color, fontSize: 11, marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  )
}

function LoadingOverlay({ label = 'Loading outages…' }) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="flex items-center gap-3 text-white/40">
        <RefreshCw size={16} className="animate-spin" />
        <span style={{ fontSize: 14 }}>{label}</span>
      </div>
    </div>
  )
}

function ErrorBanner({ message, onRetry }) {
  return (
    <div
      className="glass-card p-4 flex items-center gap-3"
      style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}
    >
      <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
      <span className="text-white/80" style={{ fontSize: 14 }}>{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="btn-secondary ml-auto"
          style={{ padding: '6px 14px', fontSize: 12 }}
        >
          Retry
        </button>
      )}
    </div>
  )
}

function EmptyState({ message = 'No outage incidents yet.' }) {
  return (
    <div className="glass-card p-10 text-center text-white/50">
      <CheckCircle2 size={28} className="mx-auto mb-3" style={{ color: '#02C9A8' }} />
      <div style={{ fontSize: 14 }}>{message}</div>
      <div className="text-white/30 mt-1" style={{ fontSize: 12 }}>
        The correlator is running; new events will open incidents automatically.
      </div>
    </div>
  )
}


export default function OutageManagement() {
  const { user } = useAuthStore()
  const toast = useToast()
  const [incidents, setIncidents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState({ status: '' })

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = {}
      if (filter.status) params.status = filter.status
      const { data } = await outagesAPI.list(params)
      setIncidents(data?.incidents ?? [])
    } catch (err) {
      setError(err?.response?.data?.detail ?? err?.message ?? 'Failed to load outages')
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => { load() }, [load])

  const counts = incidents.reduce((acc, inc) => {
    acc[inc.status] = (acc[inc.status] ?? 0) + 1
    acc.total = (acc.total ?? 0) + 1
    acc.affected = (acc.affected ?? 0) + (inc.affected_meter_count ?? 0)
    return acc
  }, {})

  return (
    <div className="space-y-5 animate-slide-up">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>Outage Management</h1>
          <div className="text-white/50" style={{ fontSize: 12 }}>
            Auto-detected from meter power-failure clusters (N≥3 per DTR / 120s)
          </div>
        </div>
        <button
          onClick={load}
          className="btn-secondary flex items-center gap-2"
          style={{ padding: '8px 14px', fontSize: 12 }}
        >
          <RefreshCw size={12} />
          Refresh
        </button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-4 gap-4">
        <KPITile icon={AlertTriangle} label="Active" value={fmt((counts.DETECTED ?? 0) + (counts.INVESTIGATING ?? 0))} color="#E94B4B" />
        <KPITile icon={Clock} label="Dispatched" value={fmt(counts.DISPATCHED ?? 0)} color="#F59E0B" />
        <KPITile icon={CheckCircle2} label="Restored" value={fmt(counts.RESTORED ?? 0)} color="#02C9A8" />
        <KPITile icon={Activity} label="Meters affected" value={fmt(counts.affected ?? 0)} color="#56CCF2" />
      </div>

      {/* Filters */}
      <div className="glass-card p-4 flex items-center gap-4">
        <Filter size={14} className="text-accent-blue" />
        <select
          value={filter.status}
          onChange={(e) => setFilter({ ...filter, status: e.target.value })}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
        >
          <option value="">All status</option>
          <option value="DETECTED">Detected</option>
          <option value="INVESTIGATING">Investigating</option>
          <option value="DISPATCHED">Dispatched</option>
          <option value="RESTORED">Restored</option>
        </select>
        <span className="ml-auto text-white/40 text-sm">{incidents.length} incidents</span>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <LoadingOverlay />
      ) : incidents.length === 0 && !error ? (
        <EmptyState />
      ) : (
        <div className="glass-card overflow-hidden">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>DTR(s)</th>
                <th>Affected / Restored</th>
                <th>Confidence</th>
                <th>Opened</th>
                <th>Duration</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((inc) => {
                const duration = inc.closed_at
                  ? `${Math.round((new Date(inc.closed_at) - new Date(inc.opened_at)) / 60000)} min`
                  : `${Math.round((Date.now() - new Date(inc.opened_at)) / 60000)} min (open)`
                return (
                  <tr key={inc.id}>
                    <td className="text-white/70 font-mono text-xs">{inc.id.slice(0, 8)}</td>
                    <td><span className={STATUS_BADGE[inc.status] ?? 'badge-info'}>{inc.status}</span></td>
                    <td className="text-white/70 text-xs">{(inc.affected_dtr_ids ?? []).join(', ') || '—'}</td>
                    <td className="text-white/80 text-xs">
                      {fmt(inc.affected_meter_count)} / {fmt(inc.restored_meter_count ?? 0)}
                    </td>
                    <td className="text-white/70 text-xs">
                      {inc.confidence_pct != null ? `${fmt(inc.confidence_pct, 1)}%` : '—'}
                    </td>
                    <td className="text-white/40 text-xs">{fmtTime(inc.opened_at)}</td>
                    <td className="text-white/50 text-xs">{duration}</td>
                    <td>
                      <Link
                        to={`/outages/${inc.id}`}
                        className="text-accent-blue hover:text-white flex items-center gap-1 text-xs"
                      >
                        View <ChevronRight size={12} />
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
