/**
 * AppBuilder — spec 018 W4.T8.
 *
 * Persisted AppBuilder surface backed by the backend /apps, /app-rules,
 * /algorithms endpoints. Replaces the earlier hardcoded prototype which
 * held rules/apps/algorithms in component state only.
 *
 * Roles
 *   Publish actions require the `app_builder_publish` role. Until Agent N
 *   wires real RBAC, the frontend forwards the caller's role hint via the
 *   X-User-Role header. Non-admins see the publish button disabled.
 */
import { useEffect, useState, useRef, useMemo, useCallback } from 'react'
import {
  BarChart2, LineChart, Gauge, Map, Bell, Cpu, Table2, Type,
  LayoutDashboard, PlusCircle, Play, Save, Trash2, Edit3, Eye,
  Download, BookOpen, Maximize2, RefreshCw, ChevronDown, ChevronUp,
} from 'lucide-react'
import { appBuilderAPI } from '@/services/api'

// ─── Constants (widget palette + form enums) ──────────────────────────────────
const WIDGET_PALETTE = [
  { id: 'kpi',   name: 'KPI Card',    icon: Gauge,     color: '#02C9A8' },
  { id: 'line',  name: 'Line Chart',  icon: LineChart, color: '#56CCF2' },
  { id: 'bar',   name: 'Bar Chart',   icon: BarChart2, color: '#3C63FF' },
  { id: 'gauge', name: 'Gauge',       icon: Gauge,     color: '#F59E0B' },
  { id: 'map',   name: 'Map View',    icon: Map,       color: '#02C9A8' },
  { id: 'alarm', name: 'Alarm Table', icon: Bell,      color: '#E94B4B' },
  { id: 'der',   name: 'DER Status',  icon: Cpu,       color: '#8B5CF6' },
  { id: 'meter', name: 'Meter Table', icon: Table2,    color: '#ABC7FF' },
  { id: 'text',  name: 'Text Block',  icon: Type,      color: 'rgba(255,255,255,0.5)' },
]

const TRIGGERS = ['Alarm Raised', 'Meter Offline', 'DER Curtailed', 'Voltage Violation', 'Threshold Breach']
const METRICS  = ['Voltage (pu)', 'Current (A)', 'Power (kW)', 'Meter Status', 'Tamper Event', 'Energy (kWh)']
const OPERATORS = ['>', '<', '=', '≠']
const ACTIONS  = ['Send SMS', 'Send Email', 'Send App Notification', 'Execute Command', 'Log Event']
const PRIORITIES = ['Critical', 'High', 'Medium', 'Low']

const slugify = (s) =>
  (s || '').toLowerCase().trim().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 119) || `slug-${Date.now()}`

const userRole = () => {
  try {
    const raw = localStorage.getItem('smoc_user')
    if (!raw) return null
    const u = JSON.parse(raw)
    return (u.role || '').toLowerCase() || null
  } catch { return null }
}

const canPublish = () => {
  const r = userRole()
  return r && ['admin', 'supervisor', 'app_builder_publish'].includes(r)
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function TabBar({ tabs, active, onChange }) {
  return (
    <div style={{
      display: 'flex', gap: 2, marginBottom: 20,
      background: 'rgba(10,54,144,0.2)', borderRadius: 10, padding: 4,
      border: '1px solid rgba(171,199,255,0.1)',
    }}>
      {tabs.map(t => (
        <button key={t} onClick={() => onChange(t)} style={{
          flex: 1, padding: '8px 16px', borderRadius: 8, border: 'none',
          fontWeight: 700, fontSize: 13, cursor: 'pointer', transition: 'all 0.2s',
          background: active === t ? 'linear-gradient(45deg, #11ABBE, #3C63FF)' : 'transparent',
          color: active === t ? '#fff' : 'rgba(255,255,255,0.5)',
        }}>{t}</button>
      ))}
    </div>
  )
}

function SectionLabel({ text }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.35)',
      textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8,
    }}>{text}</div>
  )
}

