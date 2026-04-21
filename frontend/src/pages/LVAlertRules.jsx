/**
 * LVAlertRules — list + create alarm rules scoped to LV/DTR transformers.
 *
 * Each rule is persisted via the spec-018 W4.T4 alarm-rule engine:
 *   1. POST /api/v1/groups      — materialise a VirtualObjectGroup with the
 *                                 selected transformers (hierarchy.dtr_ids).
 *   2. POST /api/v1/alarm-rules — condition AST (source, field, op, value,
 *                                 duration_seconds) + action (channels).
 *
 * The rule engine evaluates group membership on the alarms stream, so a user
 * never touches the group abstraction directly — it is created in the
 * background on save.
 */
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import {
  Bell, Plus, Trash2, Power, RefreshCw, ArrowLeft, Check,
  Mail, Monitor,
} from 'lucide-react'
import { alarmRulesAPI, groupsAPI, metersAPI } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Modal from '@/components/ui/Modal'

// Alarm types the rule engine can watch. Mirrors app/models/alarm.py AlarmType.
const ALARM_TYPES = [
  { value: 'transformer_overload', label: 'Transformer overload (temp/load)' },
  { value: 'overvoltage',          label: 'Over-voltage' },
  { value: 'undervoltage',         label: 'Under-voltage' },
  { value: 'overcurrent',          label: 'Over-current' },
  { value: 'reverse_power',        label: 'Reverse power flow' },
  { value: 'tamper',               label: 'Tamper' },
  { value: 'outage',               label: 'Outage' },
  { value: 'comm_loss',            label: 'Communication loss' },
  { value: 'fault_detected',       label: 'Fault detected' },
  { value: 'any',                  label: 'Any alarm on this DTR' },
]

const SEVERITY_LEVELS = [
  { value: 'critical', label: 'Critical' },
  { value: 'high',     label: 'High' },
  { value: 'medium',   label: 'Medium' },
  { value: 'low',      label: 'Low' },
  { value: 'info',     label: 'Info' },
]
const SEVERITY_RANK = { info: 0, low: 1, medium: 2, high: 3, critical: 4 }

function severityAtLeast(minSeverity) {
  const min = SEVERITY_RANK[minSeverity] ?? 0
  return SEVERITY_LEVELS.map(s => s.value).filter(v => (SEVERITY_RANK[v] ?? 0) >= min)
}

function buildCondition({ alarmType, minSeverity, durationSeconds }) {
  if (minSeverity) {
    return {
      source: 'alarm_event',
      field: 'severity',
      op: 'in',
      value: severityAtLeast(minSeverity),
      duration_seconds: durationSeconds || 0,
    }
  }
  if (alarmType && alarmType !== 'any') {
    return {
      source: 'alarm_event',
      field: 'alarm_type',
      op: '==',
      value: alarmType,
      duration_seconds: durationSeconds || 0,
    }
  }
  return {
    source: 'alarm_event',
    field: 'severity',
    op: 'in',
    value: SEVERITY_LEVELS.map(s => s.value),
    duration_seconds: durationSeconds || 0,
  }
}

// ─── Create-rule modal ───────────────────────────────────────────────────────

