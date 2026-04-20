/**
 * SystemManagement — SMOC-12 System Management page (5 demo points).
 * 5 tabs: Meter Registry, LV Device Registry, Supplier Performance,
 *         Equipment Performance, Asset Search.
 */
import { useState, useEffect, useCallback } from 'react'
import {
  Settings, Cpu, Search, RefreshCw, AlertTriangle,
  CheckCircle, Activity, Package, Gauge, Server,
  ChevronDown, Download,
} from 'lucide-react'
import { systemManagementAPI } from '@/services/api'

// ---- Constants ---------------------------------------------------------------

const TABS = [
  { key: 'meters',     label: 'Meter Registry',        icon: Gauge },
  { key: 'devices',    label: 'LV Device Registry',    icon: Server },
  { key: 'suppliers',  label: 'Supplier Performance',  icon: Package },
  { key: 'equipment',  label: 'Equipment Performance', icon: Activity },
  { key: 'search',     label: 'Asset Search',          icon: Search },
]

const STATUS_COLORS = {
  online:       { color: '#02C9A8', bg: 'rgba(2,201,168,0.12)' },
  offline:      { color: '#E94B4B', bg: 'rgba(233,75,75,0.12)' },
  tamper:       { color: '#F59E0B', bg: 'rgba(245,158,11,0.12)' },
  disconnected: { color: '#6B7280', bg: 'rgba(107,114,128,0.12)' },
  active:       { color: '#02C9A8', bg: 'rgba(2,201,168,0.12)' },
  normal:       { color: '#02C9A8', bg: 'rgba(2,201,168,0.12)' },
  warning:      { color: '#F59E0B', bg: 'rgba(245,158,11,0.12)' },
  critical:     { color: '#E94B4B', bg: 'rgba(233,75,75,0.12)' },
  degraded:     { color: '#F97316', bg: 'rgba(249,115,22,0.12)' },
}

const inputStyle = {
  background: 'rgba(10,54,144,0.25)',
  border: '1px solid rgba(171,199,255,0.15)',
  borderRadius: 8,
  color: '#fff',
  padding: '8px 12px',
  fontSize: 13,
  outline: 'none',
}

const selectStyle = { ...inputStyle, color: '#ABC7FF', cursor: 'pointer' }

// ---- Helpers -----------------------------------------------------------------

function StatusBadge({ status }) {
  const cfg = STATUS_COLORS[status] || STATUS_COLORS.offline
  return (
    <span
      style={{
        fontSize: 11, fontWeight: 700, padding: '2px 10px', borderRadius: 4,
        background: cfg.bg, color: cfg.color,
        border: `1px solid ${cfg.color}30`,
        textTransform: 'uppercase',
      }}
    >
      {status}
    </span>
  )
}

function StatCard({ label, value, sub, color, icon: Icon }) {
  return (
    <div className="metric-card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{
          width: 36, height: 36, borderRadius: 9,
          background: `${color}20`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={16} style={{ color }} />
        </div>
      </div>
      <div style={{ fontSize: 28, fontWeight: 900, color: '#fff', lineHeight: 1.1, marginTop: 8 }}>
        {value}
      </div>
      <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginTop: 2 }}>{label}</div>
      {sub && (
        <div style={{ fontSize: 11, color, marginTop: 4 }}>{sub}</div>
      )}
    </div>
  )
}

// ---- Tab: Meter Registry -----------------------------------------------------

function MeterRegistryTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    systemManagementAPI.meterRegistry()
      .then(res => setData(res.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSkeleton rows={6} />
  if (!data) return <ErrorState />

  const uniqueMfrs = [...new Set(data.groups.map(g => g.manufacturer))]
  const uniqueModels = [...new Set(data.groups.map(g => g.model))]

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Total Meters" value={data.total_meters} color="#56CCF2" icon={Gauge} />
        <StatCard label="Manufacturers" value={uniqueMfrs.length} color="#02C9A8" icon={Package} />
        <StatCard label="Models" value={uniqueModels.length} color="#F59E0B" icon={Cpu} />
        <StatCard label="Registry Groups" value={data.groups.length} color="#ABC7FF" icon={Settings} />
      </div>

      {/* Table */}
      <div className="glass-card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ minWidth: 900 }}>
            <thead>
              <tr>
                <th>Manufacturer</th>
                <th>Model</th>
                <th>Firmware</th>
                <th>Comm Technology</th>
                <th>Meter Class</th>
                <th style={{ textAlign: 'right' }}>Count</th>
                <th>Earliest Install</th>
                <th>Latest Install</th>
              </tr>
            </thead>
            <tbody>
              {data.groups.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 32, color: 'rgba(255,255,255,0.3)' }}>
                    No meter registry data available
                  </td>
                </tr>
              ) : data.groups.map((g, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 700, color: '#fff' }}>{g.manufacturer}</td>
                  <td style={{ color: '#ABC7FF', fontFamily: "'Courier New', monospace", fontSize: 12 }}>
                    {g.model}
                  </td>
                  <td style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{g.firmware_version}</td>
                  <td>
                    <span style={{
                      fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                      background: 'rgba(86,204,242,0.12)', color: '#56CCF2',
                      border: '1px solid rgba(86,204,242,0.3)',
                    }}>
                      {g.comm_technology}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{g.meter_class || 'N/A'}</td>
                  <td style={{ textAlign: 'right', fontWeight: 900, color: '#fff', fontSize: 15 }}>{g.count}</td>
                  <td style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', fontFamily: "'Courier New', monospace" }}>
                    {g.earliest_installed ? new Date(g.earliest_installed).toLocaleDateString() : '--'}
                  </td>
                  <td style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', fontFamily: "'Courier New', monospace" }}>
                    {g.latest_installed ? new Date(g.latest_installed).toLocaleDateString() : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---- Tab: LV Device Registry -------------------------------------------------

function DeviceRegistryTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    systemManagementAPI.deviceRegistry()
      .then(res => setData(res.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSkeleton rows={5} />
  if (!data) return <ErrorState />

  const dcus = data.devices.filter(d => d.type === 'DCU')
  const transformers = data.devices.filter(d => d.type === 'Transformer')
  const sensors = data.devices.filter(d => d.type === 'Sensor')

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Total Devices" value={data.total_devices} color="#56CCF2" icon={Server} />
        <StatCard label="DCUs" value={dcus.reduce((s, d) => s + d.count, 0)} color="#02C9A8" icon={Cpu} />
        <StatCard
          label="Transformers"
          value={transformers.reduce((s, d) => s + d.count, 0)}
          color="#F59E0B" icon={Activity}
        />
        <StatCard label="Sensors" value={sensors.reduce((s, d) => s + d.count, 0)} color="#ABC7FF" icon={Gauge} />
      </div>

      {/* Table */}
      <div className="glass-card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ minWidth: 700 }}>
            <thead>
              <tr>
                <th>Device Type</th>
                <th>Manufacturer / Supplier</th>
                <th>Model / Subtype</th>
                <th style={{ textAlign: 'right' }}>Count</th>
              </tr>
            </thead>
            <tbody>
              {data.devices.map((d, i) => (
                <tr key={i}>
                  <td>
                    <span style={{
                      fontSize: 11, fontWeight: 700, padding: '2px 10px', borderRadius: 4,
                      background: d.type === 'DCU' ? 'rgba(2,201,168,0.12)' :
                        d.type === 'Transformer' ? 'rgba(245,158,11,0.12)' : 'rgba(86,204,242,0.12)',
                      color: d.type === 'DCU' ? '#02C9A8' :
                        d.type === 'Transformer' ? '#F59E0B' : '#56CCF2',
                      border: `1px solid ${d.type === 'DCU' ? 'rgba(2,201,168,0.3)' :
                        d.type === 'Transformer' ? 'rgba(245,158,11,0.3)' : 'rgba(86,204,242,0.3)'}`,
                    }}>
                      {d.type}
                    </span>
                  </td>
                  <td style={{ fontWeight: 600, color: '#fff' }}>{d.manufacturer}</td>
                  <td style={{ color: '#ABC7FF', fontFamily: "'Courier New', monospace", fontSize: 12 }}>
                    {d.model}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 900, color: '#fff', fontSize: 15 }}>{d.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---- Tab: Supplier Performance -----------------------------------------------

function SupplierPerformanceTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    systemManagementAPI.supplierPerformance()
      .then(res => setData(res.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSkeleton rows={3} />
  if (!data || data.suppliers.length === 0) return <ErrorState msg="No supplier data available" />

  return (
    <div className="space-y-4">
      {/* Supplier cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {data.suppliers.map(s => {
          const commColor = s.comm_success_rate >= 90 ? '#02C9A8' :
            s.comm_success_rate >= 80 ? '#F59E0B' : '#E94B4B'
          const alarmColor = s.alarm_rate_per_1000 <= 10 ? '#02C9A8' :
            s.alarm_rate_per_1000 <= 30 ? '#F59E0B' : '#E94B4B'
          return (
            <div key={s.supplier_id} className="glass-card p-5">
              <div className="flex items-center gap-3 mb-4">
                <div style={{
                  width: 42, height: 42, borderRadius: 10,
                  background: 'linear-gradient(135deg, #0A3690, #56CCF2)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 16, fontWeight: 900, color: '#fff',
                }}>
                  {s.supplier_name[0]}
                </div>
                <div>
                  <div className="text-white font-bold" style={{ fontSize: 15 }}>{s.supplier_name}</div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{s.country}</div>
                </div>
              </div>

              {/* Metrics */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-white/3 rounded-lg p-3 text-center">
                  <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', fontWeight: 700 }}>
                    Total Meters
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: '#fff', marginTop: 2 }}>{s.total_meters}</div>
                </div>
                <div className="bg-white/3 rounded-lg p-3 text-center">
                  <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', fontWeight: 700 }}>
                    Online
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: '#02C9A8', marginTop: 2 }}>{s.online_meters}</div>
                </div>
                <div className="bg-white/3 rounded-lg p-3 text-center">
                  <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', fontWeight: 700 }}>
                    Comms Rate
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: commColor, marginTop: 2 }}>
                    {s.comm_success_rate}%
                  </div>
                </div>
                <div className="bg-white/3 rounded-lg p-3 text-center">
                  <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', fontWeight: 700 }}>
                    Alarm/1000
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: alarmColor, marginTop: 2 }}>
                    {s.alarm_rate_per_1000}
                  </div>
                </div>
              </div>

              {/* Comms success bar */}
              <div className="mt-4">
                <div className="flex justify-between mb-1">
                  <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>Communication Success Rate</span>
                  <span style={{ fontSize: 10, color: commColor, fontWeight: 700 }}>{s.comm_success_rate}%</span>
                </div>
                <div className="w-full h-2 rounded-full bg-white/5">
                  <div className="h-2 rounded-full transition-all" style={{
                    width: `${s.comm_success_rate}%`,
                    background: commColor,
                  }} />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---- Tab: Equipment Performance ----------------------------------------------

function EquipmentPerformanceTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    systemManagementAPI.equipmentPerformance()
      .then(res => setData(res.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSkeleton rows={6} />
  if (!data) return <ErrorState />

  const totalMeters = data.equipment.reduce((s, e) => s + e.total, 0)
  const totalFailures = data.equipment.reduce((s, e) => s + e.failures, 0)
  const avgOnline = totalMeters > 0
    ? ((data.equipment.reduce((s, e) => s + e.online, 0) / totalMeters) * 100).toFixed(1)
    : 0

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Equipment Models" value={data.equipment.length} color="#56CCF2" icon={Cpu} />
        <StatCard label="Total Fleet" value={totalMeters} color="#02C9A8" icon={Gauge} />
        <StatCard label="Avg Online Rate" value={`${avgOnline}%`} color="#F59E0B" icon={Activity} />
        <StatCard
          label="Total Failures"
          value={totalFailures}
          sub={totalFailures > 0 ? 'Offline + Tamper' : 'All healthy'}
          color="#E94B4B" icon={AlertTriangle}
        />
      </div>

      {/* Table */}
      <div className="glass-card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ minWidth: 750 }}>
            <thead>
              <tr>
                <th>Manufacturer</th>
                <th>Model</th>
                <th style={{ textAlign: 'right' }}>Total</th>
                <th style={{ textAlign: 'right' }}>Online</th>
                <th style={{ textAlign: 'right' }}>Failures</th>
                <th style={{ textAlign: 'right' }}>Online Rate</th>
                <th style={{ width: 160 }}>Health Bar</th>
              </tr>
            </thead>
            <tbody>
              {data.equipment.map((e, i) => {
                const rateColor = e.online_rate >= 90 ? '#02C9A8' :
                  e.online_rate >= 80 ? '#F59E0B' : '#E94B4B'
                return (
                  <tr key={i}>
                    <td style={{ fontWeight: 700, color: '#fff' }}>{e.manufacturer}</td>
                    <td style={{ color: '#ABC7FF', fontFamily: "'Courier New', monospace", fontSize: 12 }}>
                      {e.model}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 600, color: '#fff' }}>{e.total}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600, color: '#02C9A8' }}>{e.online}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600, color: e.failures > 0 ? '#E94B4B' : 'rgba(255,255,255,0.4)' }}>
                      {e.failures}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 900, color: rateColor, fontSize: 14 }}>
                      {e.online_rate}%
                    </td>
                    <td>
                      <div className="w-full h-2 rounded-full bg-white/5">
                        <div className="h-2 rounded-full transition-all" style={{
                          width: `${e.online_rate}%`,
                          background: rateColor,
                        }} />
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---- Tab: Asset Search -------------------------------------------------------

