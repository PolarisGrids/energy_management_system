/**
 * GroupsTab — virtual object group (VOG) list + creation.
 *
 * Creation supports two selector styles:
 *   - Hierarchy-based: pick feeders, DTRs, substations, or explicit meter
 *     serials (existing /api/v1/groups selector.hierarchy schema).
 *   - Site-type-based: pick one or more consumer_tag.site_types so the group
 *     auto-includes every hospital / data-centre / etc. (no manual list).
 *
 * The members preview resolves via /api/v1/groups/{id}/members so an
 * operator sees exactly which meter serials the group covers.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Plus, Trash2, RefreshCw, Users, Check, X, Layers, Building2,
  Hospital, Server, Flame, Home as HomeIcon, Store,
} from 'lucide-react'

import { alertMgmtAPI, groupsAPI, metersAPI } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Modal from '@/components/ui/Modal'

const SITE_TYPE_META = {
  residential:  { label: 'Residential',  icon: HomeIcon },
  commercial:   { label: 'Commercial',   icon: Store },
  industrial:   { label: 'Industrial',   icon: Building2 },
  hospital:     { label: 'Hospital',     icon: Hospital, color: '#E94B4B' },
  data_centre:  { label: 'Data Centre',  icon: Server,   color: '#60A5FA' },
  fire_station: { label: 'Fire Station', icon: Flame,    color: '#F97316' },
  government:   { label: 'Government',   icon: Building2 },
  school:       { label: 'School',       icon: Building2 },
}

function describeSelector(selector) {
  const h = selector?.hierarchy || {}
  const parts = []
  if (h.site_types?.length) parts.push(`site types: ${h.site_types.join(', ')}`)
  if (h.feeder_ids?.length) parts.push(`${h.feeder_ids.length} feeder(s)`)
  if (h.dtr_ids?.length) parts.push(`${h.dtr_ids.length} DTR(s)`)
  if (h.substation_ids?.length) parts.push(`${h.substation_ids.length} substation(s)`)
  if (h.meter_serials?.length) parts.push(`${h.meter_serials.length} meter(s)`)
  if (!parts.length) parts.push('entire fleet')
  return parts.join(' · ')
}

export default function GroupsTab({ onChanged }) {
  const toast = useToast()
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [selected, setSelected] = useState(null)
  const [members, setMembers] = useState([])
  const [membersLoading, setMembersLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await groupsAPI.list()
      setGroups(data || [])
    } catch (err) {
      toast.error('Failed to load groups', err?.response?.data?.detail ?? err?.message)
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const viewMembers = async (g) => {
    setSelected(g)
    setMembers([])
    setMembersLoading(true)
    try {
      const { data } = await groupsAPI.members(g.id)
      setMembers(data?.meter_serials || [])
    } catch (err) {
      toast.error('Failed to load group members', err?.response?.data?.detail ?? err?.message)
    } finally {
      setMembersLoading(false)
    }
  }

  const deleteGroup = async (g) => {
    if (!window.confirm(`Delete group "${g.name}"? Rules bound to it will also break.`)) return
    try {
      await groupsAPI.delete(g.id)
      toast.success('Group deleted', g.name)
      if (selected?.id === g.id) setSelected(null)
      load()
      onChanged?.()
    } catch (err) {
      toast.error('Failed to delete group', err?.response?.data?.detail ?? err?.message)
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* List */}
      <div className="glass-card overflow-hidden lg:col-span-2">
        <div className="flex items-center justify-between p-3 border-b border-white/5">
          <div>
            <div className="text-white font-bold" style={{ fontSize: 13 }}>Virtual Object Groups</div>
            <div className="text-white/40" style={{ fontSize: 11 }}>{groups.length} group(s)</div>
          </div>
          <button onClick={() => setCreateOpen(true)} className="btn-primary py-2 px-3" style={{ fontSize: 12 }}>
            <Plus size={12} className="inline mr-1" /> New group
          </button>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Selector</th>
              <th>Shared</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="text-center py-8 text-white/40">Loading groups…</td></tr>
            ) : groups.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-10 text-white/40">
                  <Layers size={28} className="mx-auto mb-2 opacity-40" />
                  <div>No groups yet</div>
                  <div className="text-xs mt-1">Click "Load default groups" at the top, or create one here.</div>
                </td>
              </tr>
            ) : groups.map(g => (
              <tr
                key={g.id}
                onClick={() => viewMembers(g)}
                className={`cursor-pointer ${selected?.id === g.id ? 'bg-white/5' : ''}`}
              >
                <td>
                  <div className="text-white font-medium" style={{ fontSize: 13 }}>{g.name}</div>
                  {g.description && (
                    <div className="text-white/40 mt-0.5" style={{ fontSize: 11 }}>{g.description}</div>
                  )}
                </td>
                <td className="text-white/60" style={{ fontSize: 11 }}>{describeSelector(g.selector)}</td>
                <td className="text-white/60" style={{ fontSize: 11 }}>
                  {(g.shared_with_roles || []).join(', ') || '—'}
                </td>
                <td className="text-white/40" style={{ fontSize: 11 }}>
                  {new Date(g.updated_at).toLocaleString('en-ZA')}
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => deleteGroup(g)}
                    className="text-status-critical hover:text-white transition-colors"
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Members sidebar */}
      <div className="glass-card p-3">
        <div className="flex items-center gap-2 mb-3">
          <Users size={14} className="text-accent-blue" />
          <div>
            <div className="text-white font-bold" style={{ fontSize: 13 }}>Resolved members</div>
            <div className="text-white/40" style={{ fontSize: 11 }}>
              {selected ? selected.name : 'Click a group to see its members'}
            </div>
          </div>
        </div>
        {!selected ? (
          <div className="text-white/30 text-center py-10 text-xs">
            No group selected
          </div>
        ) : membersLoading ? (
          <div className="text-white/40 text-xs">Resolving…</div>
        ) : members.length === 0 ? (
          <div className="text-white/40 text-xs">
            No matching meters in the local fleet yet. The selector is still
            valid — the rule engine evaluates it against incoming events.
          </div>
        ) : (
          <div className="max-h-80 overflow-y-auto space-y-1">
            {members.slice(0, 200).map(s => (
              <div key={s} className="text-white/70 text-xs font-mono bg-white/3 rounded px-2 py-1">
                {s}
              </div>
            ))}
            {members.length > 200 && (
              <div className="text-white/40 text-xs pt-1">… and {members.length - 200} more</div>
            )}
          </div>
        )}
      </div>

      <CreateGroupModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={() => { setCreateOpen(false); load(); onChanged?.() }}
      />
    </div>
  )
}


