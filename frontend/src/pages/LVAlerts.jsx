/**
 * LVAlerts — DTR-scoped alerts view.
 *
 * Re-uses /alarms and filters to alarms attached to a transformer
 * (transformer_id != null) OR of LV-side categories produced by the rule
 * engine for DTR breaches.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Bell, CheckCheck, XCircle, Filter, ArrowLeft, Gauge, RefreshCw,
} from 'lucide-react'
import { alarmsAPI, metersAPI } from '@/services/api'
import useAuthStore from '@/stores/authStore'
import { useToast } from '@/components/ui/Toast'

const LV_ALARM_TYPES = new Set([
  'transformer_overload', 'overvoltage', 'undervoltage', 'overcurrent',
  'reverse_power', 'fault_detected', 'comm_loss',
])

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }

export default function LVAlerts() {
  const { user } = useAuthStore()
  const toast = useToast()
  const [searchParams] = useSearchParams()
  const transformerFilter = searchParams.get('transformer')

  const [alarms, setAlarms] = useState([])
  const [transformers, setTransformers] = useState({})
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState({ status: '', severity: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (filter.status) params.status = filter.status
      if (filter.severity) params.severity = filter.severity
      const { data } = await alarmsAPI.list(params)
      setAlarms(data.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)))
    } catch (err) {
      toast.error('Failed to load alerts', err?.response?.data?.detail ?? err?.message)
    } finally {
      setLoading(false)
    }
  }, [filter, toast])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    metersAPI.transformers()
      .then(({ data }) => {
        const m = {}
        for (const t of data || []) m[t.id] = t
        setTransformers(m)
      })
      .catch(() => {})
  }, [])

  const lvAlarms = useMemo(() => {
    return alarms.filter(a => {
      const isLv = a.transformer_id != null || LV_ALARM_TYPES.has(a.alarm_type)
      if (!isLv) return false
      if (transformerFilter && String(a.transformer_id) !== String(transformerFilter)) return false
      return true
    })
  }, [alarms, transformerFilter])

  const counts = lvAlarms.reduce((acc, a) => {
    acc[a.status] = (acc[a.status] || 0) + 1
    return acc
  }, {})

  const acknowledge = async (id) => {
    try {
      await alarmsAPI.acknowledge(id, user?.full_name ?? 'Operator')
      toast.success('Alert acknowledged', `Alert #${id}`)
      load()
    } catch (err) {
      toast.error('Failed to acknowledge', err?.response?.data?.detail ?? err?.message)
    }
  }

  const resolve = async (id) => {
    try {
      await alarmsAPI.resolve(id, user?.full_name ?? 'Operator')
      toast.success('Alert resolved', `Alert #${id}`)
      load()
    } catch (err) {
      toast.error('Failed to resolve', err?.response?.data?.detail ?? err?.message)
    }
  }

  const filterLabel = transformerFilter
    ? ` — scoped to ${transformers[transformerFilter]?.name || `Transformer ${transformerFilter}`}`
    : ''

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Link to="/sensors" className="btn-secondary p-2" title="Back to sensors">
            <ArrowLeft size={14} />
          </Link>
          <div>
            <h1 className="text-white font-black" style={{ fontSize: 22 }}>LV Alerts{filterLabel}</h1>
            <p className="text-white/40" style={{ fontSize: 13 }}>
              Distribution-transformer alarms from the rule engine and HES stream
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/sensors/rules" className="btn-secondary py-2 px-3" style={{ fontSize: 12 }}>
            <Gauge size={12} className="inline mr-1" /> Manage rules
          </Link>
          <button onClick={load} className="btn-secondary py-2 px-3" style={{ fontSize: 12 }}>
            <RefreshCw size={12} className={`inline mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Active',       key: 'active',       color: '#E94B4B' },
          { label: 'Acknowledged', key: 'acknowledged', color: '#F59E0B' },
          { label: 'Resolved',     key: 'resolved',     color: '#02C9A8' },
        ].map(({ label, key, color }) => (
          <div key={key} className="glass-card p-4 flex items-center gap-3">
            <Bell size={18} style={{ color }} />
            <div>
              <div className="text-white font-black" style={{ fontSize: 26 }}>{counts[key] ?? 0}</div>
              <div className="text-white/50" style={{ fontSize: 12 }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="glass-card p-3 flex items-center gap-3">
        <Filter size={14} className="text-accent-blue" />
        <select
          value={filter.status}
          onChange={(e) => setFilter({ ...filter, status: e.target.value })}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
        >
          <option value="">All status</option>
          <option value="active">Active</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
        </select>
        <select
          value={filter.severity}
          onChange={(e) => setFilter({ ...filter, severity: e.target.value })}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
        >
          <option value="">All severity</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
          <option value="info">Info</option>
        </select>
        <span className="ml-auto text-white/40 text-sm">{lvAlarms.length} alerts</span>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Type</th>
              <th>Title</th>
              <th>Transformer</th>
              <th>Value</th>
              <th>Triggered</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center py-8 text-white/40">Loading alerts…</td></tr>
            ) : lvAlarms.length === 0 ? (
              <tr>
                <td colSpan={8} className="text-center py-10 text-white/40">
                  <Bell size={28} className="mx-auto mb-2 opacity-40" />
                  <div>No LV alerts matching filter</div>
                </td>
              </tr>
            ) : lvAlarms.map(a => (
              <tr key={a.id}>
                <td><span className={`badge-${a.severity}`}>{a.severity}</span></td>
                <td className="text-accent-blue" style={{ fontSize: 11 }}>{a.alarm_type?.replace(/_/g, ' ')}</td>
                <td className="text-white font-medium" style={{ fontSize: 13 }}>{a.title}</td>
                <td className="text-white/60 text-xs">
                  {a.transformer_id
                    ? (transformers[a.transformer_id]?.name || `TX-${a.transformer_id}`)
                    : '—'}
                </td>
                <td className="text-white/60 text-xs">
                  {a.value != null ? `${a.value} ${a.unit ?? ''}` : '—'}
                </td>
                <td className="text-white/40 text-xs">{new Date(a.triggered_at).toLocaleString('en-ZA')}</td>
                <td><span className={a.status === 'active' ? 'badge-critical' : a.status === 'acknowledged' ? 'badge-medium' : 'badge-ok'}>{a.status}</span></td>
                <td>
                  <div className="flex gap-2">
                    {a.status === 'active' && (
                      <button onClick={() => acknowledge(a.id)} className="text-status-medium hover:text-white transition-colors" title="Acknowledge">
                        <CheckCheck size={14} />
                      </button>
                    )}
                    {a.status !== 'resolved' && (
                      <button onClick={() => resolve(a.id)} className="text-energy-green hover:text-white transition-colors" title="Resolve">
                        <XCircle size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