function CreateRuleModal({ open, onClose, onSaved, transformers, presetTransformerId }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedTxIds, setSelectedTxIds] = useState([])
  const [alarmType, setAlarmType] = useState('transformer_overload')
  const [minSeverity, setMinSeverity] = useState('high')
  const [duration, setDuration] = useState(0)
  const [priority, setPriority] = useState(3)
  const [channels, setChannels] = useState(['in_app'])
  const [emailRecipient, setEmailRecipient] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName('')
      setDescription('')
      setSelectedTxIds(presetTransformerId ? [Number(presetTransformerId)] : [])
      setAlarmType('transformer_overload')
      setMinSeverity('high')
      setDuration(0)
      setPriority(3)
      setChannels(['in_app'])
      setEmailRecipient('')
    }
  }, [open, presetTransformerId])

  const toggleTx = (id) => {
    setSelectedTxIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }
  const toggleChannel = (ch) => {
    setChannels(prev => prev.includes(ch) ? prev.filter(x => x !== ch) : [...prev, ch])
  }

  const canSave = name.trim() && selectedTxIds.length > 0 && channels.length > 0 &&
    (!channels.includes('email') || emailRecipient.trim())

  const submit = async () => {
    if (!canSave) return
    setSaving(true)
    try {
      const selectedTxNames = selectedTxIds
        .map(id => transformers.find(t => t.id === id)?.name)
        .filter(Boolean)
      const { data: group } = await groupsAPI.create({
        name: `lv-rule-${name.trim()}`.slice(0, 200),
        description: `Auto-generated group for alarm rule "${name.trim()}"`,
        selector: { hierarchy: { dtr_ids: selectedTxNames } },
      })

      const action = { channels, priority }
      if (channels.includes('email')) action.email_recipient = emailRecipient.trim()
      await alarmRulesAPI.create({
        group_id: group.id,
        name: name.trim(),
        description: description.trim() || undefined,
        condition: buildCondition({ alarmType, minSeverity, durationSeconds: duration }),
        action,
        priority,
        active: true,
        dedup_window_seconds: 300,
      })
      toast.success('Alert rule created', `"${name.trim()}" is active on ${selectedTxIds.length} DTR${selectedTxIds.length > 1 ? 's' : ''}.`)
      onSaved?.()
      onClose?.()
    } catch (err) {
      toast.error('Failed to create rule', err?.response?.data?.detail ?? err?.message ?? 'Unknown error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create LV Alert Rule"
      size="lg"
      footer={
        <div className="flex justify-end gap-2">
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
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3">
          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>RULE NAME</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. DTR-5 winding overheat"
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm focus:border-accent-blue/50"
            />
          </label>
          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>DESCRIPTION (optional)</span>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="When this should fire and what to do about it"
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm focus:border-accent-blue/50"
            />
          </label>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-white/50" style={{ fontSize: 11 }}>TRANSFORMERS (DTRs)</span>
            <span className="text-white/30" style={{ fontSize: 10 }}>{selectedTxIds.length} selected</span>
          </div>
          <div className="max-h-48 overflow-y-auto bg-white/3 rounded-lg border border-white/5 p-2">
            {(transformers || []).length === 0 ? (
              <div className="text-white/30 text-sm p-3">No transformers available</div>
            ) : transformers.map(t => {
              const checked = selectedTxIds.includes(t.id)
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => toggleTx(t.id)}
                  className="flex items-center gap-2 w-full px-2 py-1.5 rounded hover:bg-white/5 text-left"
                >
                  <span
                    className="w-4 h-4 rounded border flex items-center justify-center shrink-0"
                    style={{
                      borderColor: checked ? '#60A5FA' : 'rgba(255,255,255,0.2)',
                      background: checked ? 'rgba(96,165,250,0.2)' : 'transparent',
                    }}
                  >
                    {checked && <Check size={10} style={{ color: '#60A5FA' }} />}
                  </span>
                  <span className="text-white text-sm">{t.name}</span>
                  <span className="text-white/30 text-xs ml-auto">
                    {t.latitude?.toFixed(3)}, {t.longitude?.toFixed(3)}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>ALARM TYPE</span>
            <select
              value={alarmType}
              onChange={(e) => setAlarmType(e.target.value)}
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            >
              {ALARM_TYPES.map(a => (<option key={a.value} value={a.value}>{a.label}</option>))}
            </select>
          </label>
          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>MINIMUM SEVERITY</span>
            <select
              value={minSeverity}
              onChange={(e) => setMinSeverity(e.target.value)}
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            >
              <option value="">Any</option>
              {SEVERITY_LEVELS.map(s => (<option key={s.value} value={s.value}>At or above {s.label}</option>))}
            </select>
          </label>
          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>SUSTAIN (seconds)</span>
            <input
              type="number"
              min={0}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              placeholder="0 = fire on first occurrence"
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            />
          </label>
          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>PRIORITY (1=highest)</span>
            <select
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            >
              {[1, 2, 3, 4, 5].map(p => (<option key={p} value={p}>P{p}</option>))}
            </select>
          </label>
        </div>

        <div>
          <div className="text-white/50 mb-1.5" style={{ fontSize: 11 }}>NOTIFICATION CHANNELS</div>
          <div className="flex gap-2">
            {[
              { id: 'in_app', label: 'In-app',  Icon: Monitor },
              { id: 'email',  label: 'Email',   Icon: Mail },
            ].map(({ id, label, Icon }) => {
              const on = channels.includes(id)
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => toggleChannel(id)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg transition-colors"
                  style={{
                    background: on ? 'rgba(96,165,250,0.15)' : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${on ? '#60A5FA60' : 'rgba(255,255,255,0.08)'}`,
                    color: on ? '#60A5FA' : 'rgba(255,255,255,0.5)',
                  }}
                >
                  <Icon size={12} />
                  <span className="text-sm">{label}</span>
                </button>
              )
            })}
          </div>
          {channels.includes('email') && (
            <input
              value={emailRecipient}
              onChange={(e) => setEmailRecipient(e.target.value)}
              placeholder="oncall@eskom.co.za"
              className="w-full mt-2 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
            />
          )}
        </div>
      </div>
    </Modal>
  )
}

// ─── Main page ───────────────────────────────────────────────────────────────

export default function LVAlertRules() {
  const toast = useToast()
  const [searchParams] = useSearchParams()
  const presetTransformerId = searchParams.get('transformer')

  const [rules, setRules] = useState([])
  const [transformers, setTransformers] = useState([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)

  const load = useCallback(async () => {
    try {
      const [rRes, tRes] = await Promise.all([
        alarmRulesAPI.list(),
        metersAPI.transformers(),
      ])
      setRules(rRes.data || [])
      setTransformers(tRes.data || [])
    } catch (err) {
      toast.error('Failed to load rules', err?.response?.data?.detail ?? err?.message ?? 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (searchParams.get('create') === '1' || presetTransformerId) {
      setCreateOpen(true)
    }
  }, [searchParams, presetTransformerId])

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
    if (!window.confirm(`Delete rule "${rule.name}"? This cannot be undone.`)) return
    try {
      await alarmRulesAPI.remove(rule.id)
      toast.success('Rule deleted', rule.name)
      load()
    } catch (err) {
      toast.error('Failed to delete rule', err?.response?.data?.detail ?? err?.message)
    }
  }

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Link to="/sensors" className="btn-secondary p-2" title="Back to sensors">
            <ArrowLeft size={14} />
          </Link>
          <div>
            <h1 className="text-white font-black" style={{ fontSize: 22 }}>LV Alert Rules</h1>
            <p className="text-white/40" style={{ fontSize: 13 }}>
              Notification rules scoped to distribution transformers (DTR meters)
            </p>
          </div>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="btn-primary py-2 px-4"
          style={{ fontSize: 13 }}
        >
          <Plus size={14} className="inline mr-2" /> New rule
        </button>
      </div>

      {/* Rule table */}
      <div className="glass-card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Name</th>
              <th>Condition</th>
              <th>Priority</th>
              <th>Channels</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="text-center py-8 text-white/40">Loading rules…</td></tr>
            ) : rules.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-10 text-white/40">
                  <Bell size={28} className="mx-auto mb-2 opacity-40" />
                  <div>No LV alert rules yet</div>
                  <div className="text-xs mt-1">Click "New rule" to be notified when DTRs breach thresholds.</div>
                </td>
              </tr>
            ) : rules.map(r => {
              const cond = r.condition || {}
              const channels = r.action?.channels || []
              return (
                <tr key={r.id}>
                  <td>
                    <span className={r.active ? 'badge-ok' : 'badge-medium'} style={{ textTransform: 'uppercase' }}>
                      {r.active ? 'Active' : 'Paused'}
                    </span>
                  </td>
                  <td>
                    <div className="text-white font-medium" style={{ fontSize: 13 }}>{r.name}</div>
                    {r.description && (
                      <div className="text-white/40" style={{ fontSize: 11 }}>{r.description}</div>
                    )}
                  </td>
                  <td className="text-white/60 font-mono" style={{ fontSize: 11 }}>
                    {cond.field} {cond.op} {Array.isArray(cond.value) ? cond.value.join('|') : String(cond.value)}
                    {cond.duration_seconds > 0 && (
                      <span className="text-white/30"> for ≥{cond.duration_seconds}s</span>
                    )}
                  </td>
                  <td className="text-white/60" style={{ fontSize: 12 }}>P{r.priority}</td>
                  <td>
                    <div className="flex gap-1">
                      {channels.includes('in_app') && <Monitor size={12} className="text-accent-blue" title="In-app" />}
                      {channels.includes('email')  && <Mail    size={12} className="text-accent-blue" title="Email" />}
                    </div>
                  </td>
                  <td className="text-white/40" style={{ fontSize: 11 }}>
                    {new Date(r.updated_at).toLocaleString('en-ZA')}
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
        onSaved={load}
        transformers={transformers}
        presetTransformerId={presetTransformerId}
      />
    </div>
  )
}