function StatusBadge({ status }) {
  const map = {
    DRAFT: { color: '#ABC7FF', bg: 'rgba(171,199,255,0.15)' },
    PREVIEW: { color: '#F59E0B', bg: 'rgba(245,158,11,0.15)' },
    PUBLISHED: { color: '#02C9A8', bg: 'rgba(2,201,168,0.15)' },
    ARCHIVED: { color: 'rgba(255,255,255,0.4)', bg: 'rgba(255,255,255,0.05)' },
  }
  const s = map[status] || map.DRAFT
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 10,
      color: s.color, background: s.bg, border: `1px solid ${s.color}44`,
    }}>{status}</span>
  )
}

function Toast({ message, type = 'info', onClose }) {
  useEffect(() => {
    if (!message) return
    const t = setTimeout(onClose, 4000)
    return () => clearTimeout(t)
  }, [message, onClose])
  if (!message) return null
  const color = type === 'error' ? '#E94B4B' : type === 'success' ? '#02C9A8' : '#56CCF2'
  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, padding: '12px 18px',
      borderRadius: 8, background: '#0A1628', border: `1px solid ${color}88`,
      color: '#fff', fontSize: 13, boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
      zIndex: 2000, maxWidth: 400,
    }}>
      <span style={{ color, fontWeight: 700, marginRight: 8 }}>{type.toUpperCase()}</span>
      {message}
    </div>
  )
}

