import { useState, useEffect } from 'react'
import { Bell, CheckCheck, XCircle, Filter } from 'lucide-react'
import { alarmsAPI } from '@/services/api'
import useAuthStore from '@/stores/authStore'
import { useToast } from '@/components/ui/Toast'

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }

export default function AlarmConsole() {
  const { user } = useAuthStore()
  const toast = useToast()
  const [alarms, setAlarms] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState({ status: '', severity: '' })

  const load = async () => {
    try {
      const params = {}
      if (filter.status) params.status = filter.status
      if (filter.severity) params.severity = filter.severity
      const { data } = await alarmsAPI.list(params)
      setAlarms(data.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)))
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [filter])

  const acknowledge = async (id) => {
    try {
      await alarmsAPI.acknowledge(id, user?.full_name ?? 'Operator')
      toast.success('Alarm acknowledged', `Alarm #${id} marked as acknowledged.`)
      load()
    } catch (err) {
      toast.error(
        'Failed to acknowledge alarm',
        err?.response?.data?.detail ?? err?.message ?? 'Unknown error',
      )
    }
  }

  const resolve = async (id) => {
    try {
      await alarmsAPI.resolve(id, user?.full_name ?? 'Operator')
      toast.success('Alarm resolved', `Alarm #${id} closed.`)
      load()
    } catch (err) {
      toast.error(
        'Failed to resolve alarm',
        err?.response?.data?.detail ?? err?.message ?? 'Unknown error',
      )
    }
  }

  const counts = alarms.reduce((acc, a) => {
    acc[a.status] = (acc[a.status] || 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-5 animate-slide-up">
      {/* Header stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Active', key: 'active', color: '#E94B4B' },
          { label: 'Acknowledged', key: 'acknowledged', color: '#F59E0B' },
          { label: 'Resolved', key: 'resolved', color: '#02C9A8' },
        ].map(({ label, key, color }) => (
          <div key={key} className="glass-card p-5 flex items-center gap-4">
            <Bell size={20} style={{ color }} />
            <div>
              <div className="text-white font-black" style={{ fontSize: 28 }}>{counts[key] ?? 0}</div>
              <div className="text-white/50" style={{ fontSize: 13 }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="glass-card p-4 flex items-center gap-4">
        <Filter size={14} className="text-accent-blue" />
        <select
          value={filter.status}
          onChange={(e) => setFilter({ ...filter, status: e.target.value })}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
        >
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
        </select>
        <select
          value={filter.severity}
          onChange={(e) => setFilter({ ...filter, severity: e.target.value })}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
        >
          <option value="">All Severity</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <span className="ml-auto text-white/40 text-sm">{alarms.length} alarms</span>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Type</th>
              <th>Title</th>
              <th>Meter / Transformer</th>
              <th>Value</th>
              <th>Triggered</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center py-8 text-white/40">Loading alarms…</td></tr>
            ) : alarms.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-8 text-white/40">No alarms found</td></tr>
            ) : alarms.map(a => (
              <tr key={a.id}>
                <td><span className={`badge-${a.severity}`}>{a.severity}</span></td>
                <td className="text-accent-blue text-xs">{a.alarm_type?.replace(/_/g, ' ')}</td>
                <td className="text-white font-medium" style={{ fontSize: 13 }}>{a.title}</td>
                <td className="text-white/50 font-mono text-xs">{a.meter_serial ?? (a.transformer_id ? `TX-${a.transformer_id}` : '—')}</td>
                <td className="text-white/70 text-xs">
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
