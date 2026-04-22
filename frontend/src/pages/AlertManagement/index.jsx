/**
 * AlertManagement — single-page tabbed UI that demonstrates the four required
 * pillars:
 *   1. Virtual Object Group information          → Groups tab
 *   2. Alarm rules creation + information        → Rules tab
 *   3. Alarm Subscription (priority + channels)  → Subscriptions tab
 *   4. Default feeder + critical-customer groups → top of page
 *
 * Data sources:
 *   - Virtual-object groups come from /api/v1/groups (local).
 *   - Alarm rules come from /api/v1/alarm-rules (local).
 *   - Consumers come from MDMS db_cis.consumer_master_data (read-only) via
 *     /api/v1/cis/consumers, overlayed with the local consumer_tag table so
 *     a hospital / data-centre / fire-station classification can drive the
 *     "critical customers" group selector.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Bell, Users, Layers, Zap, Plus, RefreshCw, AlertTriangle, CheckCircle2,
  Mail, MessageSquare, Monitor, ShieldAlert, ArrowLeft,
} from 'lucide-react'

import { alertMgmtAPI, alarmsAPI } from '@/services/api'
import { useToast } from '@/components/ui/Toast'

import GroupsTab from './GroupsTab'
import RulesTab from './RulesTab'
import SubscriptionsTab from './SubscriptionsTab'
import AlertsTab from './AlertsTab'

const TABS = [
  { id: 'groups',        label: 'Virtual Groups',  icon: Layers,       desc: 'Consumer + feeder groups that rules target' },
  { id: 'rules',         label: 'Alarm Rules',     icon: Zap,          desc: 'Condition + action bound to a group' },
  { id: 'subscriptions', label: 'Subscriptions',   icon: Bell,         desc: 'Priority → channel mapping per rule' },
  { id: 'alerts',        label: 'Live Alerts',     icon: AlertTriangle,desc: 'Firings from the rule engine' },
]

export default function AlertManagement() {
  const toast = useToast()
  const navigate = useNavigate()
  const { tab: urlTab } = useParams()
  const tab = TABS.some(t => t.id === urlTab) ? urlTab : 'groups'
  const setTab = (id) => navigate(`/alerts-mgmt/${id}`)
  const [stats, setStats] = useState(null)
  const [defaults, setDefaults] = useState(null)
  const [seeding, setSeeding] = useState(false)

  const loadHeader = useCallback(async () => {
    try {
      const [s, d] = await Promise.all([
        alertMgmtAPI.consumerStats(),
        alertMgmtAPI.defaultsStatus(),
      ])
      setStats(s.data)
      setDefaults(d.data)
    } catch (err) {
      // Stats are a nice-to-have; silence errors so the tab stays usable.
      // Surface via toast only when explicit.
    }
  }, [])

  useEffect(() => { loadHeader() }, [loadHeader])

  const seedDefaults = async () => {
    if (!window.confirm('Create the default feeder-meters + critical-customers groups and tag a handful of consumers?')) return
    setSeeding(true)
    try {
      const { data } = await alertMgmtAPI.seedDefaults()
      const created = [...(data.created_groups || []), ...(data.created_rules || [])]
      toast.success(
        created.length ? 'Defaults seeded' : 'Defaults already present',
        `Tagged ${data.tagged_consumers} new critical consumers (${data.critical_members} total).`
      )
      loadHeader()
    } catch (err) {
      toast.error('Failed to seed defaults', err?.response?.data?.detail ?? err?.message)
    } finally {
      setSeeding(false)
    }
  }

  const critical = stats?.by_site_type || {}
  const criticalCount = (critical.hospital || 0) + (critical.data_centre || 0) + (critical.fire_station || 0)
  const seeded = defaults?.seeded

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-white font-black flex items-center gap-2" style={{ fontSize: 22 }}>
              <ShieldAlert size={20} className="text-accent-blue" />
              Alert Management
            </h1>
            <p className="text-white/40" style={{ fontSize: 13 }}>
              Virtual groups, rule configuration, and priority-based notifications
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={seedDefaults}
            disabled={seeding}
            className="btn-secondary py-2 px-3"
            style={{ fontSize: 12, opacity: seeding ? 0.5 : 1 }}
            title="Idempotent — won't duplicate existing groups"
          >
            {seeded ? <CheckCircle2 size={12} className="inline mr-1 text-energy-green" /> : <Plus size={12} className="inline mr-1" />}
            {seeding ? 'Seeding…' : seeded ? 'Defaults loaded' : 'Load default groups'}
          </button>
          <button onClick={loadHeader} className="btn-secondary py-2 px-3" style={{ fontSize: 12 }}>
            <RefreshCw size={12} className="inline mr-1" /> Refresh
          </button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          icon={<Layers size={16} />}
          label="Consumers (MDMS CIS)"
          value={stats?.mdms_total ?? '—'}
          hint="read from db_cis.consumer_master_data"
          color="#60A5FA"
        />
        <KpiCard
          icon={<Users size={16} />}
          label="Critical sites tagged"
          value={criticalCount}
          hint={`${critical.hospital || 0} hosp · ${critical.data_centre || 0} dc · ${critical.fire_station || 0} fire`}
          color="#E94B4B"
        />
        <KpiCard
          icon={<Bell size={16} />}
          label="Default groups"
          value={seeded ? 'Ready' : 'Not seeded'}
          hint="feeder-meters + critical-customers"
          color={seeded ? '#02C9A8' : '#F59E0B'}
        />
        <KpiCard
          icon={<Mail size={16} />}
          label="Channels"
          value="In-app · Email · SMS"
          hint="SMS simulated (Twilio disabled)"
          color="#A78BFA"
        />
      </div>

      {/* Tabs */}
      <div className="glass-card p-1 flex gap-1 flex-wrap">
        {TABS.map(t => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="flex-1 min-w-[160px] flex items-center gap-2 px-3 py-2 rounded-lg transition-colors"
              style={{
                background: active ? 'rgba(96,165,250,0.12)' : 'transparent',
                border: `1px solid ${active ? '#60A5FA40' : 'transparent'}`,
                color: active ? '#60A5FA' : 'rgba(255,255,255,0.6)',
              }}
              title={t.desc}
            >
              <Icon size={14} />
              <span className="text-sm font-medium">{t.label}</span>
            </button>
          )
        })}
      </div>

      {/* Tab body */}
      <div>
        {tab === 'groups'        && <GroupsTab onChanged={loadHeader} />}
        {tab === 'rules'         && <RulesTab />}
        {tab === 'subscriptions' && <SubscriptionsTab />}
        {tab === 'alerts'        && <AlertsTab />}
      </div>
    </div>
  )
}


function KpiCard({ icon, label, value, hint, color }) {
  return (
    <div className="glass-card p-4">
      <div className="flex items-center gap-2 mb-2" style={{ color }}>
        {icon}
        <span className="text-white/50" style={{ fontSize: 11 }}>{label}</span>
      </div>
      <div className="text-white font-black" style={{ fontSize: 20 }}>{value}</div>
      {hint && <div className="text-white/40 mt-1" style={{ fontSize: 11 }}>{hint}</div>}
    </div>
  )
}
