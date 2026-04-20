import { useEffect, useCallback } from 'react'

/**
 * Connect to the SSE /api/v1/events/stream endpoint.
 * handlers: { alarm, network_health, simulation_update, heartbeat }
 */
export function useSSE(handlers = {}) {
  const token = localStorage.getItem('smoc_token')

  useEffect(() => {
    if (!token) return

    // EventSource doesn't support custom headers — pass token as query param
    const url = `/api/v1/events/stream?token=${token}`
    const es = new EventSource(url)

    Object.entries(handlers).forEach(([event, handler]) => {
      es.addEventListener(event, (e) => {
        try {
          const data = JSON.parse(e.data)
          handler(data)
        } catch { /* ignore parse errors */ }
      })
    })

    es.onerror = () => {
      // Auto-reconnect handled by browser EventSource spec
    }

    return () => es.close()
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps
}
