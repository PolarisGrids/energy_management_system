/**
 * SubscriptionsTab — read-only view of who gets paged for which priority.
 *
 * Rolls up every rule into a priority → channel → recipients matrix so
 * an operator can answer "for a P1 incident on Critical Customers, who's
 * on the line?" without opening each rule individually.
 */
import { useCallback, useEffect, useState } from 'react'
import { Bell, Mail, MessageSquare, Monitor, RefreshCw } from 'lucide-react'

import { alarmRulesAPI, groupsAPI } from '@/services/api'
import { useToast } from '@/components/ui/Toast'

const CHANNEL_META = {
  in_app: { label: 'In-app', icon: Monitor,       color: '#60A5FA' },
  email:  { label: 'Email',  icon: Mail,          color: '#02C9A8' },
  sms:    { label: 'SMS',    icon: MessageSquare, color: '#F59E0B' },
}

const PRIORITY_META = {
  1: { label: 'P1 — Critical', color: '#E94B4B' },
  2: { label: 'P2 — High',     color: '#F97316' },
  3: { label: 'P3 — Warning',  color: '#F59E0B' },
  4: { label: 'P4 — Low',      color: '#3B82F6' },
  5: { label: 'P5 — Info',     color: '#6B7280' },
}

export default function SubscriptionsTab() {
  const toast = useToast()
  const [rules, setRules] = useState([])
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rRes, gRes] = await Promise.all([alarmRulesAPI.list(), groupsAPI.list()])
      setRules(rRes.data || [])
      setGroups(gRes.data || [])
    } catch (err) {
      toast.error('Failed to load subscriptions', err?.response?.data?.detail ?? err?.message)
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  // Build priority → [{rule, group, channels}]
  const byPriority = {}
  for (const r of rules) {
    const p = r.priority || 3
    byPriority[p] = byPriority[p] || []
    byPriority[p].push(r)
  }
  const priorities = Object.keys(byPriority).map(Number).sort((a, b) => a - b)
  const groupName = (id) => groups.find(g => g.id === id)?.name || 'Unknown group'

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-white/50 text-xs">
          Priority-driven paging map — which channels/recipients are notified for each rule.
        </div>
        <button onClick={load} className="btn-secondary py-2 px-3" style={{ fontSize: 12 }}>
          <RefreshCw size={12} className={`inline mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="glass-card p-6 text-white/40 text-sm">Loading subscriptions…</div>
      ) : rules.length === 0 ? (
        <div className="glass-card p-10 text-white/40 text-center">
          <Bell size={28} className="mx-auto mb-2 opacity-40" />
          <div>No alarm rules exist yet</div>
          <div className="text-xs mt-1">Create a rule under the Rules tab or load the default groups to populate this view.</div>
        </div>
      ) : (
        priorities.map(p => {
          const meta = PRIORITY_META[p] || PRIORITY_META[3]
          const rulesInP = byPriority[p]
          return (
            <div key={p} className="glass-card overflow-hidden">
              <div
                className="flex items-center gap-2 px-4 py-2 border-b border-white/5"
                style={{ background: `${meta.color}15` }}
              >
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ background: meta.color }}
                />
                <div className="text-white font-bold" style={{ fontSize: 13 }}>{meta.label}</div>
                <div className="text-white/40 text-xs ml-2">{rulesInP.length} rule(s)</div>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Rule</th>
                    <th>Group</th>
                    <th>Channels</th>
                    <th>Recipients</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rulesInP.map(r => {
                    const channels = r.action?.channels || []
                    return (
                      <tr key={r.id}>
                        <td>
                          <div className="text-white font-medium" style={{ fontSize: 13 }}>{r.name}</div>
                          {r.description && <div className="text-white/40" style={{ fontSize: 11 }}>{r.description}</div>}
                        </td>
                        <td className="text-white/60" style={{ fontSize: 12 }}>{groupName(r.group_id)}</td>
                        <td>
                          <div className="flex gap-1">
                            {channels.map((c, i) => {
                              const cm = CHANNEL_META[c.type]
                              if (!cm) return (
                                <span key={i} className="text-white/30 text-xs">{c.type}</span>
                              )
                              const Icon = cm.icon
                              return (
                                <span
                                  key={i}
                                  className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs"
                                  style={{ background: `${cm.color}20`, color: cm.color }}
                                >
                                  <Icon size={10} /> {cm.label}
                                </span>
                              )
                            })}
                          </div>
                        </td>
                        <td className="text-white/60" style={{ fontSize: 11 }}>
                          {channels.length === 0 ? '—' :
                            channels.map((c, i) => (
                              <div key={i}>
                                <span className="text-white/40">{c.type}:</span>{' '}
                                {(c.recipients || []).join(', ') || (c.recipients?.length === 0 ? '—' : '—')}
                              </div>
                            ))
                          }
                        </td>
                        <td>
                          <span className={r.active ? 'badge-ok' : 'badge-medium'} style={{ textTransform: 'uppercase' }}>
                            {r.active ? 'Active' : 'Paused'}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        })
      )}
    </div>
  )
}
