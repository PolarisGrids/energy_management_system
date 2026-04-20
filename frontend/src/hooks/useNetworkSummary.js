import { useState, useEffect, useCallback } from 'react'
import { metersAPI } from '@/services/api'

/**
 * Periodically polls /meters/summary. Returns
 * `{ summary, loading, error, refetch }`.
 *
 * `loading` is only true on the first fetch; subsequent background
 * refreshes do not flip the spinner. Errors are captured rather than
 * silently swallowed so consumer components can distinguish "loading",
 * "live", "empty", and "upstream failed".
 */
export function useNetworkSummary(intervalMs = 30000) {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetch = useCallback(async () => {
    try {
      const { data } = await metersAPI.summary()
      setSummary(data)
      setError(null)
    } catch (err) {
      setError(err?.response?.data?.detail ?? err?.message ?? 'Unreachable')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetch()
    const id = setInterval(fetch, intervalMs)
    return () => clearInterval(id)
  }, [fetch, intervalMs])

  return { summary, loading, error, refetch: fetch }
}