// ─── My Apps (list + create + version history) ────────────────────────────────
function MyApps({ toast }) {
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [newApp, setNewApp] = useState({ name: '', description: '' })
  const [openApp, setOpenApp] = useState(null)
  const [versions, setVersions] = useState([])
  const [expandedSlug, setExpandedSlug] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await appBuilderAPI.listApps()
      setApps(res.data || [])
    } catch (e) {
      toast.show(`Failed to load apps: ${e?.response?.data?.detail || e.message}`, 'error')
    } finally { setLoading(false) }
  }, [toast])

  useEffect(() => { refresh() }, [refresh])

  const createApp = async () => {
    if (!newApp.name.trim()) return
    try {
      await appBuilderAPI.createApp({
        slug: slugify(newApp.name),
        name: newApp.name.trim(),
        description: newApp.description || null,
        definition: { widgets: [] },
      })
      setNewApp({ name: '', description: '' })
      setCreateOpen(false)
      await refresh()
      toast.show('App created', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Create failed', 'error')
    }
  }

  const publish = async (slug) => {
    if (!canPublish()) {
      toast.show('Publishing requires app_builder_publish role', 'error')
      return
    }
    try {
      await appBuilderAPI.publishApp(slug, { notes: '' }, userRole())
      await refresh()
      toast.show(`Published ${slug}`, 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail?.error?.message || 'Publish failed', 'error')
    }
  }

  const preview = async (slug) => {
    try {
      await appBuilderAPI.previewApp(slug)
      await refresh()
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Preview failed', 'error')
    }
  }

  const archive = async (slug) => {
    try {
      await appBuilderAPI.archiveApp(slug, userRole())
      await refresh()
    } catch (e) {
      toast.show(e?.response?.data?.detail?.error?.message || 'Archive failed', 'error')
    }
  }

  const showVersions = async (slug) => {
    if (expandedSlug === slug) { setExpandedSlug(null); return }
    try {
      const res = await appBuilderAPI.getAppVersions(slug)
      setVersions(res.data)
      setExpandedSlug(slug)
    } catch (e) {
      toast.show('Failed to load versions', 'error')
    }
  }

  const appColors = ['#02C9A8', '#56CCF2', '#8B5CF6', '#F59E0B', '#E94B4B']

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <button className="btn-secondary" onClick={refresh} style={{ gap: 6, padding: '8px 14px', fontSize: 12 }}>
          <RefreshCw size={12} /> Refresh
        </button>
        <button className="btn-primary" onClick={() => setCreateOpen(true)} style={{ gap: 6, padding: '9px 18px', fontSize: 13 }}>
          <PlusCircle size={14} /> Create New App
        </button>
      </div>

      {loading ? (
        <p style={{ color: 'rgba(255,255,255,0.4)' }}>Loading…</p>
      ) : apps.length === 0 ? (
        <div className="glass-card" style={{ padding: 36, textAlign: 'center' }}>
          <LayoutDashboard size={32} style={{ color: 'rgba(255,255,255,0.2)', marginBottom: 10 }} />
          <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, margin: 0 }}>
            No apps yet. Create one to start building dashboards.
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {apps.map((app, i) => (
            <div key={app.slug} className="glass-card" style={{ padding: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10,
                  background: `${appColors[i % appColors.length]}20`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  border: `1px solid ${appColors[i % appColors.length]}44`,
                }}>
                  <LayoutDashboard size={18} style={{ color: appColors[i % appColors.length] }} />
                </div>
                <StatusBadge status={app.status} />
              </div>
              <div style={{ fontWeight: 800, fontSize: 15, color: '#fff', marginBottom: 2 }}>{app.name}</div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginBottom: 8, fontFamily: 'monospace' }}>
                {app.slug} · v{app.version}
              </div>
              {app.description && (
                <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', margin: '0 0 12px' }}>{app.description}</p>
              )}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button className="btn-primary" onClick={() => setOpenApp(app)} style={{ padding: '6px 12px', fontSize: 11, gap: 4 }}>
                  <Maximize2 size={11} /> Open
                </button>
                {app.status === 'DRAFT' && (
                  <button className="btn-secondary" onClick={() => preview(app.slug)} style={{ padding: '6px 12px', fontSize: 11, gap: 4 }}>
                    <Eye size={11} /> Preview
                  </button>
                )}
                {['DRAFT', 'PREVIEW'].includes(app.status) && (
                  <button
                    disabled={!canPublish()}
                    onClick={() => publish(app.slug)}
                    style={{
                      padding: '6px 12px', fontSize: 11, borderRadius: 6,
                      background: canPublish() ? '#02C9A822' : 'rgba(255,255,255,0.05)',
                      border: `1px solid ${canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.1)'}`,
                      color: canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.3)',
                      cursor: canPublish() ? 'pointer' : 'not-allowed', fontWeight: 700,
                    }}
                    title={canPublish() ? 'Publish' : 'Requires app_builder_publish role'}
                  >
                    Publish
                  </button>
                )}
                <button onClick={() => showVersions(app.slug)} style={{
                  padding: '6px 10px', fontSize: 11, borderRadius: 6,
                  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)',
                  color: 'rgba(255,255,255,0.6)', cursor: 'pointer', fontWeight: 700,
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                }}>
                  {expandedSlug === app.slug ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                  History
                </button>
                <button onClick={() => archive(app.slug)} style={{
                  padding: '6px 10px', fontSize: 11, borderRadius: 6,
                  background: 'rgba(233,75,75,0.1)', border: '1px solid rgba(233,75,75,0.25)',
                  color: '#E94B4B', cursor: 'pointer',
                }} title="Archive">
                  <Trash2 size={11} />
                </button>
              </div>
              {expandedSlug === app.slug && versions.length > 0 && (
                <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                  <SectionLabel text="Version History" />
                  {versions.map(v => (
                    <div key={v.id} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '4px 6px', fontSize: 11,
                      borderBottom: '1px solid rgba(255,255,255,0.04)',
                    }}>
                      <span style={{ color: 'rgba(255,255,255,0.7)', fontFamily: 'monospace' }}>v{v.version}</span>
                      <StatusBadge status={v.status} />
                      <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10 }}>
                        {new Date(v.updated_at).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create modal */}
      {createOpen && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div className="glass-card animate-slide-up" style={{ padding: 28, width: 420, border: '1px solid rgba(2,201,168,0.2)' }}>
            <h3 style={{ margin: '0 0 16px', color: '#fff', fontSize: 17, fontWeight: 900 }}>Create New App</h3>
            <label style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 5, fontWeight: 700 }}>App Name</label>
            <input
              value={newApp.name}
              onChange={e => setNewApp(p => ({ ...p, name: e.target.value }))}
              placeholder="e.g. Substation Monitor"
              style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 8, color: '#fff', padding: '10px 12px', fontSize: 13, outline: 'none', boxSizing: 'border-box', marginBottom: 12 }}
            />
            <label style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 5, fontWeight: 700 }}>Description</label>
            <input
              value={newApp.description}
              onChange={e => setNewApp(p => ({ ...p, description: e.target.value }))}
              placeholder="What does this app do?"
              style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 8, color: '#fff', padding: '10px 12px', fontSize: 13, outline: 'none', boxSizing: 'border-box', marginBottom: 16 }}
            />
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="btn-primary" onClick={createApp} style={{ flex: 1 }}>Create</button>
              <button className="btn-secondary" onClick={() => setCreateOpen(false)} style={{ flex: 1 }}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {openApp && (
        <div style={{
          position: 'fixed', inset: 0, background: '#0A0F1E',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <LayoutDashboard size={56} style={{ color: '#02C9A8', marginBottom: 20 }} />
          <h1 style={{ color: '#fff', fontSize: 28, fontWeight: 900, margin: '0 0 8px' }}>{openApp.name}</h1>
          <StatusBadge status={openApp.status} />
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 14, margin: '16px 0 28px' }}>
            Version {openApp.version} · {openApp.definition?.widgets?.length || 0} widget(s)
          </p>
          <button className="btn-secondary" onClick={() => setOpenApp(null)}>Exit Preview</button>
        </div>
      )}
    </div>
  )
}

