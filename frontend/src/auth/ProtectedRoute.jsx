// Spec 018 W4.T12 — ProtectedRoute wraps authenticated routes with an
// optional `requiredPermission` prop. If the user lacks the permission,
// we render a 403-style Forbidden view instead of the child route.

import { Navigate, useLocation } from 'react-router-dom'
import useAuthStore from '@/stores/authStore'
import { hasPermission, canAccessRoute } from '@/auth/permissions'

export function Forbidden({ reason = 'Your role does not have access to this area.' }) {
  return (
    <div className="flex flex-col items-center justify-center h-full py-20" data-testid="forbidden">
      <div className="glass-card p-8 max-w-md text-center">
        <div className="text-6xl mb-4">403</div>
        <div className="text-white font-black text-lg">Access denied</div>
        <div className="text-white/60 mt-2 text-sm">{reason}</div>
      </div>
    </div>
  )
}

export default function ProtectedRoute({ children, requiredPermission }) {
  const { token, permissions } = useAuthStore()
  const { pathname } = useLocation()

  if (!token) {
    return <Navigate to="/login" replace />
  }

  // Explicit permission beats route-table permission.
  if (requiredPermission) {
    if (!hasPermission(permissions, requiredPermission)) {
      return <Forbidden reason={`Missing permission: ${requiredPermission}`} />
    }
    return children
  }

  // Fall back to the route-table lookup so unguarded routes still obey RBAC.
  if (!canAccessRoute(permissions, pathname)) {
    return <Forbidden />
  }
  return children
}