function AssetSearchTab() {
  const [query, setQuery] = useState('')
  const [assetType, setAssetType] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)

  const doSearch = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (query.trim()) params.q = query.trim()
      if (assetType) params.asset_type = assetType
      if (statusFilter) params.status = statusFilter
      const res = await systemManagementAPI.assetSearch(params)
      setResults(res.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [query, assetType, statusFilter])

  // Fetch all assets on mount
  useEffect(() => { doSearch() }, [])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') doSearch()
  }

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className="glass-card" style={{ padding: 14 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          {/* Search input */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 250,
            background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)',
            borderRadius: 8, padding: '8px 12px',
          }}>
            <Search size={14} style={{ color: 'rgba(255,255,255,0.3)', flexShrink: 0 }} />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search by serial, manufacturer, model..."
              style={{
                background: 'none', border: 'none', outline: 'none',
                color: '#fff', fontSize: 13, flex: 1, minWidth: 0,
              }}
            />
          </div>

          {/* Asset type filter */}
          <select
            value={assetType}
            onChange={e => setAssetType(e.target.value)}
            style={selectStyle}
          >
            <option value="" style={{ background: '#0A1535' }}>All Asset Types</option>
            <option value="meter" style={{ background: '#0A1535' }}>Meters</option>
            <option value="dcu" style={{ background: '#0A1535' }}>DCUs</option>
            <option value="transformer" style={{ background: '#0A1535' }}>Transformers</option>
            <option value="sensor" style={{ background: '#0A1535' }}>Sensors</option>
          </select>

          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            style={selectStyle}
          >
            <option value="" style={{ background: '#0A1535' }}>All Statuses</option>
            <option value="online" style={{ background: '#0A1535' }}>Online</option>
            <option value="offline" style={{ background: '#0A1535' }}>Offline</option>
            <option value="tamper" style={{ background: '#0A1535' }}>Tamper</option>
            <option value="normal" style={{ background: '#0A1535' }}>Normal</option>
            <option value="warning" style={{ background: '#0A1535' }}>Warning</option>
            <option value="critical" style={{ background: '#0A1535' }}>Critical</option>
          </select>

          <button onClick={doSearch} className="btn-primary" style={{ gap: 7, padding: '9px 18px', fontSize: 13 }}>
            <Search size={14} /> Search
          </button>

          {results && (
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', whiteSpace: 'nowrap' }}>
              {results.total} result{results.total !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Results table */}
      <div className="glass-card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ minWidth: 900 }}>
            <thead>
              <tr>
                <th style={{ width: 100 }}>Asset Type</th>
                <th>Serial / Name</th>
                <th>Manufacturer</th>
                <th>Model</th>
                <th style={{ width: 100 }}>Status</th>
                <th>Firmware</th>
                <th>Comm Tech</th>
                <th>Location</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 32, color: 'rgba(255,255,255,0.3)' }}>
                    <RefreshCw size={14} className="inline animate-spin mr-2" />
                    Searching...
                  </td>
                </tr>
              ) : !results || results.results.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 32, color: 'rgba(255,255,255,0.3)' }}>
                    No assets found matching the criteria
                  </td>
                </tr>
              ) : results.results.map((r, i) => (
                <tr key={i}>
                  <td>
                    <span style={{
                      fontSize: 11, fontWeight: 700, padding: '2px 10px', borderRadius: 4,
                      background: r.asset_type === 'Meter' ? 'rgba(86,204,242,0.12)' :
                        r.asset_type === 'DCU' ? 'rgba(2,201,168,0.12)' :
                        r.asset_type === 'Transformer' ? 'rgba(245,158,11,0.12)' :
                        'rgba(171,199,255,0.12)',
                      color: r.asset_type === 'Meter' ? '#56CCF2' :
                        r.asset_type === 'DCU' ? '#02C9A8' :
                        r.asset_type === 'Transformer' ? '#F59E0B' :
                        '#ABC7FF',
                    }}>
                      {r.asset_type}
                    </span>
                  </td>
                  <td style={{ fontFamily: "'Courier New', monospace", fontSize: 12, color: '#ABC7FF', fontWeight: 600 }}>
                    {r.serial}
                  </td>
                  <td style={{ fontWeight: 600, color: '#fff' }}>{r.manufacturer}</td>
                  <td style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{r.model}</td>
                  <td>{r.status && <StatusBadge status={r.status} />}</td>
                  <td style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)' }}>{r.firmware || '--'}</td>
                  <td style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)' }}>{r.comm_tech || '--'}</td>
                  <td style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', fontFamily: "'Courier New', monospace" }}>
                    {r.location || '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---- Shared components -------------------------------------------------------

function LoadingSkeleton({ rows = 4 }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton h-24 rounded-card" />
        ))}
      </div>
      <div className="glass-card" style={{ overflow: 'hidden' }}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="skeleton h-12 mx-4 my-2 rounded" />
        ))}
      </div>
    </div>
  )
}