// ─── Rule Engine (persisted via /app-rules) ───────────────────────────────────
function RuleEngine({ toast }) {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const emptyForm = { name: '', trigger: TRIGGERS[0], metric: METRICS[0], op: '>', value: '', action: ACTIONS[0], priority: 'Medium' }
  const [form, setForm] = useState(emptyForm)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await appBuilderAPI.listRules()
      setRules(res.data || [])
    } catch (e) {
      toast.show('Failed to load rules', 'error')
    } finally { setLoading(false) }
  }, [toast])

  useEffect(() => { refresh() }, [refresh])

  const saveRule = async () => {
    if (!form.name.trim()) return
    try {
      await appBuilderAPI.createRule({
        slug: slugify(form.name),
        name: form.name.trim(),
        definition: {
          trigger: form.trigger, metric: form.metric, op: form.op,
          value: form.value, action: form.action, priority: form.priority,
        },
      })
      setForm(emptyForm); setCreating(false)
      await refresh()
      toast.show('Rule created', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Create failed', 'error')
    }
  }

  const deleteRule = async (slug) => {
    try {
      await appBuilderAPI.deleteRule(slug, userRole())
      await refresh()
    } catch (e) {
      toast.show('Delete failed', 'error')
    }
  }

  const publish = async (slug) => {
    if (!canPublish()) { toast.show('Publishing requires app_builder_publish role', 'error'); return }
    try {
      await appBuilderAPI.publishRule(slug, {}, userRole())
      await refresh()
      toast.show('Published', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail?.error?.message || 'Publish failed', 'error')
    }
  }

  const pColor = { Critical: '#E94B4B', High: '#F97316', Medium: '#F59E0B', Low: '#3B82F6' }

  return (
    <div>
      {creating ? (
        <div className="glass-card animate-slide-up" style={{ padding: 20, marginBottom: 20, border: '1px solid rgba(2,201,168,0.2)' }}>
          <h3 style={{ margin: '0 0 16px', color: '#fff', fontSize: 15, fontWeight: 700 }}>Create Rule</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Rule Name</label>
              <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                placeholder="e.g. High Load Alert"
                style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#fff', padding: '8px 10px', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Trigger</label>
              <select value={form.trigger} onChange={e => setForm(p => ({ ...p, trigger: e.target.value }))}
                style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#ABC7FF', padding: '8px 10px', fontSize: 13, outline: 'none', boxSizing: 'border-box' }}>
                {TRIGGERS.map(t => <option key={t} value={t} style={{ background: '#0A1535' }}>{t}</option>)}
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Condition</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <select value={form.metric} onChange={e => setForm(p => ({ ...p, metric: e.target.value }))}
                  style={{ flex: 2, background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#ABC7FF', padding: '8px 10px', fontSize: 13 }}>
                  {METRICS.map(m => <option key={m} value={m} style={{ background: '#0A1535' }}>{m}</option>)}
                </select>
                <select value={form.op} onChange={e => setForm(p => ({ ...p, op: e.target.value }))}
                  style={{ flex: 1, background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#ABC7FF', padding: '8px 10px', fontSize: 13, textAlign: 'center' }}>
                  {OPERATORS.map(o => <option key={o} value={o} style={{ background: '#0A1535' }}>{o}</option>)}
                </select>
                <input value={form.value} onChange={e => setForm(p => ({ ...p, value: e.target.value }))}
                  placeholder="Value"
                  style={{ flex: 1, background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#fff', padding: '8px 10px', fontSize: 13 }} />
              </div>
            </div>
            <div>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Action</label>
              <select value={form.action} onChange={e => setForm(p => ({ ...p, action: e.target.value }))}
                style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#ABC7FF', padding: '8px 10px', fontSize: 13, boxSizing: 'border-box' }}>
                {ACTIONS.map(a => <option key={a} value={a} style={{ background: '#0A1535' }}>{a}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Priority</label>
              <div style={{ display: 'flex', gap: 6 }}>
                {PRIORITIES.map(p => (
                  <button key={p} onClick={() => setForm(f => ({ ...f, priority: p }))} style={{
                    flex: 1, padding: '7px 4px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                    cursor: 'pointer', background: form.priority === p ? `${pColor[p]}22` : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${form.priority === p ? pColor[p] : 'rgba(255,255,255,0.08)'}`,
                    color: form.priority === p ? pColor[p] : 'rgba(255,255,255,0.4)',
                  }}>{p}</button>
                ))}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button className="btn-primary" onClick={saveRule} style={{ gap: 6, padding: '9px 18px', fontSize: 13 }}>
              <Save size={13} /> Save Rule
            </button>
            <button className="btn-secondary" onClick={() => { setCreating(false); setForm(emptyForm) }}
              style={{ padding: '9px 18px', fontSize: 13 }}>Cancel</button>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <button className="btn-secondary" onClick={refresh} style={{ gap: 6, padding: '8px 14px', fontSize: 12 }}>
            <RefreshCw size={12} /> Refresh
          </button>
          <button className="btn-primary" onClick={() => setCreating(true)} style={{ gap: 6, padding: '9px 18px', fontSize: 13 }}>
            <PlusCircle size={14} /> Create Rule
          </button>
        </div>
      )}

      <div className="glass-card" style={{ overflow: 'hidden' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th><th>Slug/Ver</th><th>Trigger</th><th>Condition</th>
              <th>Action</th><th>Status</th><th style={{ width: 160 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'rgba(255,255,255,0.4)' }}>Loading…</td></tr>
            ) : rules.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'rgba(255,255,255,0.4)' }}>No rules yet.</td></tr>
            ) : rules.map(rule => {
              const d = rule.definition || {}
              return (
                <tr key={rule.slug}>
                  <td style={{ fontWeight: 600, color: '#fff' }}>{rule.name}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 11, color: '#ABC7FF' }}>{rule.slug} v{rule.version}</td>
                  <td style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>{d.trigger}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12, color: '#ABC7FF' }}>
                    {d.metric} {d.op} {d.value}
                  </td>
                  <td style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>{d.action}</td>
                  <td><StatusBadge status={rule.status} /></td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {['DRAFT', 'PREVIEW'].includes(rule.status) && (
                        <button onClick={() => publish(rule.slug)} disabled={!canPublish()}
                          style={{
                            padding: '4px 10px', fontSize: 11, borderRadius: 5, fontWeight: 700,
                            background: canPublish() ? '#02C9A822' : 'rgba(255,255,255,0.05)',
                            border: `1px solid ${canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.1)'}`,
                            color: canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.3)',
                            cursor: canPublish() ? 'pointer' : 'not-allowed',
                          }} title={canPublish() ? 'Publish' : 'Role required'}>Publish</button>
                      )}
                      <button onClick={() => deleteRule(rule.slug)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#E94B4B', padding: 4 }}>
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
    </div>
  )
}

// ─── Algorithm Editor (persisted via /algorithms + /run sandbox) ──────────────
function AlgorithmEditor({ toast }) {
  const [algos, setAlgos] = useState([])
  const [active, setActive] = useState(null)   // { slug, name, source, version, status }
  const [loading, setLoading] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [consoleOut, setConsoleOut] = useState('')
  const [running, setRunning] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await appBuilderAPI.listAlgorithms()
      setAlgos(res.data || [])
      if (!active && res.data?.length) {
        const first = res.data[0]
        setActive(first); setCode(first.source); setName(first.name)
      }
    } catch (e) {
      toast.show('Failed to load algorithms', 'error')
    } finally { setLoading(false) }
  }, [toast, active])

  useEffect(() => { refresh() }, []) // eslint-disable-line

  const loadAlgo = (a) => {
    setActive(a)
    setCode(a.source)
    setName(a.name)
    setConsoleOut('')
  }

  const createNew = async () => {
    const nn = prompt('Algorithm name')
    if (!nn) return
    const slug = slugify(nn)
    const defaultSource = `# ${nn}\ndef main(inputs):\n    # inputs is a dict. Return any JSON-serialisable value.\n    return {"ok": True, "received": inputs}\n`
    try {
      const res = await appBuilderAPI.createAlgorithm({
        slug, name: nn, source: defaultSource, definition: {},
      })
      await refresh()
      loadAlgo(res.data)
      toast.show('Algorithm created', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Create failed', 'error')
    }
  }

  const saveAlgo = async () => {
    if (!active) return
    try {
      const res = await appBuilderAPI.updateAlgorithm(active.slug, {
        name, source: code,
      })
      setActive(res.data)
      await refresh()
      toast.show(`Saved v${res.data.version}`, 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Save failed', 'error')
    }
  }

  const runAlgo = async () => {
    if (!active) return
    setRunning(true); setConsoleOut('Running…\n')
    try {
      const res = await appBuilderAPI.runAlgorithm(active.slug, {
        inputs: {}, timeout_seconds: 5,
      })
      const d = res.data
      let out = `[${new Date().toISOString()}] ${d.status.toUpperCase()} in ${d.duration_ms}ms\n`
      if (d.stdout) out += `stdout:\n${d.stdout}\n`
      if (d.error) out += `error: ${d.error}\n`
      if (d.result !== null && d.result !== undefined) {
        out += `result: ${JSON.stringify(d.result, null, 2)}\n`
      }
      setConsoleOut(out)
    } catch (e) {
      setConsoleOut(`RUN FAILED: ${e?.response?.data?.detail || e.message}`)
    } finally { setRunning(false) }
  }

  const publishAlgo = async () => {
    if (!active) return
    if (!canPublish()) { toast.show('Publishing requires app_builder_publish role', 'error'); return }
    try {
      await appBuilderAPI.publishAlgorithm(active.slug, {}, userRole())
      await refresh()
      toast.show('Published', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail?.error?.message || 'Publish failed', 'error')
    }
  }

  const lineNumbers = code.split('\n').map((_, i) => i + 1).join('\n')

  return (
    <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 240px)' }}>
      <div className="glass-card" style={{ padding: 14, width: 220, flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
        <SectionLabel text="Algorithm Library" />
        <button className="btn-primary" onClick={createNew}
          style={{ padding: '6px 10px', fontSize: 11, marginBottom: 8, gap: 4 }}>
          <PlusCircle size={11} /> New
        </button>
        <button className="btn-secondary" onClick={refresh}
          style={{ padding: '6px 10px', fontSize: 11, marginBottom: 10, gap: 4 }}>
          <RefreshCw size={11} /> Refresh
        </button>
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {loading && <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>Loading…</p>}
          {algos.map(a => (
            <button key={a.slug} onClick={() => loadAlgo(a)} style={{
              width: '100%', padding: '8px 10px', borderRadius: 8, marginBottom: 4,
              background: active?.slug === a.slug ? 'rgba(2,201,168,0.12)' : 'rgba(255,255,255,0.04)',
              border: `1px solid ${active?.slug === a.slug ? '#02C9A8' : 'rgba(255,255,255,0.08)'}`,
              color: active?.slug === a.slug ? '#02C9A8' : 'rgba(255,255,255,0.6)',
              fontSize: 11, fontWeight: 600, cursor: 'pointer', textAlign: 'left',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <BookOpen size={11} style={{ flexShrink: 0 }} />
              <span style={{ flex: 1 }}>{a.name}</span>
              <StatusBadge status={a.status} />
            </button>
          ))}
          {!loading && algos.length === 0 && (
            <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>No algorithms yet.</p>
          )}
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn-primary" onClick={runAlgo} disabled={running || !active}
            style={{ gap: 6, padding: '8px 16px', fontSize: 12 }}>
            <Play size={13} /> {running ? 'Running…' : 'Preview / Run'}
          </button>
          <button className="btn-secondary" onClick={saveAlgo} disabled={!active}
            style={{ gap: 6, padding: '8px 16px', fontSize: 12 }}>
            <Save size={13} /> Save (new version)
          </button>
          <button onClick={publishAlgo} disabled={!active || !canPublish()}
            style={{
              padding: '8px 16px', fontSize: 12, borderRadius: 6, fontWeight: 700,
              background: canPublish() ? '#02C9A822' : 'rgba(255,255,255,0.05)',
              border: `1px solid ${canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.1)'}`,
              color: canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.3)',
              cursor: canPublish() && active ? 'pointer' : 'not-allowed',
            }}
            title={canPublish() ? 'Publish' : 'Requires app_builder_publish role'}>
            Publish
          </button>
          {active && (
            <input
              value={name} onChange={e => setName(e.target.value)}
              placeholder="Name"
              style={{ marginLeft: 'auto', padding: '6px 10px', fontSize: 12,
                background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)',
                borderRadius: 6, color: '#fff', outline: 'none', width: 260 }}
            />
          )}
          {active && <StatusBadge status={active.status} />}
          {active && <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 11, fontFamily: 'monospace' }}>v{active.version}</span>}
        </div>

        <div style={{
          flex: 1, display: 'flex', borderRadius: 10, overflow: 'hidden',
          border: '1px solid rgba(2,201,168,0.2)', background: '#060B18',
        }}>
          <div style={{
            padding: '16px 12px', background: '#060B18', borderRight: '1px solid rgba(255,255,255,0.06)',
            fontFamily: "'Courier New', Courier, monospace", fontSize: 13, lineHeight: '1.7',
            color: 'rgba(255,255,255,0.2)', whiteSpace: 'pre', userSelect: 'none',
            minWidth: 40, textAlign: 'right', overflowY: 'hidden',
          }}>
            {lineNumbers}
          </div>
          <textarea
            value={code}
            onChange={e => setCode(e.target.value)}
            disabled={!active}
            spellCheck={false}
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none', resize: 'none',
              fontFamily: "'Courier New', Courier, monospace", fontSize: 13, lineHeight: '1.7',
              color: '#02C9A8', padding: '16px', caretColor: '#02C9A8',
            }}
          />
        </div>

        <div style={{
          height: 160, borderRadius: 8, background: '#030712', border: '1px solid rgba(255,255,255,0.06)',
          padding: '10px 14px', overflow: 'auto',
        }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.25)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Sandbox Output
          </div>
          <pre style={{
            margin: 0, fontFamily: "'Courier New', Courier, monospace", fontSize: 12,
            color: consoleOut ? '#02C9A8' : 'rgba(255,255,255,0.2)', lineHeight: '1.6',
            whiteSpace: 'pre-wrap',
          }}>
            {consoleOut || '— No output yet. Press Preview / Run to execute in the sandbox. —'}
          </pre>
        </div>
      </div>
    </div>
  )
}

// ─── Dashboard Builder (in-memory scratchpad — saving persists via /apps) ─────
function DashboardBuilder({ toast }) {
  const GRID_ROWS = 3, GRID_COLS = 4
  const [canvas, setCanvas] = useState(Array(GRID_ROWS * GRID_COLS).fill(null))
  const [saveName, setSaveName] = useState('')
  const dragRef = useRef(null)

  const handleDrop = (idx, e) => {
    e.preventDefault()
    if (!dragRef.current || canvas[idx]) return
    const next = [...canvas]
    next[idx] = { ...dragRef.current, cellId: idx }
    setCanvas(next)
    dragRef.current = null
  }

  const removeWidget = (idx) => {
    const next = [...canvas]
    next[idx] = null
    setCanvas(next)
  }

  const saveAsApp = async () => {
    if (!saveName.trim()) {
      toast.show('Provide an app name first', 'error'); return
    }
    const widgets = canvas
      .map((w, i) => w ? { slot: i, widget: w.id, name: w.name } : null)
      .filter(Boolean)
    try {
      await appBuilderAPI.createApp({
        slug: slugify(saveName),
        name: saveName.trim(),
        description: `Dashboard with ${widgets.length} widget(s)`,
        definition: { widgets, grid: { rows: GRID_ROWS, cols: GRID_COLS } },
      })
      toast.show('Saved as app', 'success')
      setSaveName('')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Save failed', 'error')
    }
  }

  return (
    <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 240px)' }}>
      <div className="glass-card" style={{ padding: 16, width: 160, overflowY: 'auto', flexShrink: 0 }}>
        <SectionLabel text="Widget Palette" />
        {WIDGET_PALETTE.map(w => (
          <div
            key={w.id}
            draggable
            onDragStart={() => { dragRef.current = w }}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
              borderRadius: 8, marginBottom: 6, cursor: 'grab',
              background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
            }}
          >
            <w.icon size={14} style={{ color: w.color, flexShrink: 0 }} />
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.7)', fontWeight: 600 }}>{w.name}</span>
          </div>
        ))}
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{
          flex: 1, display: 'grid', gridTemplateColumns: `repeat(${GRID_COLS}, 1fr)`,
          gridTemplateRows: `repeat(${GRID_ROWS}, 1fr)`, gap: 8,
        }}>
          {canvas.map((widget, idx) => (
            <div
              key={idx}
              onDragOver={e => { if (!canvas[idx]) { e.preventDefault() } }}
              onDrop={e => handleDrop(idx, e)}
              style={{
                borderRadius: 10,
                border: `2px dashed ${widget ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.08)'}`,
                background: widget ? `${widget.color}0d` : 'rgba(255,255,255,0.03)',
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                position: 'relative',
              }}
            >
              {widget ? (
                <>
                  <widget.icon size={22} style={{ color: widget.color, marginBottom: 6 }} />
                  <span style={{ fontSize: 11, fontWeight: 700, color: widget.color }}>{widget.name}</span>
                  <button
                    onClick={e => { e.stopPropagation(); removeWidget(idx) }}
                    style={{
                      position: 'absolute', top: 6, right: 6, width: 18, height: 18,
                      borderRadius: '50%', background: 'rgba(233,75,75,0.3)', border: '1px solid rgba(233,75,75,0.5)',
                      color: '#E94B4B', cursor: 'pointer', fontSize: 11, fontWeight: 900,
                      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
                    }}
                  >×</button>
                </>
              ) : (
                <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)' }}>Drop here</span>
              )}
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={saveName}
            onChange={e => setSaveName(e.target.value)}
            placeholder="App name to save this layout as…"
            style={{ flex: 1, padding: '8px 12px', background: 'rgba(10,54,144,0.25)',
              border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#fff', fontSize: 13, outline: 'none' }}
          />
          <button className="btn-primary" onClick={saveAsApp} style={{ gap: 6, padding: '8px 16px', fontSize: 12 }}>
            <Save size={13} /> Save as App
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Root ─────────────────────────────────────────────────────────────────────
const TABS = ['Dashboard Builder', 'Rule Engine', 'Algorithm Editor', 'My Apps']

export default function AppBuilder() {
  const [activeTab, setActiveTab] = useState('Dashboard Builder')
  const [toastMsg, setToastMsg] = useState({ message: '', type: 'info' })
  const toast = useMemo(() => ({
    show: (message, type = 'info') => setToastMsg({ message, type }),
  }), [])

  return (
    <div className="animate-slide-up" style={{ padding: 24, minHeight: '100vh', background: '#0A0F1E' }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 900, color: '#fff', margin: 0 }}>No-Code App Builder</h1>
        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13, margin: '4px 0 0' }}>
          REQ-27 L3 — Custom displays · Rule engine · Algorithm editor · App creation
          {!canPublish() && (
            <span style={{ color: '#F59E0B', marginLeft: 10 }}>
              · Publish disabled (requires app_builder_publish role)
            </span>
          )}
        </p>
      </div>

      <TabBar tabs={TABS} active={activeTab} onChange={setActiveTab} />

      {activeTab === 'Dashboard Builder' && <DashboardBuilder toast={toast} />}
      {activeTab === 'Rule Engine'       && <RuleEngine toast={toast} />}
      {activeTab === 'Algorithm Editor'  && <AlgorithmEditor toast={toast} />}
      {activeTab === 'My Apps'           && <MyApps toast={toast} />}

      <Toast message={toastMsg.message} type={toastMsg.type} onClose={() => setToastMsg({ message: '', type: 'info' })} />
    </div>
  )
}
