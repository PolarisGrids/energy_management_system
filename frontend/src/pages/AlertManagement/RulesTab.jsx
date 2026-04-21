/**
 * RulesTab — alarm rule list + creation targeting any existing VOG.
 *
 * Differences vs LVAlertRules (which still exists for the sensor track):
 *   - Group is chosen from the dropdown of ALL existing VOGs (consumer +
 *     feeder + DTR groups), not auto-created per-rule.
 *   - Channels now include SMS (simulated via LogOnlySender when TWILIO_ENABLED=false).
 *   - Recipients are free-text, allowing comma-separated lists.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  Plus, Trash2, Power, RefreshCw, Bell, Mail, Monitor, MessageSquare, Check,
} from 'lucide-react'

import { alarmRulesAPI, groupsAPI } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Modal from '@/components/ui/Modal'

const ALARM_TYPES = [
  { value: 'any',                   label: 'Any alarm on the group' },
  { value: 'outage',                label: 'Power-cut / outage' },
  { value: 'power_failure',         label: 'Power failure' },
  { value: 'undervoltage',          label: 'Under-voltage' },
  { value: 'overvoltage',           label: 'Over-voltage' },
  { value: 'overcurrent',           label: 'Over-current' },
  { value: 'reverse_power',         label: 'Reverse power flow' },
  { value: 'tamper',                label: 'Tamper detected' },
  { value: 'transformer_overload',  label: 'Transformer overload' },
  { value: 'comm_loss',             label: 'Communication loss' },
  { value: 'fault_detected',        label: 'Fault detected' },
]

const SEVERITY_LEVELS = [
  { value: 'critical', label: 'Critical' },
  { value: 'high',     label: 'High' },
  { value: 'medium',   label: 'Medium' },
  { value: 'low',      label: 'Low' },
  { value: 'info',     label: 'Info' },
]
const SEVERITY_RANK = { info: 0, low: 1, medium: 2, high: 3, critical: 4 }
function severityAtLeast(min) {
  const m = SEVERITY_RANK[min] ?? 0
  return SEVERITY_LEVELS.map(s => s.value).filter(v => (SEVERITY_RANK[v] ?? 0) >= m)
}

const CHANNEL_META = {
  in_app: { label: 'In-app',  icon: Monitor,         hint: 'Operator console notification' },
  email:  { label: 'Email',   icon: Mail,            hint: 'SMTP / SES — currently simulated' },
  sms:    { label: 'SMS',     icon: MessageSquare,   hint: 'Twilio — currently simulated' },
}

function buildCondition({ alarmTypes, minSeverity, duration }) {
  // If operator picked 'any' or empty, fall back to severity floor.
  if (alarmTypes.length && !alarmTypes.includes('any')) {
    return {
      source: 'alarm_event',
      field: 'alarm_type',
      op: alarmTypes.length === 1 ? '==' : 'in',
      value: alarmTypes.length === 1 ? alarmTypes[0] : alarmTypes,
      duration_seconds: duration || 0,
    }
  }
  return {
    source: 'alarm_event',
    field: 'severity',
    op: 'in',
    value: severityAtLeast(minSeverity || 'info'),
    duration_seconds: duration || 0,
  }
}

function describeCondition(cond) {
  if (!cond) return '—'
  const v = Array.isArray(cond.value) ? cond.value.join(' | ') : cond.value
  const dur = cond.duration_seconds > 0 ? ` for ≥${cond.duration_seconds}s` : ''
  return `${cond.field} ${cond.op} ${v}${dur}`
}

export default function RulesTab() {
  const toast = useToast()
  const [rules, setRules] = useState([])
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rRes, gRes] = await Promise.all([alarmRulesAPI.list(), groupsAPI.list()])
      setRules(rRes.data || [])
      setGroups(gRes.data || [])
    } catch (err) {
      toast.error('Failed to load rules', err?.response?.data?.detail ?? err?.message)
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const toggleActive = async (rule) => {
    try {
      await alarmRulesAPI.update(rule.id, { active: !rule.active })
      toast.success(rule.active ? 'Rule disabled' : 'Rule enabled', rule.name)
      load()
    } catch (err) {
      toast.error('Failed to update rule', err?.response?.data?.detail ?? err?.message)
    }
  }

  const remove = async (rule) => {
    if (!window.confirm(`Delete rule "${rule.name}"?`)) return
    try {
      await alarmRulesAPI.remove(rule.id)
      toast.success('Rule deleted', rule.name)
      load()
    } catch (err) {
      toast.error('Failed to delete rule', err?.response?.data?.detail ?? err?.message)
    }
  }

  const groupNameById = (id) => groups.find(g => g.id === id)?.name || id?.slice(0, 8) || '—'

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-white/50 text-xs">
          {rules.length} rule(s) — each bound to a virtual group and one or more notification channels
        </div>
        <button onClick={() => setCreateOpen(true)} className="btn-primary py-2 px-3" style={{ fontSize: 12 }}>
          <Plus size={12} className="inline mr-1" /> New rule
        </button>
      </div>

      <div className="glass-card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Name</th>
              <th>Group</th>
              <th>Condition</th>
              <th>Priority</th>
              <th>Channels</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="text-center py-8 text-white/40">Loading…</td></tr>
            ) : rules.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-10 text-white/40">
                  <Bell size={28} className="mx-auto mb-2 opacity-40" />
                  <div>No rules yet</div>
                  <div className="text-xs mt-1">Create a rule — or use "Load default groups" to seed starters.</div>
                </td>
              </tr>
            ) : rules.map(r => {
              const channels = (r.action?.channels || []).map(c => c.type)
              return (
                <tr key={r.id}>
                  <td>
                    <span className={r.active ? 'badge-ok' : 'badge-medium'} style={{ textTransform: 'uppercase' }}>
                      {r.active ? 'Active' : 'Paused'}
                    </span>
                  </td>
                  <td>
                    <div className="text-white font-medium" style={{ fontSize: 13 }}>{r.name}</div>
                    {r.description && <div className="text-white/40" style={{ fontSize: 11 }}>{r.description}</div>}
                  </td>
                  <td className="text-white/60" style={{ fontSize: 12 }}>{groupNameById(r.group_id)}</td>
                  <td className="text-white/60 font-mono" style={{ fontSize: 11 }}>{describeCondition(r.condition)}</td>
                  <td className="text-white/60" style={{ fontSize: 12 }}>P{r.priority}</td>
                  <td>
                    <div className="flex gap-1">
                      {channels.map(ch => {
                        const meta = CHANNEL_META[ch]
                        if (!meta) return null
                        const Icon = meta.icon
                        return <Icon key={ch} size={12} className="text-accent-blue" title={meta.label} />
                      })}
                    </div>
                  </td>
                  <td>
                    <div className="flex gap-2">
                      <button
                        onClick={() => toggleActive(r)}
                        className={r.active ? 'text-status-medium hover:text-white' : 'text-energy-green hover:text-white'}
                        title={r.active ? 'Disable' : 'Enable'}
                      >
                        <Power size={14} />
                      </button>
                      <button
                        onClick={() => remove(r)}
                        className="text-status-critical hover:text-white transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <CreateRuleModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={() => { setCreateOpen(false); load() }}
        groups={groups}
      />
    </div>
  )
}


function CreateRuleModal({ open, onClose, onSaved, groups }) {
  const toast = useToast()
  const [groupId, setGroupId] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [alarmTypes, setAlarmTypes] = useState(['outage'])
  const [minSeverity, setMinSeverity] = useState('high')
  const [duration, setDuration] = useState(0)
  const [priority, setPriority] = useState(2)
  const [channels, setChannels] = useState(['in_app', 'email'])
  const [recipients, setRecipients] = useState({ email: '', sms: '', in_app: 'operations-desk' })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setGroupId(groups[0]?.id || '')
    setName('')
    setDescription('')
    setAlarmTypes(['outage'])
    setMinSeverity('high')
    setDuration(0)
    setPriority(2)
    setChannels(['in_app', 'email'])
    setRecipients({ email: '', sms: '', in_app: 'operations-desk' })
  }, [open, groups])

  const toggleAlarmType = (t) => setAlarmTypes(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t])
  const toggleChannel = (c) => setChannels(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c])

  const canSave = groupId && name.trim() && channels.length > 0

  const submit = async () => {
    if (!canSave) return
    setSaving(true)
    try {
      const channelCfg = channels.map(type => ({
        type,
        recipients: (recipients[type] || '').split(',').map(s => s.trim()).filter(Boolean),
      }))
      await alarmRulesAPI.create({
        group_id: groupId,
        name: name.trim(),
        description: description.trim() || undefined,
        condition: buildCondition({ alarmTypes, minSeverity, duration }),
        action: {
          channels: channelCfg,
          priority,
        },
        priority,
        active: true,
        dedup_window_seconds: 300,
      })
      toast.success('Rule created', name.trim())
      onSaved?.()
    } catch (err) {
      toast.error('Failed to create rule', err?.response?.data?.detail ?? err?.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create Alarm Rule"
      size="lg"
      footer={
        <div className="flex justify-end gap-2 w-full">
          <button onClick={onClose} className="btn-secondary py-2 px-4" style={{ fontSize: 13 }}>Cancel</button>
          <button
            onClick={submit}
            disabled={!canSave || saving}
            className="btn-primary py-2 px-4"
            style={{ fontSize: 13, opacity: !canSave || saving ? 0.5 : 1 }}
          >
            {saving ? <><RefreshCw size={12} className="animate-spin inline mr-2" />Saving…</> : <><Check size={12} className="inline mr-2" />Create rule</>}
          </button>
        </div>
      }
    >
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <label className="block col-span-2">
            <span className="text-white/50" style={{ fontSize: 11 }}>RULE NAME</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Soweto hospital power-cut"
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            />
          </label>

          <label className="block col-span-2">
            <span className="text-white/50" style={{ fontSize: 11 }}>TARGET GROUP</span>
            <select
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            >
              <option value="" disabled>Pick a virtual group…</option>
              {groups.map(g => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </label>

          <label className="block col-span-2">
            <span className="text-white/50" style={{ fontSize: 11 }}>DESCRIPTION (optional)</span>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="When this fires and what to do"
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            />
          </label>

          <div className="col-span-2">
            <div className="text-white/50 mb-1.5" style={{ fontSize: 11 }}>TRIGGER ON ALARM TYPE</div>
            <div className="flex gap-2 flex-wrap">
              {ALARM_TYPES.map(t => {
                const on = alarmTypes.includes(t.value)
                return (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => toggleAlarmType(t.value)}
                    className="px-2.5 py-1 rounded-lg text-xs"
                    style={{
                      background: on ? 'rgba(96,165,250,0.15)' : 'rgba(255,255,255,0.03)',
                      border: `1px solid ${on ? '#60A5FA60' : 'rgba(255,255,255,0.08)'}`,
                      color: on ? '#60A5FA' : 'rgba(255,255,255,0.55)',
                    }}
                  >
                    {t.label}
                  </button>
                )
              })}
            </div>
          </div>

          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>MIN SEVERITY (fallback if alarm-type is "any")</span>
            <select
              value={minSeverity}
              onChange={(e) => setMinSeverity(e.target.value)}
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            >
              {SEVERITY_LEVELS.map(s => <option key={s.value} value={s.value}>At or above {s.label}</option>)}
            </select>
          </label>

          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>SUSTAIN (seconds)</span>
            <input
              type="number" min={0}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              placeholder="0 = fire on first occurrence"
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            />
          </label>

          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>PRIORITY (1 = highest)</span>
            <select
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            >
              {[1, 2, 3, 4, 5].map(p => (
                <option key={p} value={p}>P{p}{p === 1 ? ' — Critical' : p === 2 ? ' — High' : p === 3 ? ' — Warning' : p === 4 ? ' — Low' : ' — Info'}</option>
              ))}
            </select>
          </label>

          <div>
            <div className="text-white/50 mb-1.5" style={{ fontSize: 11 }}>NOTIFICATION CHANNELS</div>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(CHANNEL_META).map(([id, meta]) => {
                const Icon = meta.icon
                const on = channels.includes(id)
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => toggleChannel(id)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg"
                    style={{
                      background: on ? 'rgba(96,165,250,0.15)' : 'rgba(255,255,255,0.03)',
                      border: `1px solid ${on ? '#60A5FA60' : 'rgba(255,255,255,0.08)'}`,
                      color: on ? '#60A5FA' : 'rgba(255,255,255,0.55)',
                    }}
                    title={meta.hint}
                  >
                    <Icon size={12} />
                    <span className="text-xs">{meta.label}</span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {channels.length > 0 && (
          <div className="space-y-2 bg-white/3 rounded-lg p-3">
            <div className="text-white/50" style={{ fontSize: 11 }}>
              RECIPIENTS (comma-separated)
            </div>
            {channels.map(ch => {
              const meta = CHANNEL_META[ch]
              const Icon = meta.icon
              return (
                <div key={ch} className="flex items-center gap-2">
                  <div className="w-24 flex items-center gap-1 text-white/60" style={{ fontSize: 12 }}>
                    <Icon size={11} /> {meta.label}
                  </div>
                  <input
                    value={recipients[ch] || ''}
                    onChange={(e) => setRecipients(prev => ({ ...prev, [ch]: e.target.value }))}
                    placeholder={
                      ch === 'email' ? 'noc@eskom.co.za, oncall@eskom.co.za' :
                      ch === 'sms' ? '+27831112222, +27841113333' :
                      'operations-desk'
                    }
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-white outline-none text-xs"
                  />
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Modal>
  )
}