function ErrorState({ msg }) {
  return (
    <div className="glass-card p-12 flex items-center justify-center">
      <div className="text-center text-white/30">
        <AlertTriangle size={40} className="mx-auto mb-3 opacity-30" />
        <div className="font-bold">{msg || 'Failed to load data'}</div>
        <div className="text-sm mt-1">Check backend connectivity and try again</div>
      </div>
    </div>
  )
}

// ---- Main Page ---------------------------------------------------------------

export default function SystemManagement() {
  const [activeTab, setActiveTab] = useState('meters')

  const TabContent = {
    meters: MeterRegistryTab,
    devices: DeviceRegistryTab,
    suppliers: SupplierPerformanceTab,
    equipment: EquipmentPerformanceTab,
    search: AssetSearchTab,
  }

  const ActiveComponent = TabContent[activeTab]

  return (
    <div className="animate-slide-up" style={{ padding: 24, minHeight: '100vh', background: '#0A0F1E' }}>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 900, color: '#fff', margin: 0 }}>System Management</h1>
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13, margin: '4px 0 0' }}>
            SMOC-12 -- Asset registry, supplier & equipment performance, asset search
          </p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="glass-card" style={{ padding: '4px', marginBottom: 16, display: 'flex', gap: 2 }}>
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              padding: '10px 12px',
              borderRadius: 6,
              fontSize: 13,
              fontWeight: activeTab === key ? 700 : 500,
              cursor: 'pointer',
              border: 'none',
              transition: 'all 0.2s ease',
              background: activeTab === key
                ? 'linear-gradient(45deg, #11ABBE, #3C63FF)'
                : 'transparent',
              color: activeTab === key ? '#fff' : 'rgba(255,255,255,0.5)',
            }}
          >
            <Icon size={14} />
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      <ActiveComponent />

      {/* Footer note */}
      <div style={{
        marginTop: 20, padding: '10px 16px', borderRadius: 8,
        background: 'rgba(10,54,144,0.1)', border: '1px solid rgba(171,199,255,0.08)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <div style={{
          width: 6, height: 6, borderRadius: '50%', background: '#02C9A8',
          boxShadow: '0 0 6px #02C9A8', flexShrink: 0,
        }} />
        <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)' }}>
          Asset registry synchronized from HES and MDMS. Supplier performance metrics calculated in real-time from meter fleet data.
        </span>
      </div>
    </div>
  )
}
