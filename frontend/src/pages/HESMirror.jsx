import { useCallback, useEffect, useState } from 'react'
import {
  Wifi, WifiOff, AlertTriangle, CheckCircle, Activity,
  Radio, Send, RefreshCw, UploadCloud, Terminal, Clock,
  ChevronDown, ChevronUp, Zap, Search,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { hesAPI, metersAPI } from '@/services/api'
import { ErrorBoundary, UpstreamErrorPanel, useToast } from '@/components/ui'

// All panels below read from /api/v1/hes/* — the EMS SSOT proxy to
// HES routing-service. When the upstream is unreachable we render the
// red UpstreamErrorPanel, never a hard-coded fallback number.

const fmt = (n) => (n ?? 0).toLocaleString()
const ago = (iso) => {
  if (!iso) return '—'
  const s = Math.floor((Date.now() - new Date(iso)) / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

const TABS = ['Network Health', 'Meter Inventory', 'Commands', 'FOTA']
const STATUS_COLOR = { online: '#02C9A8', offline: '#E94B4B', tamper: '#F59E0B', disconnected: '#ABC7FF' }

const formatUpstreamError = (err) => {
  if (!err) return null
  const payload = err.response?.data?.error
  if (payload?.message) return `${payload.code || 'ERR'}: ${payload.message}`
  return err.message || 'HES upstream request failed'
}

const KPI = ({ icon: Icon, label, value, color = '#02C9A8', sub }) => (
  <div className="metric-card">
    <div className="flex items-start justify-between">
      <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: `${color}22` }}>
        <Icon size={18} style={{ color }} />
      </div>
    </div>
    <div className="mt-3">
      <div className="text-white font-black" style={{ fontSize: 26 }}>{value ?? '—'}</div>
      <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 12 }}>{label}</div>
      {sub && <div style={{ color, fontSize: 11, marginTop: 3 }}>{sub}</div>}
    </div>
  </div>
)

