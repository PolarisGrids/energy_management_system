/**
 * AlertsTab — live alarm feed with optional filtering.
 *
 * Uses the existing /api/v1/alarms endpoint (same source as the LV alerts
 * view) but presented in the Alert-Management navigation context. A future
 * enhancement would join against alarm_rule_firings to show which rule
 * triggered each notification, but we already surface priority in the feed.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Bell, CheckCheck, XCircle, Filter, RefreshCw, AlertTriangle,
} from 'lucide-react'

import { alarmsAPI } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import useAuthStore from '@/stores/authStore'

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }

export default function AlertsTab() {
  const toast = useToast()
  const { user } = useAuthStore()
  const [alarms, setAlarms] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState({ status: 'active', severity: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (filter.status) params.status = filter.status
      if (filter.severity) params.severity = filter.severity
      const { data } = await alarmsAPI.list(params)
      setAlarms((data || []).sort((a, b) =>
        (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
      ))
    } catch (err) {
      toast.error('Failed to load alerts', err?.response?.data?.detail ?? err?.message)
    } finally {
      setLoading(false)
    }
  }, [filter, toast])

  useEffect(() => { load() }, [load])

  const counts = useMemo(() => alarms.reduce((acc, a) => {
    acc[a.severity] = (acc[a.severity] || 0) + 1
    return acc
  }, {}), [alarms])

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

  return (
    <div className="space-y-3">
      {/* KPI strip */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { key: 'critical', label: 'Critical', color: '#E94B4B' },
          { key: 'high',     label: 'High',     color: '#F97316' },
          { key: 'medium',   label: 'Medium',   color: '#F59E0B' },
          { key: 'low',      label: 'Low',      color: '#3B82F6' },
          { key: 'info',     label: 'Info',     color: '#6B7280' },
        ].map(b => (
          <div key={b.key} className="glass-card p-3 flex items-center gap-2">
            <AlertTriangle size={14} style={{ color: b.color }} />
            <div>
              <div className="text-white font-black" style={{ fontSize: 20 }}>{counts[b.key] ?? 0}</div>
              <div className="text-white/50" style={{ fontSize: 11 }}>{b.label}</div>
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
        <button onClick={load} className="btn-secondary py-2 px-3 ml-auto" style={{ fontSize: 12 }}>
          <RefreshCw size={12} className={`inline mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Type</th>
              <th>Title</th>
              <th>Meter</th>
              <th>Value</th>
              <th>Triggered</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center py-8 text-white/40">Loading alerts…</td></tr>
            ) : alarms.length === 0 ? (
              <tr>
                <td colSpan={8} className="text-center py-10 text-white/40">
                  <Bell size={28} className="mx-auto mb-2 opacity-40" />
                  <div>No alerts matching filter</div>
                </td>
              </tr>
            ) : alarms.map(a => (
              <tr key={a.id}>
                <td><span className={`badge-${a.severity}`}>{a.severity}</span></td>
                <td className="text-accent-blue" style={{ fontSize: 11 }}>{a.alarm_type?.replace(/_/g, ' ')}</td>
                <td className="text-white font-medium" style={{ fontSize: 13 }}>{a.title}</td>
                <td className="text-white/60 text-xs font-mono">{a.meter_serial || '—'}</td>
                <td className="text-white/60 text-xs">{a.value != null ? `${a.value} ${a.unit ?? ''}` : '—'}</td>
                <td className="text-white/40 text-xs">{new Date(a.triggered_at).toLocaleString('en-ZA')}</td>
                <td>
                  <span className={a.status === 'active' ? 'badge-critical' : a.status === 'acknowledged' ? 'badge-medium' : 'badge-ok'}>
                    {a.status}
                  </span>
                </td>
                <td>
                  <div className="flex gap-2">
                    {a.status === 'active' && (
                      <button onClick={() => acknowledge(a.id)} className="text-status-medium hover:text-white" title="Acknowledge">
                        <CheckCheck size={14} />
                      </button>
                    )}
                    {a.status !== 'resolved' && (
                      <button onClick={() => resolve(a.id)} className="text-energy-green hover:text-white" title="Resolve">
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
