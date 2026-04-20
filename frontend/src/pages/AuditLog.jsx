import { useState, useMemo, useEffect, useCallback } from 'react'
import {
  Download, Search, Filter, LogIn, Terminal, Bell,
  Settings, Cpu, RefreshCw, ChevronDown,
} from 'lucide-react'
import { auditAPI } from '@/services/api'
import { todayIso, daysAgoIso } from '@/components/ui'

const EVENT_TYPES = ['All', 'Login', 'Command', 'Alarm', 'Configuration', 'System']

const TYPE_BADGE = {
  Login:         'badge-info',
  Command:       'badge-ok',
  Alarm:         'badge-high',
  Configuration: 'badge-medium',
  System:        'badge-low',
}

const TYPE_ICON = {
  Login:         LogIn,
  Command:       Terminal,
  Alarm:         Bell,
  Configuration: Settings,
  System:        Cpu,
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmtTs(iso) {
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} SAST`
}

function StatCard(props) {
  const { label, value, color } = props
  const CardIcon = props.icon
  return (
    <div className="metric-card" style={{ minWidth: 150 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ width: 36, height: 36, borderRadius: 9, background: `${color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <CardIcon size={16} style={{ color }} />
        </div>
      </div>
      <div style={{ fontSize: 28, fontWeight: 900, color: '#fff', lineHeight: 1.1, marginTop: 8 }}>{value}</div>
      <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginTop: 2 }}>{label}</div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function AuditLog() {
  // Default to last 7 days (today-7 → today) instead of a stale hardcoded date.
  const [dateFrom,  setDateFrom]  = useState(() => daysAgoIso(7))
  const [dateTo,    setDateTo]    = useState(() => todayIso())
  const [typeFilter, setTypeFilter] = useState('All')
  const [userFilter, setUserFilter] = useState('All')
  const [search,    setSearch]    = useState('')
  const [page,      setPage]      = useState(1)
  const PAGE_SIZE = 15

  const [events, setEvents] = useState([])
  const [summary, setSummary] = useState({ total: 0, commands: 0, alarms: 0, configs: 0, users: [] })
  const [loading, setLoading] = useState(true)
  const [usersList, setUsersList] = useState(['All'])

  const fetchEvents = useCallback(async (filters = {}) => {
    setLoading(true)
    try {
      const res = await auditAPI.events(filters)
      setEvents(res.data.events)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    fetchEvents()
    auditAPI.summary().then(res => {
      setSummary(res.data)
      setUsersList(['All', ...res.data.users])
    }).catch(console.error)
  }, [fetchEvents])

  // Re-fetch when filters change
  useEffect(() => {
    const filters = {}
    if (typeFilter !== 'All') filters.event_type = typeFilter
    if (userFilter !== 'All') filters.user = userFilter
    if (dateFrom) filters.from_date = dateFrom
    if (dateTo) filters.to_date = dateTo
    fetchEvents(filters)
  }, [dateFrom, dateTo, typeFilter, userFilter, fetchEvents])

  // Client-side search within fetched events
  const filtered = useMemo(() => {
    return events.filter(ev => {
      if (search) {
        const q = search.toLowerCase()
        if (
          !ev.action.toLowerCase().includes(q) &&
          !ev.resource.toLowerCase().includes(q) &&
          !ev.user.toLowerCase().includes(q)
        ) return false
      }
      return true
    }).sort((a, b) => new Date(b.ts) - new Date(a.ts))
  }, [events, search])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageData   = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  // Summary stats from API
  const totalToday    = summary.total
  const commandCount  = summary.commands
  const alarmAckCount = summary.alarms
  const configCount   = summary.configs

  // Export CSV
  const exportCSV = () => {
    const headers = ['Timestamp', 'User', 'Role', 'Event Type', 'Action', 'Resource', 'IP Address', 'Result']
    const rows = filtered.map(ev => [
      fmtTs(ev.ts), ev.user, ev.role, ev.type, ev.action, ev.resource, ev.ip, ev.result,
    ])
    const csv = [headers, ...rows].map(r => r.map(c => `"${c}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url; a.download = `audit-log-${dateFrom}.csv`; a.click()
    URL.revokeObjectURL(url)
  }

  const inputStyle = {
    background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)',
    borderRadius: 8, color: '#fff', padding: '8px 12px', fontSize: 13, outline: 'none',
  }

  const selectStyle = { ...inputStyle, color: '#ABC7FF', cursor: 'pointer' }

  return (
    <div className="animate-slide-up" style={{ padding: 24, minHeight: '100vh', background: '#0A0F1E' }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 900, color: '#fff', margin: 0 }}>Audit Log</h1>
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13, margin: '4px 0 0' }}>
            REQ-13 — System events · User actions · Command history
          </p>
        </div>
        <button onClick={exportCSV} className="btn-primary" style={{ gap: 7, padding: '9px 18px', fontSize: 13 }}>
          <Download size={14} /> Export Audit CSV
        </button>
      </div>

      {/* Summary stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 20 }}>
        <StatCard label="Total Events Today" value={totalToday}    color="#56CCF2" icon={RefreshCw} />
        <StatCard label="Commands Issued"    value={commandCount}  color="#02C9A8" icon={Terminal} />
        <StatCard label="Alarms Acknowledged" value={alarmAckCount} color="#F97316" icon={Bell} />
        <StatCard label="Config Changes"     value={configCount}   color="#F59E0B" icon={Settings} />
      </div>

      {/* Filter bar */}
      <div className="glass-card" style={{ padding: 14, marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          {/* Date range */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', fontWeight: 700, whiteSpace: 'nowrap' }}>From</span>
            <input
              type="date" value={dateFrom}
              onChange={e => { setDateFrom(e.target.value); setPage(1) }}
              style={{ ...inputStyle, colorScheme: 'dark' }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', fontWeight: 700, whiteSpace: 'nowrap' }}>To</span>
            <input
              type="date" value={dateTo}
              onChange={e => { setDateTo(e.target.value); setPage(1) }}
              style={{ ...inputStyle, colorScheme: 'dark' }}
            />
          </div>

          {/* Event type */}
          <select value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1) }} style={selectStyle}>
            {EVENT_TYPES.map(t => <option key={t} value={t} style={{ background: '#0A1535' }}>{t === 'All' ? 'All Event Types' : t}</option>)}
          </select>

          {/* User */}
          <select value={userFilter} onChange={e => { setUserFilter(e.target.value); setPage(1) }} style={selectStyle}>
            {usersList.map(u => <option key={u} value={u} style={{ background: '#0A1535' }}>{u === 'All' ? 'All Users' : u}</option>)}
          </select>

          {/* Search */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 200,
            background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)',
            borderRadius: 8, padding: '8px 12px' }}>
            <Search size={14} style={{ color: 'rgba(255,255,255,0.3)', flexShrink: 0 }} />
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Search actions, resources, users…"
              style={{ background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, flex: 1, minWidth: 0 }}
            />
          </div>

          {/* Result count */}
          <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', whiteSpace: 'nowrap' }}>
            {filtered.length} event{filtered.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="glass-card" style={{ overflow: 'hidden', marginBottom: 16 }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ minWidth: 900 }}>
            <thead>
              <tr>
                <th style={{ width: 190 }}>Timestamp</th>
                <th style={{ width: 100 }}>User</th>
                <th style={{ width: 100 }}>Role</th>
                <th style={{ width: 110 }}>Event Type</th>
                <th>Action</th>
                <th>Resource</th>
                <th style={{ width: 110 }}>IP Address</th>
                <th style={{ width: 80 }}>Result</th>
              </tr>
            </thead>
            <tbody>
              {pageData.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: '32px', color: 'rgba(255,255,255,0.3)' }}>
                    No events match the current filters
                  </td>
                </tr>
              ) : pageData.map((ev, i) => {
                const TypeIcon = TYPE_ICON[ev.type] || Cpu
                return (
                  <tr key={i}>
                    <td style={{ fontFamily: "'Courier New', Courier, monospace", fontSize: 12, color: 'rgba(255,255,255,0.55)', whiteSpace: 'nowrap' }}>
                      {fmtTs(ev.ts)}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{
                          width: 22, height: 22, borderRadius: '50%',
                          background: 'linear-gradient(135deg, #0A3690, #56CCF2)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 9, fontWeight: 900, color: '#fff', flexShrink: 0,
                        }}>
                          {ev.user[0].toUpperCase()}
                        </div>
                        <span style={{ fontSize: 13, color: '#fff', fontWeight: 600 }}>{ev.user}</span>
                      </div>
                    </td>
                    <td>
                      <span style={{
                        fontSize: 11, fontWeight: 700,
                        color: ev.role === 'Admin' ? '#E94B4B' : ev.role === 'Supervisor' ? '#F59E0B' : '#56CCF2',
                      }}>
                        {ev.role}
                      </span>
                    </td>
                    <td>
                      <span className={TYPE_BADGE[ev.type] || 'badge-low'} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <TypeIcon size={9} />
                        {ev.type}
                      </span>
                    </td>
                    <td style={{ fontSize: 13, color: 'rgba(255,255,255,0.8)' }}>{ev.action}</td>
                    <td style={{ fontFamily: "'Courier New', Courier, monospace", fontSize: 12, color: '#ABC7FF' }}>
                      {ev.resource}
                    </td>
                    <td style={{ fontFamily: "'Courier New', Courier, monospace", fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>
                      {ev.ip}
                    </td>
                    <td>
                      <span style={{
                        fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                        background: ev.result === 'Success' ? 'rgba(2,201,168,0.15)'
                          : ev.result === 'Running'  ? 'rgba(86,204,242,0.15)'
                          : ev.result === 'Queued'   ? 'rgba(245,158,11,0.15)'
                          : 'rgba(233,75,75,0.15)',
                        color: ev.result === 'Success' ? '#02C9A8'
                          : ev.result === 'Running'  ? '#56CCF2'
                          : ev.result === 'Queued'   ? '#F59E0B'
                          : '#E94B4B',
                        border: `1px solid ${
                          ev.result === 'Success' ? 'rgba(2,201,168,0.3)'
                          : ev.result === 'Running'  ? 'rgba(86,204,242,0.3)'
                          : ev.result === 'Queued'   ? 'rgba(245,158,11,0.3)'
                          : 'rgba(233,75,75,0.3)'
                        }`,
                      }}>
                        {ev.result}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="btn-secondary"
            style={{ padding: '6px 14px', fontSize: 13 }}
          >
            ← Prev
          </button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
            <button key={p} onClick={() => setPage(p)} style={{
              width: 34, height: 34, borderRadius: 6, cursor: 'pointer',
              fontWeight: 700, fontSize: 13,
              background: page === p ? 'linear-gradient(45deg, #11ABBE, #3C63FF)' : 'rgba(255,255,255,0.05)',
              border: `1px solid ${page === p ? 'transparent' : 'rgba(255,255,255,0.1)'}`,
              color: page === p ? '#fff' : 'rgba(255,255,255,0.5)',
            }}>{p}</button>
          ))}
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="btn-secondary"
            style={{ padding: '6px 14px', fontSize: 13 }}
          >
            Next →
          </button>
        </div>
      )}

      {/* Footer note */}
      <div style={{
        marginTop: 20, padding: '10px 16px', borderRadius: 8,
        background: 'rgba(10,54,144,0.1)', border: '1px solid rgba(171,199,255,0.08)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#02C9A8', boxShadow: '0 0 6px #02C9A8', flexShrink: 0 }} />
        <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)' }}>
          Audit log retained for 365 days. All events timestamped in SAST (UTC+2). Exported CSV includes full ISO-8601 timestamps.
        </span>
      </div>
    </div>
  )
}
