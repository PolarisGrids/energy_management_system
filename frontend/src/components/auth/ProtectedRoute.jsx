import { useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import useAuthStore from '@/stores/authStore'
import { can, canAll } from '@/lib/can'

/**
 * Gate a route by one or more required capabilities.
 *
 * Usage:
 *   <ProtectedRoute required="users.manage">
 *     <AdminUsers />
 *   </ProtectedRoute>
 *
 * Multiple caps are ALL-required:
 *   <ProtectedRoute required={["der.control", "simulation.run"]}>
 *
 * On denial:
 *   - fires a one-shot console/toast notification
 *   - redirects to ``/`` (dashboard) — a dedicated 403 page is deferred.
 */
export default function ProtectedRoute({ required, children }) {
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)

  const caps = Array.isArray(required) ? required : [required]
  const allowed =
    !!token && !!user && (caps.length === 0 || canAll(user, ...caps))

  useEffect(() => {
    if (token && user && !allowed) {
      const missing = caps.filter((c) => !can(user, c))
      // Minimal toast: delegate to window.toast if present (see Toast.jsx).
      const msg = `Access denied — requires ${missing.join(', ')}`
      if (typeof window !== 'undefined') {
        if (typeof window.polarisToast === 'function') {
          window.polarisToast({ variant: 'error', message: msg })
        } else {
          console.warn(msg)
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed, token])

  if (!token) return <Navigate to="/login" replace />
  if (!allowed) return <Navigate to="/" replace />
  return children
}
