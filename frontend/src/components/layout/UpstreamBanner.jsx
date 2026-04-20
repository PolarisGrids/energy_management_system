import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, AlertOctagon, RefreshCw } from 'lucide-react'
import { healthAPI } from '@/services/api'

/**
 * Global upstream-health banner (spec 018 W1.T11).
 *
 * Polls `GET /api/v1/health` every 30 s and renders a persistent red bar
 * across the top of the app whenever `overall !== 'ok'`. The bar lists the
 * failing components so the operator can triage at a glance.
 *
 * Mount once inside `AppLayout`.
 */
const POLL_INTERVAL_MS = 30000

const STYLES = {
  fail: {
    bg: 'rgba(233,75,75,0.22)',
    border: '1px solid rgba(233,75,75,0.6)',
    accent: '#E94B4B',
    Icon: AlertOctagon,
    label: 'Upstream down',
  },
  degraded: {
    bg: 'rgba(245,158,11,0.18)',
    border: '1px solid rgba(245,158,11,0.5)',
    accent: '#F59E0B',
    Icon: AlertTriangle,
    label: 'Degraded',
  },
}

export default function UpstreamBanner() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  const fetchHealth = useCallback(async () => {
    setRefreshing(true)
    try {
      const { data } = await healthAPI.get()
      setHealth(data)
      setError(null)
    } catch (err) {
      setError(err?.message || 'Health probe failed')
      setHealth(null)
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    fetchHealth()
    const id = setInterval(fetchHealth, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [fetchHealth])

  const failing = useMemo(() => {
    if (!health?.components) return []
    return Object.entries(health.components)
      .filter(([, v]) => v?.status && v.status !== 'ok')
      .map(([k, v]) => ({ name: k, status: v.status, detail: v.detail }))
  }, [health])

  const overall = error ? 'fail' : health?.overall ?? 'ok'

  if (overall === 'ok') return null

  const style = STYLES[overall] || STYLES.degraded
  const { Icon } = style

  return (
    <div
      role="status"
      className="w-full flex items-center gap-3 px-5 py-2"
      style={{
        background: style.bg,
        borderBottom: style.border,
        color: '#fff',
        fontSize: 13,
      }}
      data-testid="upstream-banner"
      data-status={overall}
    >
      <Icon size={16} style={{ color: style.accent, flexShrink: 0 }} />
      <span className="font-bold" style={{ color: style.accent }}>
        {style.label}
      </span>
      <span className="text-white/80" style={{ flex: 1, minWidth: 0 }}>
        {error
          ? `Health probe unreachable (${error}). EMS may be restarting.`
          : failing.length === 0
          ? 'Health reported not-ok but no failing component listed.'
          : `${failing.map((c) => `${c.name}: ${c.status}`).join(' · ')}`}
        {health?.ssot_mode && <span className="text-white/50 ml-2">({health.ssot_mode} mode)</span>}
      </span>
      <button
        type="button"
        onClick={fetchHealth}
        className="flex items-center gap-1 text-white/80 hover:text-white"
        style={{ fontSize: 12 }}
        aria-label="Refresh health"
      >
        <RefreshCw size={12} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
        Refresh
      </button>
    </div>
  )
}