// ─── Network Health ───────────────────────────────────────────────────────────
function NetworkHealth({ networkHealth, dcus, commTrend, errors, onRetry }) {
  if (errors.network) {
    return <UpstreamErrorPanel upstream="hes" detail={errors.network} onRetry={onRetry} />
  }

  // networkHealth shape (contracts/hes-integration.md): counts + rates only.
  const donutRows = networkHealth
    ? [
        { name: 'Online',  value: networkHealth.online_meters ?? 0,  itemStyle: { color: '#02C9A8' } },
        { name: 'Offline', value: networkHealth.offline_meters ?? 0, itemStyle: { color: '#E94B4B' } },
        { name: 'Tamper',  value: networkHealth.tamper_meters ?? 0,  itemStyle: { color: '#F59E0B' } },
      ]
    : []
  const donut = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', backgroundColor: '#0A1628', borderColor: '#ABC7FF22' },
    legend: { bottom: 0, textStyle: { color: '#ABC7FF' }, itemWidth: 10, itemHeight: 10 },
    series: [{ type: 'pie', radius: ['50%', '72%'], center: ['50%', '45%'], label: { show: false }, data: donutRows }],
  }

  const trendPoints = (commTrend ?? []).map((d) => ({ day: d.day ?? d.date, value: d.value ?? d.success_rate_pct ?? 0 }))
  const line = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#0A1628', borderColor: '#ABC7FF22',
      formatter: (p) => `${p[0].axisValue}: <b style="color:#02C9A8">${Number(p[0].value).toFixed(1)}%</b>` },
    xAxis: { type: 'category', data: trendPoints.map((d) => d.day),
      axisLine: { lineStyle: { color: '#ABC7FF44' } }, axisLabel: { color: '#ABC7FF' } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: '#ABC7FF', formatter: '{value}%' },
      splitLine: { lineStyle: { color: '#ABC7FF11' } } },
    series: [{
      type: 'line', data: trendPoints.map((d) => Number(d.value).toFixed(2)),
      smooth: true, lineStyle: { color: '#02C9A8', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: '#02C9A844' }, { offset: 1, color: '#02C9A800' }] } },
      symbol: 'circle', symbolSize: 6, itemStyle: { color: '#02C9A8' },
    }],
  }

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 14 }}>
        <KPI icon={Activity}      label="Total Meters"   value={fmt(networkHealth?.total_meters)}   color="#02C9A8" />
        <KPI icon={Wifi}          label="Online"         value={fmt(networkHealth?.online_meters)}  color="#02C9A8" />
        <KPI icon={WifiOff}       label="Offline"        value={fmt(networkHealth?.offline_meters)} color="#E94B4B" />
        <KPI icon={AlertTriangle} label="Tamper"         value={fmt(networkHealth?.tamper_meters)}  color="#F59E0B" />
        <KPI icon={CheckCircle}   label="Comm Success"
          value={networkHealth?.comm_success_rate != null ? `${networkHealth.comm_success_rate}%` : '—'} color="#56CCF2" />
        <KPI icon={Zap}           label="Active Alarms"  value={fmt(networkHealth?.active_alarms)}  color="#E94B4B" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 16 }}>
        <div className="glass-card" style={{ padding: 20 }}>
          <div className="text-white font-semibold mb-2" style={{ fontSize: 14 }}>Meter Status Breakdown</div>
          {donutRows.reduce((a, r) => a + r.value, 0) > 0
            ? <ReactECharts option={donut} style={{ height: 260 }} />
            : <div style={{ padding: 40, textAlign: 'center', color: '#ABC7FF', fontSize: 12 }}>No data yet.</div>}
        </div>
        <div className="glass-card" style={{ padding: 20 }}>
          <div className="text-white font-semibold mb-2" style={{ fontSize: 14 }}>Comm Success Rate — Last 7 Days</div>
          {trendPoints.length > 0
            ? <ReactECharts option={line} style={{ height: 260 }} />
            : <div style={{ padding: 40, textAlign: 'center', color: '#ABC7FF', fontSize: 12 }}>No trend data yet.</div>}
        </div>
      </div>

      <div className="glass-card" style={{ padding: 20 }}>
        <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>DCU Status</div>
        {errors.dcus ? (
          <UpstreamErrorPanel upstream="hes" detail={errors.dcus} onRetry={onRetry} />
        ) : (!dcus || dcus.length === 0) ? (
          <div style={{ color: '#ABC7FF', fontSize: 12, padding: 24, textAlign: 'center' }}>
            No DCUs returned by HES.
          </div>
        ) : (
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              {['DCU ID','Location','Meters Attached','Online Meters','Last Heartbeat','Status'].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {dcus.map((d) => (
                <tr key={d.id ?? d.dcu_id}>
                  <td style={{ color: '#56CCF2', fontFamily: 'monospace' }}>{d.id ?? d.dcu_id}</td>
                  <td>{d.location ?? '—'}</td>
                  <td>{d.total_meters ?? d.meters_connected ?? '—'}</td>
                  <td>{d.online_meters ?? '—'}</td>
                  <td style={{ color: '#ABC7FF' }}>{ago(d.last_comm ?? d.timestamp)}</td>
                  <td>
                    <span className={`badge-${(d.status === 'online' || d.status === 'ONLINE') ? 'ok'
                      : (d.status === 'degraded' || d.status === 'DEGRADED') ? 'medium' : 'critical'}`}>
                      {d.status ?? '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ─── Meter Inventory ──────────────────────────────────────────────────────────
function MeterInventory() {
  // Meter inventory stays on the EMS /meters endpoint — that's still the
  // EMS-owned roll-up used by the Meters page. When we want raw upstream
  // filtering, operators use the Commands tab (proxy-backed).
  const [meters, setMeters] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(0)
  const [expanded, setExpanded] = useState(null)
  const PAGE = 20

  useEffect(() => {
    metersAPI.list({ limit: 100 })
      .then((r) => setMeters(r.data?.meters ?? []))
      .catch(() => setMeters([]))
      .finally(() => setLoading(false))
  }, [])

  const filtered = meters.filter((m) => {
    const q = search.toLowerCase()
    const matchQ = !q || m.serial?.toLowerCase().includes(q) || m.customer_name?.toLowerCase().includes(q)
    const matchS = statusFilter === 'all' || m.status === statusFilter
    return matchQ && matchS
  })

  const paged = filtered.slice(page * PAGE, (page + 1) * PAGE)
  const pages = Math.ceil(filtered.length / PAGE)

  const statusDot = (s) => {
    const c = STATUS_COLOR[s] ?? '#ABC7FF'
    return <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: c, marginRight: 6 }} />
  }

  if (loading) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 42, borderRadius: 8 }} />)}
    </div>
  )

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#ABC7FF88' }} />
          <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(0) }}
            placeholder="Search serial or customer…"
            style={{ width: '100%', paddingLeft: 32, paddingRight: 12, paddingTop: 8, paddingBottom: 8,
              background: 'rgba(255,255,255,0.05)', border: '1px solid #ABC7FF22',
              borderRadius: 8, color: '#fff', fontSize: 13, outline: 'none' }} />
        </div>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(0) }}
          style={{ padding: '8px 12px', background: '#0A1628', border: '1px solid #ABC7FF22',
            borderRadius: 8, color: '#fff', fontSize: 13, cursor: 'pointer' }}>
          {['all','online','offline','tamper'].map((o) => <option key={o} value={o}>{o === 'all' ? 'All Status' : o}</option>)}
        </select>
        <span style={{ alignSelf: 'center', color: '#ABC7FF', fontSize: 12 }}>{filtered.length} meters</span>
      </div>

      {filtered.length === 0 ? (
        <div className="glass-card" style={{ padding: 40, textAlign: 'center', color: '#ABC7FF' }}>No meters match the current filters.</div>
      ) : (
        <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              {['Serial','Customer','Type','Status','Relay','Comm Tech','Firmware','Last Seen',''].map((h) => (
                <th key={h} style={{ fontSize: 11 }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {paged.map((m) => (
                <>
                  <tr key={m.serial} style={{ cursor: 'pointer' }} onClick={() => setExpanded(expanded === m.serial ? null : m.serial)}>
                    <td style={{ color: '#56CCF2', fontFamily: 'monospace', fontSize: 12 }}>{m.serial}</td>
                    <td style={{ fontSize: 12 }}>{m.customer_name ?? '—'}</td>
                    <td style={{ fontSize: 11 }}>{m.meter_type ?? '—'}</td>
                    <td style={{ fontSize: 12 }}>{statusDot(m.status)}{m.status ?? '—'}</td>
                    <td>
                      <span className={`badge-${m.relay_state === 'connected' ? 'ok' : 'critical'}`} style={{ fontSize: 10 }}>
                        {m.relay_state ?? '—'}
                      </span>
                    </td>
                    <td style={{ fontSize: 11 }}>{m.comm_tech ?? '—'}</td>
                    <td style={{ fontSize: 11, fontFamily: 'monospace' }}>{m.firmware_version ?? '—'}</td>
                    <td style={{ fontSize: 11, color: '#ABC7FF' }}>{ago(m.last_seen)}</td>
                    <td>{expanded === m.serial ? <ChevronUp size={14} color="#ABC7FF" /> : <ChevronDown size={14} color="#ABC7FF" />}</td>
                  </tr>
                  {expanded === m.serial && (
                    <tr key={`${m.serial}-exp`}>
                      <td colSpan={9}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12,
                          padding: '12px 16px', background: 'rgba(2,201,168,0.04)', borderTop: '1px solid #02C9A822' }}>
                          {[
                            ['Address', m.address ?? '—'],
                            ['Tariff Class', m.tariff_class ?? '—'],
                            ['Coordinates', m.latitude ? `${m.latitude}, ${m.longitude}` : '—'],
                            ['Account #', m.account_number ?? '—'],
                          ].map(([k, v]) => (
                            <div key={k}>
                              <div style={{ color: '#ABC7FF', fontSize: 10, marginBottom: 2 }}>{k}</div>
                              <div style={{ color: '#fff', fontSize: 13 }}>{v}</div>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
          {pages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: 16 }}>
              <button className="btn-secondary" style={{ fontSize: 12, padding: '4px 12px' }}
                disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</button>
              <span style={{ color: '#ABC7FF', fontSize: 12, alignSelf: 'center' }}>{page + 1} / {pages}</span>
              <button className="btn-secondary" style={{ fontSize: 12, padding: '4px 12px' }}
                disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Commands ─────────────────────────────────────────────────────────────────
function Commands({ cmdHistory, error, onRetry }) {
  const toast = useToast()
  const [rcSerial, setRcSerial] = useState('')
  const [rdSerial, setRdSerial] = useState('')
  const [odrSerial, setOdrSerial] = useState('')
  const [odrLoading, setOdrLoading] = useState(false)
  const [syncLoading, setSyncLoading] = useState(false)
  const [cmdLog, setCmdLog] = useState([])

  useEffect(() => { setCmdLog(cmdHistory ?? []) }, [cmdHistory])

  const addLog = (serial, cmd, status) => {
    const ts = new Date().toLocaleString('en-ZA', { dateStyle: 'short', timeStyle: 'medium' })
    setCmdLog((prev) => [{ ts, serial, cmd, status, op: 'admin' }, ...prev])
  }

  // Commands go through the HES proxy so HES remains SSOT for command lifecycle.
  const sendCommand = async (type, serial, label) => {
    if (!serial?.trim()) { toast.error(`${label} failed`, 'Enter a meter serial first'); return }
    try {
      await hesAPI.postCommand({ type, meter_serial: serial.trim(), payload: {} })
      toast.success(`${label} sent to ${serial}`)
      addLog(serial, label, 'ok')
    } catch (e) {
      toast.error(`${label} failed for ${serial}`, formatUpstreamError(e))
      addLog(serial, label, 'failed')
    }
  }

  const handleODR = async () => {
    if (!odrSerial.trim()) { toast.error('On-demand read failed', 'Enter a meter serial first'); return }
    setOdrLoading(true)
    try {
      await hesAPI.postCommand({ type: 'READ_BILLING_REGISTER', meter_serial: odrSerial.trim(), payload: {} })
      toast.success(`Read request sent for ${odrSerial}`)
      addLog(odrSerial, 'On-Demand Read', 'ok')
    } catch (e) {
      toast.error(`Read failed for ${odrSerial}`, formatUpstreamError(e))
      addLog(odrSerial, 'On-Demand Read', 'failed')
    } finally {
      setOdrLoading(false)
    }
  }

  const handleSync = async () => {
    setSyncLoading(true)
    try {
      await hesAPI.postCommand({ type: 'TIME_SYNC_BROADCAST', meter_serial: '*', payload: {} })
      toast.success('Time-sync broadcast sent')
      addLog('ALL', 'Time Sync', 'ok')
    } catch (e) {
      toast.error('Time-sync broadcast failed', formatUpstreamError(e))
      addLog('ALL', 'Time Sync', 'failed')
    } finally {
      setSyncLoading(false)
    }
  }

  const inputStyle = {
    padding: '8px 12px', background: 'rgba(255,255,255,0.05)',
    border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff',
    fontSize: 13, outline: 'none', fontFamily: 'monospace', width: '100%',
  }

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
        <div className="glass-card" style={{ padding: 20 }}>
          <div className="flex items-center gap-2 mb-4">
            <Send size={16} color="#02C9A8" />
            <span className="text-white font-semibold" style={{ fontSize: 14 }}>Remote Connect / Disconnect</span>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ color: '#ABC7FF', fontSize: 11, display: 'block', marginBottom: 4 }}>Meter Serial</label>
            <input style={inputStyle} placeholder="ESK-XXXXXXX" value={rcSerial} onChange={(e) => setRcSerial(e.target.value)} />
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn-primary" style={{ flex: 1, fontSize: 12 }}
              onClick={() => sendCommand('REMOTE_CONNECT', rcSerial, 'Remote Connect')}>
              <CheckCircle size={13} style={{ marginRight: 4 }} /> Connect
            </button>
            <button className="btn-secondary" style={{ flex: 1, fontSize: 12, color: '#E94B4B' }}
              onClick={() => sendCommand('REMOTE_DISCONNECT', rdSerial || rcSerial, 'Remote Disconnect')}>
              <WifiOff size={13} style={{ marginRight: 4 }} /> Disconnect
            </button>
          </div>
        </div>

        <div className="glass-card" style={{ padding: 20 }}>
          <div className="flex items-center gap-2 mb-4">
            <Terminal size={16} color="#56CCF2" />
            <span className="text-white font-semibold" style={{ fontSize: 14 }}>On-Demand Read</span>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ color: '#ABC7FF', fontSize: 11, display: 'block', marginBottom: 4 }}>Meter Serial</label>
            <input style={inputStyle} placeholder="ESK-XXXXXXX" value={odrSerial} onChange={(e) => setOdrSerial(e.target.value)} />
          </div>
          <button className="btn-primary" style={{ width: '100%', marginTop: 12, fontSize: 12, justifyContent: 'center' }}
            onClick={handleODR} disabled={odrLoading}>
            {odrLoading
              ? <><RefreshCw size={13} style={{ marginRight: 4, animation: 'spin 1s linear infinite' }} /> Sending…</>
              : 'Read Now'}
          </button>
        </div>

        <div className="glass-card" style={{ padding: 20 }}>
          <div className="flex items-center gap-2 mb-4">
            <Clock size={16} color="#ABC7FF" />
            <span className="text-white font-semibold" style={{ fontSize: 14 }}>Time Synchronisation</span>
          </div>
          <p style={{ color: '#ABC7FF', fontSize: 12, marginBottom: 12 }}>
            Broadcast an NTP-aligned sync command to every meter registered with HES.
          </p>
          <button className="btn-primary" style={{ width: '100%', fontSize: 12, justifyContent: 'center' }}
            onClick={handleSync} disabled={syncLoading}>
            {syncLoading
              ? <><RefreshCw size={13} style={{ marginRight: 4, animation: 'spin 1s linear infinite' }} /> Broadcasting…</>
              : <><RefreshCw size={13} style={{ marginRight: 4 }} />Sync All Meters</>}
          </button>
        </div>
      </div>

      <div className="glass-card" style={{ padding: 20 }}>
        <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>Command History</div>
        {error ? (
          <UpstreamErrorPanel upstream="hes" detail={error} onRetry={onRetry} />
        ) : cmdLog.length === 0 ? (
          <div style={{ color: '#ABC7FF', fontSize: 12, padding: 24, textAlign: 'center' }}>
            No commands in the last 24 h.
          </div>
        ) : (
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              {['Timestamp','Meter Serial','Command','Status','Operator'].map((h) => <th key={h}>{h}</th>)}
            </tr></thead>
            <tbody>
              {cmdLog.map((r, i) => (
                <tr key={i}>
                  <td style={{ color: '#ABC7FF', fontSize: 11 }}>{r.ts ?? r.timestamp}</td>
                  <td style={{ color: '#56CCF2', fontFamily: 'monospace', fontSize: 12 }}>{r.serial ?? r.meter_serial}</td>
                  <td style={{ fontSize: 12 }}>{r.cmd ?? r.command_type ?? r.type}</td>
                  <td><span className={`badge-${(r.status === 'ok' || r.status === 'CONFIRMED') ? 'ok' : 'critical'}`} style={{ fontSize: 10 }}>{r.status}</span></td>
                  <td style={{ fontSize: 12, color: '#ABC7FF' }}>{r.op ?? r.operator ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ─── FOTA ─────────────────────────────────────────────────────────────────────
function FOTA({ fotaJobs, fwDist, errors, onRetry }) {
  const toast = useToast()
  const [targetFw, setTargetFw] = useState('v2.2.0')
  const [scope, setScope] = useState('All')
  const [scheduling, setScheduling] = useState(false)

  const handleSchedule = async () => {
    setScheduling(true)
    try {
      // Dispatch a real FIRMWARE_UPGRADE command via HES. If upstream auth
      // or the W2B FOTA service isn't ready, the toast shows the real error
      // instead of the previous fake success.
      await hesAPI.postCommand({
        type: 'FIRMWARE_UPGRADE',
        meter_serial: '*',
        payload: { target_firmware: targetFw, scope },
      })
      toast.success(`FOTA job scheduled: ${targetFw} → ${scope}`)
    } catch (e) {
      toast.error('FOTA schedule failed', formatUpstreamError(e))
    } finally {
      setScheduling(false)
    }
  }

  const fwBarOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#0A1628', borderColor: '#ABC7FF22' },
    xAxis: { type: 'category', data: (fwDist ?? []).map((f) => f.version),
      axisLine: { lineStyle: { color: '#ABC7FF44' } }, axisLabel: { color: '#ABC7FF' } },
    yAxis: { type: 'value', axisLabel: { color: '#ABC7FF' }, splitLine: { lineStyle: { color: '#ABC7FF11' } } },
    series: [{
      type: 'bar', data: (fwDist ?? []).map((f) => f.count),
      barMaxWidth: 40, itemStyle: { color: '#02C9A8', borderRadius: [4,4,0,0] },
      label: { show: true, position: 'top', color: '#fff', fontSize: 11 },
    }],
  }

  const progressBar = (updated, total) => {
    const pct = total ? Math.round((updated / total) * 100) : 0
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ flex: 1, background: '#ABC7FF22', borderRadius: 4, height: 6, overflow: 'hidden' }}>
          <div style={{ width: `${pct}%`, height: '100%', background: '#02C9A8', borderRadius: 4 }} />
        </div>
        <span style={{ color: '#ABC7FF', fontSize: 11, width: 32 }}>{pct}%</span>
      </div>
    )
  }

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <div className="glass-card" style={{ padding: 20 }}>
          <div className="text-white font-semibold mb-1" style={{ fontSize: 14 }}>Meters by Firmware Version</div>
          {errors.fwDist ? (
            <UpstreamErrorPanel upstream="hes" detail={errors.fwDist} onRetry={onRetry} />
          ) : (!fwDist || fwDist.length === 0) ? (
            <div style={{ color: '#ABC7FF', fontSize: 12, padding: 24, textAlign: 'center' }}>
              No firmware distribution data from HES.
            </div>
          ) : (
            <ReactECharts option={fwBarOption} style={{ height: 240 }} />
          )}
        </div>

        <div className="glass-card" style={{ padding: 20 }}>
          <div className="flex items-center gap-2 mb-4">
            <UploadCloud size={16} color="#02C9A8" />
            <span className="text-white font-semibold" style={{ fontSize: 14 }}>Schedule FOTA Job</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ color: '#ABC7FF', fontSize: 11, display: 'block', marginBottom: 4 }}>Target Firmware</label>
              <input value={targetFw} onChange={(e) => setTargetFw(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', background: '#0A1628',
                  border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 13 }} />
            </div>
            <div>
              <label style={{ color: '#ABC7FF', fontSize: 11, display: 'block', marginBottom: 4 }}>Target Scope</label>
              <input value={scope} onChange={(e) => setScope(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', background: '#0A1628',
                  border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 13 }} />
            </div>
            <button className="btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: 4, fontSize: 13 }}
              onClick={handleSchedule} disabled={scheduling}>
              {scheduling ? 'Scheduling…' : <><UploadCloud size={14} style={{ marginRight: 6 }} />Schedule FOTA</>}
            </button>
          </div>
        </div>
      </div>

      <div className="glass-card" style={{ padding: 20 }}>
        <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>Active FOTA Jobs</div>
        {errors.fotaJobs ? (
          <UpstreamErrorPanel upstream="hes" detail={errors.fotaJobs} onRetry={onRetry} />
        ) : (!fotaJobs || fotaJobs.length === 0) ? (
          <div style={{ color: '#ABC7FF', fontSize: 12, padding: 24, textAlign: 'center' }}>
            No active FOTA jobs.
          </div>
        ) : (
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              {['Job ID','Target','Total Meters','Updated','Failed','Progress','Status'].map((h) => <th key={h}>{h}</th>)}
            </tr></thead>
            <tbody>
              {fotaJobs.map((j) => (
                <tr key={j.id ?? j.job_id}>
                  <td style={{ color: '#56CCF2', fontFamily: 'monospace', fontSize: 12 }}>{j.id ?? j.job_id}</td>
                  <td style={{ fontSize: 12 }}>{j.target ?? j.firmware_version}</td>
                  <td>{j.total_meters ?? j.total ?? '—'}</td>
                  <td style={{ color: '#02C9A8' }}>{j.updated_count ?? j.updated ?? 0}</td>
                  <td style={{ color: (j.failed_count ?? j.failed) ? '#E94B4B' : '#ABC7FF' }}>{j.failed_count ?? j.failed ?? 0}</td>
                  <td style={{ width: 160 }}>{progressBar(j.updated_count ?? j.updated ?? 0, j.total_meters ?? j.total ?? 0)}</td>
                  <td>
                    <span className={`badge-${j.status === 'complete' ? 'ok' : j.status === 'running' ? 'info' : 'critical'}`} style={{ fontSize: 10 }}>
                      {j.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function HESMirror() {
  const [tab, setTab] = useState(0)
  const [networkHealth, setNetworkHealth] = useState(null)
  const [dcus, setDcus] = useState([])
  const [commTrend, setCommTrend] = useState([])
  const [cmdHistory, setCmdHistory] = useState([])
  const [fotaJobs, setFotaJobs] = useState([])
  const [fwDist, setFwDist] = useState([])
  const [errors, setErrors] = useState({ network: null, dcus: null, trend: null, cmds: null, fotaJobs: null, fwDist: null })
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const next = { network: null, dcus: null, trend: null, cmds: null, fotaJobs: null, fwDist: null }

    await Promise.all([
      hesAPI.networkHealth()
        .then((r) => setNetworkHealth(r.data))
        .catch((e) => { next.network = formatUpstreamError(e) }),
      hesAPI.dcus()
        .then((r) => setDcus(r.data?.items ?? r.data?.dcus ?? []))
        .catch((e) => { next.dcus = formatUpstreamError(e) }),
      hesAPI.commTrend({ days: 7 })
        .then((r) => setCommTrend(r.data?.trend ?? r.data?.items ?? []))
        .catch((e) => { next.trend = formatUpstreamError(e) }),
      hesAPI.commands({ limit: 20 })
        .then((r) => setCmdHistory(r.data?.items ?? r.data?.commands ?? []))
        .catch((e) => { next.cmds = formatUpstreamError(e) }),
      hesAPI.fota()
        .then((r) => setFotaJobs(r.data?.items ?? r.data?.jobs ?? []))
        .catch((e) => { next.fotaJobs = formatUpstreamError(e) }),
      hesAPI.firmwareDistribution()
        .then((r) => setFwDist(r.data?.items ?? r.data?.versions ?? []))
        .catch((e) => { next.fwDist = formatUpstreamError(e) }),
    ])

    setErrors(next)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const panels = [
    <ErrorBoundary title="Network-health panel crashed" onRetry={load}>
      <NetworkHealth networkHealth={networkHealth} dcus={dcus} commTrend={commTrend}
        errors={errors} onRetry={load} />
    </ErrorBoundary>,
    <ErrorBoundary title="Meter inventory panel crashed" onRetry={load}>
      <MeterInventory />
    </ErrorBoundary>,
    <ErrorBoundary title="Commands panel crashed" onRetry={load}>
      <Commands cmdHistory={cmdHistory} error={errors.cmds} onRetry={load} />
    </ErrorBoundary>,
    <ErrorBoundary title="FOTA panel crashed" onRetry={load}>
      <FOTA fotaJobs={fotaJobs} fwDist={fwDist} errors={errors} onRetry={load} />
    </ErrorBoundary>,
  ]

  return (
    <div style={{ padding: '24px 28px', minHeight: '100vh', background: '#0A0F1E' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: '#02C9A822',
            display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Radio size={18} color="#02C9A8" />
          </div>
          <div>
            <h1 className="text-white font-black" style={{ fontSize: 22, lineHeight: 1 }}>HES Mirror Panel</h1>
            <p style={{ color: '#ABC7FF', fontSize: 12, marginTop: 2 }}>
              Source of truth: HES routing-service (via EMS proxy /api/v1/hes/*) — AMI Communication & Control
            </p>
          </div>
          <button type="button" onClick={load} className="btn-secondary"
            style={{ marginLeft: 'auto', fontSize: 12 }} disabled={loading}>
            <RefreshCw size={13} style={{ marginRight: 4, animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            Refresh
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 22, background: 'rgba(255,255,255,0.04)',
        padding: 4, borderRadius: 12, width: 'fit-content' }}>
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)}
            style={{
              padding: '7px 18px', borderRadius: 9, fontSize: 13, fontWeight: 600,
              cursor: 'pointer', border: 'none', transition: 'all 0.2s',
              background: tab === i ? 'linear-gradient(135deg,#0A3690,#02C9A8)' : 'transparent',
              color: tab === i ? '#fff' : '#ABC7FF',
            }}>
            {t}
          </button>
        ))}
      </div>

      {panels[tab]}
    </div>
  )
}
