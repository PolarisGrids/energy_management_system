import { useCallback, useEffect, useState } from 'react'
import { metersAPI } from '@/services/api'

/**
 * Source the /dashboard KPIs from the local /meters/summary endpoint.
 *
 * Previously forwarded to /api/v1/hes/* + /api/v1/mdms/* SSOT proxies, but
 * upstream HES/MDMS reject SMOC's session JWT (different Cognito audience)
 * so every request 401'd. /meters/summary computes the identical KPI set
 * from SMOC's own tables (meters, feeders, transformers, alarms) which
 * are synced from MDMS — same real numbers the proxy would return.
 *
 * Returns `{ kpis, errors, loading, refetch, lastRefresh }`. `errors` is
 * kept for Dashboard banner back-compat.
 */
export function useSSOTDashboard(intervalMs = 30000) {
  const [kpis, setKpis] = useState({
    total_meters: null,
    online_meters: null,
    offline_meters: null,
    active_alarms: null,
    comm_success_rate: null,
    total_transformers: null,
    total_feeders: null,
    tamper_meters: null,
  })
  const [errors, setErrors] = useState({ hes: null, mdms: null })
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState(null)

  const fetch = useCallback(async () => {
    try {
      const { data } = await metersAPI.summary()
      setKpis({
        total_meters: data?.total_meters ?? null,
        online_meters: data?.online_meters ?? null,
        offline_meters: data?.offline_meters ?? null,
        active_alarms: data?.active_alarms ?? null,
        comm_success_rate: data?.comm_success_rate ?? null,
        total_transformers: data?.total_transformers ?? null,
        total_feeders: data?.total_feeders ?? null,
        tamper_meters: data?.tamper_meters ?? null,
      })
      setErrors({ hes: null, mdms: null })
    } catch (e) {
      const msg = e?.response?.data?.error?.message ?? e?.message ?? 'Dashboard KPIs unavailable'
      setErrors({ hes: msg, mdms: msg })
    } finally {
      setLastRefresh(new Date())
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetch()
    const id = setInterval(fetch, intervalMs)
    return () => clearInterval(id)
  }, [fetch, intervalMs])

  return { kpis, errors, loading, refetch: fetch, lastRefresh }
}