function CreateGroupModal({ open, onClose, onSaved }) {
  const toast = useToast()
  const [tab, setTab] = useState('consumers')  // consumers | hierarchy
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [siteTypes, setSiteTypes] = useState([])
  const [consumers, setConsumers] = useState([])
  const [consumerPick, setConsumerPick] = useState([])
  const [consumerSearch, setConsumerSearch] = useState('')
  const [feeders, setFeeders] = useState([])
  const [transformers, setTransformers] = useState([])
  const [selectedFeederIds, setSelectedFeederIds] = useState([])
  const [selectedDtrIds, setSelectedDtrIds] = useState([])
  const [saving, setSaving] = useState(false)
  const [consumerLoading, setConsumerLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    setTab('consumers')
    setName('')
    setDescription('')
    setSiteTypes([])
    setConsumerPick([])
    setConsumerSearch('')
    setSelectedFeederIds([])
    setSelectedDtrIds([])
    // Preload MDMS consumers + local feeders/DTRs.
    setConsumerLoading(true)
    Promise.all([
      alertMgmtAPI.listConsumers({ limit: 200 }),
      metersAPI.feeders(),
      metersAPI.transformers(),
    ])
      .then(([cRes, fRes, tRes]) => {
        setConsumers(cRes.data?.items || [])
        setFeeders(fRes.data || [])
        setTransformers(tRes.data || [])
      })
      .catch(() => {})
      .finally(() => setConsumerLoading(false))
  }, [open])

  const refreshConsumers = async (search) => {
    setConsumerLoading(true)
    try {
      const { data } = await alertMgmtAPI.listConsumers({ limit: 200, search })
      setConsumers(data?.items || [])
    } finally {
      setConsumerLoading(false)
    }
  }

  const filteredConsumers = useMemo(() => {
    if (!consumerSearch) return consumers
    const s = consumerSearch.toLowerCase()
    return consumers.filter(c =>
      c.consumer_name?.toLowerCase().includes(s) ||
      c.account_id?.toLowerCase().includes(s) ||
      c.meter_serial?.toLowerCase().includes(s)
    )
  }, [consumers, consumerSearch])

  const toggle = (arr, id) => arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id]

  const buildSelector = () => {
    const hierarchy = {}
    if (siteTypes.length) hierarchy.site_types = siteTypes
    if (consumerPick.length) hierarchy.meter_serials = consumerPick
    if (tab === 'hierarchy') {
      if (selectedFeederIds.length) hierarchy.feeder_ids = selectedFeederIds
      if (selectedDtrIds.length) hierarchy.dtr_ids = selectedDtrIds
    }
    return { hierarchy, filters: {} }
  }

  const canSave = name.trim() && (
    siteTypes.length > 0 || consumerPick.length > 0 ||
    selectedFeederIds.length > 0 || selectedDtrIds.length > 0
  )

  const submit = async () => {
    if (!canSave) return
    setSaving(true)
    try {
      await groupsAPI.create({
        name: name.trim(),
        description: description.trim() || undefined,
        selector: buildSelector(),
        shared_with_roles: ['admin', 'supervisor', 'operator'],
      })
      toast.success('Group created', name.trim())
      onSaved?.()
    } catch (err) {
      toast.error('Failed to create group', err?.response?.data?.detail ?? err?.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create Virtual Object Group"
      size="xl"
      footer={
        <div className="flex justify-between items-center w-full">
          <div className="text-white/40 text-xs">
            {consumerPick.length} consumer(s) · {siteTypes.length} site type(s) · {selectedFeederIds.length} feeder(s) · {selectedDtrIds.length} DTR(s) selected
          </div>
          <div className="flex gap-2">
            <button onClick={onClose} className="btn-secondary py-2 px-4" style={{ fontSize: 13 }}>Cancel</button>
            <button
              onClick={submit}
              disabled={!canSave || saving}
              className="btn-primary py-2 px-4"
              style={{ fontSize: 13, opacity: !canSave || saving ? 0.5 : 1 }}
            >
              {saving ? <><RefreshCw size={12} className="animate-spin inline mr-2" />Saving…</> : <><Check size={12} className="inline mr-2" />Create group</>}
            </button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3">
          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>GROUP NAME</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Sandton CBD commercial"
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm focus:border-accent-blue/50"
            />
          </label>
          <label className="block">
            <span className="text-white/50" style={{ fontSize: 11 }}>DESCRIPTION (optional)</span>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="When this group is used and by whom"
              className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm focus:border-accent-blue/50"
            />
          </label>
        </div>

        {/* Tab strip within modal */}
        <div className="glass-card p-1 flex gap-1">
          {[
            { id: 'consumers', label: 'Consumers (MDMS)' },
            { id: 'hierarchy', label: 'Feeders / DTRs' },
          ].map(t => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className="flex-1 px-3 py-1.5 rounded-lg text-sm"
              style={{
                background: tab === t.id ? 'rgba(96,165,250,0.12)' : 'transparent',
                color: tab === t.id ? '#60A5FA' : 'rgba(255,255,255,0.6)',
                border: `1px solid ${tab === t.id ? '#60A5FA40' : 'transparent'}`,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'consumers' && (
          <div className="space-y-3">
            {/* Site-type quick-select */}
            <div>
              <div className="text-white/50 mb-1.5" style={{ fontSize: 11 }}>
                AUTO-INCLUDE BY SITE TYPE (syncs as new consumers are tagged)
              </div>
              <div className="flex gap-2 flex-wrap">
                {Object.entries(SITE_TYPE_META).map(([val, meta]) => {
                  const Icon = meta.icon
                  const on = siteTypes.includes(val)
                  return (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setSiteTypes(prev => toggle(prev, val))}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg transition-colors"
                      style={{
                        background: on ? 'rgba(96,165,250,0.15)' : 'rgba(255,255,255,0.03)',
                        border: `1px solid ${on ? '#60A5FA60' : 'rgba(255,255,255,0.08)'}`,
                        color: on ? (meta.color || '#60A5FA') : 'rgba(255,255,255,0.55)',
                      }}
                    >
                      <Icon size={11} />
                      <span className="text-xs">{meta.label}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Individual consumer pick */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-white/50" style={{ fontSize: 11 }}>
                  INDIVIDUAL CONSUMERS ({consumerPick.length} selected)
                </span>
                <input
                  value={consumerSearch}
                  onChange={(e) => {
                    setConsumerSearch(e.target.value)
                    if (e.target.value.length >= 3) refreshConsumers(e.target.value)
                  }}
                  placeholder="Search name, account, serial"
                  className="bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-white outline-none text-xs w-48"
                />
              </div>
              <div className="max-h-56 overflow-y-auto bg-white/3 rounded-lg border border-white/5 p-2">
                {consumerLoading ? (
                  <div className="text-white/40 text-sm p-2">Loading…</div>
                ) : filteredConsumers.length === 0 ? (
                  <div className="text-white/40 text-sm p-2">No consumers</div>
                ) : filteredConsumers.map(c => {
                  const on = consumerPick.includes(c.meter_serial)
                  const meta = SITE_TYPE_META[c.site_type] || SITE_TYPE_META.residential
                  const Icon = meta.icon
                  return (
                    <button
                      key={c.meter_serial}
                      type="button"
                      onClick={() => setConsumerPick(prev => toggle(prev, c.meter_serial))}
                      className="flex items-center gap-2 w-full px-2 py-1.5 rounded hover:bg-white/5 text-left"
                    >
                      <span
                        className="w-4 h-4 rounded border flex items-center justify-center shrink-0"
                        style={{
                          borderColor: on ? '#60A5FA' : 'rgba(255,255,255,0.2)',
                          background: on ? 'rgba(96,165,250,0.2)' : 'transparent',
                        }}
                      >
                        {on && <Check size={10} style={{ color: '#60A5FA' }} />}
                      </span>
                      <Icon size={11} style={{ color: meta.color || 'rgba(255,255,255,0.4)' }} />
                      <span className="text-white text-xs">{c.consumer_name}</span>
                      <span className="text-white/40 text-xs ml-2">#{c.account_id}</span>
                      <span className="text-white/30 text-xs ml-auto font-mono">{c.meter_serial}</span>
                      <span className="text-white/30 text-xs">{c.feeder_code}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        )}

        {tab === 'hierarchy' && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-white/50 mb-1.5" style={{ fontSize: 11 }}>
                FEEDERS ({selectedFeederIds.length})
              </div>
              <div className="max-h-56 overflow-y-auto bg-white/3 rounded-lg border border-white/5 p-2">
                {feeders.map(f => {
                  const on = selectedFeederIds.includes(f.name)
                  return (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => setSelectedFeederIds(prev => toggle(prev, f.name))}
                      className="flex items-center gap-2 w-full px-2 py-1.5 rounded hover:bg-white/5 text-left"
                    >
                      <span
                        className="w-4 h-4 rounded border flex items-center justify-center shrink-0"
                        style={{
                          borderColor: on ? '#60A5FA' : 'rgba(255,255,255,0.2)',
                          background: on ? 'rgba(96,165,250,0.2)' : 'transparent',
                        }}
                      >
                        {on && <Check size={10} style={{ color: '#60A5FA' }} />}
                      </span>
                      <span className="text-white text-sm">{f.name}</span>
                      <span className="text-white/30 text-xs ml-auto">{f.substation}</span>
                    </button>
                  )
                })}
              </div>
            </div>
            <div>
              <div className="text-white/50 mb-1.5" style={{ fontSize: 11 }}>
                DISTRIBUTION TRANSFORMERS ({selectedDtrIds.length})
              </div>
              <div className="max-h-56 overflow-y-auto bg-white/3 rounded-lg border border-white/5 p-2">
                {transformers.map(t => {
                  const on = selectedDtrIds.includes(t.name)
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setSelectedDtrIds(prev => toggle(prev, t.name))}
                      className="flex items-center gap-2 w-full px-2 py-1.5 rounded hover:bg-white/5 text-left"
                    >
                      <span
                        className="w-4 h-4 rounded border flex items-center justify-center shrink-0"
                        style={{
                          borderColor: on ? '#60A5FA' : 'rgba(255,255,255,0.2)',
                          background: on ? 'rgba(96,165,250,0.2)' : 'transparent',
                        }}
                      >
                        {on && <Check size={10} style={{ color: '#60A5FA' }} />}
                      </span>
                      <span className="text-white text-sm">{t.name}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
