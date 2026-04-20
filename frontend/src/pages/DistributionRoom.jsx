// Spec 018 W3.T11 — Distribution-room sensors dashboard.
// Route: /distribution.
// Uses existing /api/v1/sensors/* endpoints (transformer_sensor_reading
// populated by hesv2.sensor.readings Kafka consumer).
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Thermometer, Droplets, Flame, Waves, DoorOpen, RefreshCw, AlertTriangle,
  CheckCircle, Gauge,
} from 'lucide-react'
import { sensorsAPI, metersAPI } from '@/services/api'

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

const ICON_BY_TYPE = {
  oil_temp: Thermometer,
  ambient_temp: Thermometer,
  humidity: Droplets,
  smoke: Flame,
  water: Waves,
  water_immersion: Waves,
  door: DoorOpen,
  door_access: DoorOpen,
  load_current: Gauge,
}

const COLOR_BY_TYPE = {
  oil_temp: '#F59E0B',
  ambient_temp: '#F97316',
  humidity: '#56CCF2',
  smoke: '#E94B4B',
  water: '#ABC7FF',
  water_immersion: '#ABC7FF',
  door: '#02C9A8',
  door_access: '#02C9A8',
  load_current: '#F59E0B',
}

export default function DistributionRoom() {
  const [rooms, setRooms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      // Per-transformer sensor lists form the "room" grouping.
      const [{ data: transformers }, { data: sensors }] = await Promise.all([
        metersAPI.transformers().catch(() => ({ data: [] })),
        sensorsAPI.list({}),
      ])

      const txMap = new Map(
        (transformers || []).map((t) => [t.id, t]),
      )
      const byTx = new Map()
      for (const s of sensors || []) {
        const key = s.transformer_id
        if (!byTx.has(key)) byTx.set(key, [])
        byTx.get(key).push(s)
      }
      const out = []
      for (const [txId, sensorList] of byTx.entries()) {
        const tx = txMap.get(txId) || { id: txId, name: `DTR-${txId}` }
        out.push({ transformer: tx, sensors: sensorList })
      }
      out.sort((a, b) => (a.transformer.name || '').localeCompare(b.transformer.name || ''))
      setRooms(out)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load distribution-room data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 60_000)
    return () => clearInterval(id)
  }, [load])

  const totals = useMemo(() => {
    const allSensors = rooms.flatMap((r) => r.sensors)
    const critical = allSensors.filter((s) => (s.status || '').toLowerCase() === 'critical').length
    const warning = allSensors.filter((s) => (s.status || '').toLowerCase() === 'warning').length
    const online = allSensors.filter((s) => (s.status || '').toLowerCase() === 'ok' || (s.status || '').toLowerCase() === 'normal').length
    return { rooms: rooms.length, critical, warning, online }
  }, [rooms])

  return (
    <div className="space-y-5 animate-slide-up" data-testid="distribution-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>Distribution Rooms</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-25 · Temp · Humidity · Smoke · Water · Door Access
          </div>
        </div>
        <button onClick={load} disabled={loading}
          className="btn-secondary flex items-center gap-2"
          style={{ padding: '8px 16px', fontSize: 13 }}>
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="glass-card p-3 flex items-center gap-3"
          style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}>
          <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
          <span className="text-white/80" style={{ fontSize: 13 }}>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPI icon={Gauge} label="Rooms" value={totals.rooms} color="#56CCF2" />
        <KPI icon={CheckCircle} label="Sensors Normal" value={totals.online} color="#02C9A8" />
        <KPI icon={AlertTriangle} label="Warnings" value={totals.warning} color="#F59E0B" />
        <KPI icon={Flame} label="Critical" value={totals.critical} color="#E94B4B" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="distribution-rooms">
        {rooms.map((r) => <RoomCard key={r.transformer.id} room={r} />)}
        {rooms.length === 0 && !loading && (
          <div className="glass-card p-6 text-center text-white/40 md:col-span-2 xl:col-span-3" style={{ fontSize: 13 }}>
            No distribution-room sensors registered.
          </div>
        )}
      </div>
    </div>
  )
}

function KPI({ icon: Icon, label, value, color = '#02C9A8' }) {
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ background: `${color}20` }}>
          <Icon size={18} style={{ color }} />
        </div>
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 26 }}>{value}</div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 13 }}>{label}</div>
      </div>
    </div>
  )
}

function RoomCard({ room }) {
  const status = (room.sensors || []).reduce((worst, s) => {
    const v = (s.status || '').toLowerCase()
    if (v === 'critical') return 'critical'
    if (v === 'warning' && worst !== 'critical') return 'warning'
    return worst
  }, 'ok')
  const borderColor =
    status === 'critical' ? 'rgba(233,75,75,0.4)'
    : status === 'warning' ? 'rgba(245,158,11,0.4)'
    : 'rgba(2,201,168,0.2)'
  return (
    <div className="glass-card p-4" data-testid="distribution-room" style={{ borderColor }}>
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-white font-bold" style={{ fontSize: 14 }}>
            {room.transformer.name || `DTR ${room.transformer.id}`}
          </div>
          <div className="text-white/40" style={{ fontSize: 11 }}>
            Transformer ID {room.transformer.id}
          </div>
        </div>
        <span className={
          status === 'critical' ? 'badge-critical'
          : status === 'warning' ? 'badge-medium'
          : 'badge-ok'
        }>{status}</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {(room.sensors || []).map((s) => <SensorCell key={s.id} sensor={s} />)}
      </div>
    </div>
  )
}

function SensorCell({ sensor }) {
  const Icon = ICON_BY_TYPE[sensor.sensor_type] || Gauge
  const color = COLOR_BY_TYPE[sensor.sensor_type] || '#ABC7FF'
  const status = (sensor.status || 'ok').toLowerCase()
  return (
    <div className="rounded-lg p-2 flex items-center gap-2"
      style={{
        background:
          status === 'critical' ? 'rgba(233,75,75,0.08)'
          : status === 'warning' ? 'rgba(245,158,11,0.08)'
          : 'rgba(255,255,255,0.03)',
      }}>
      <div className="w-8 h-8 rounded-lg flex items-center justify-center"
        style={{ background: `${color}20` }}>
        <Icon size={14} style={{ color }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-white/40" style={{ fontSize: 10 }}>
          {(sensor.sensor_type || '').replace(/_/g, ' ')}
        </div>
        <div className="text-white font-bold" style={{ fontSize: 13, fontFamily: 'monospace' }}>
          {fmt(sensor.last_value, 1)}{sensor.unit ? ` ${sensor.unit}` : ''}
        </div>
      </div>
    </div>
  )
}
