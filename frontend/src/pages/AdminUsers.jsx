import { useEffect, useState } from 'react'
import axios from 'axios'
import useAuthStore from '@/stores/authStore'

/**
 * Admin Users stub page (spec 015-rbac-ui-lib US2).
 * Full CRUD UI is tracked under TODO(015-mvp-phase2). This stub lists
 * users and shows that the route is reachable only for users.manage.
 */
export default function AdminUsers() {
  const token = useAuthStore((s) => s.token)
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const base = import.meta.env.VITE_API_BASE || '/api/v1'
    axios
      .get(`${base}/admin/users/`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((r) => setUsers(r.data || []))
      .catch((e) => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false))
  }, [token])

  return (
    <div className="p-6">
      <h1 className="text-white text-2xl font-black mb-4">User Management</h1>
      <p className="text-white/60 text-sm mb-4">
        Admin-only surface. Create/edit UI scheduled for Phase 2 follow-up;
        API endpoints are live at <code>/api/v1/admin/users/*</code>.
      </p>

      {loading && <div className="text-white/60">Loading…</div>}
      {error && <div className="text-red-400">{String(error)}</div>}

      {!loading && !error && (
        <table className="data-table w-full">
          <thead>
            <tr>
              <th>ID</th>
              <th>Username</th>
              <th>Email</th>
              <th>Full Name</th>
              <th>Role</th>
              <th>Active</th>
              <th>Last Login</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.username}</td>
                <td>{u.email}</td>
                <td>{u.full_name}</td>
                <td>{u.role}</td>
                <td>{u.is_active ? 'yes' : 'no'}</td>
                <td>{u.last_login || '—'}</td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={7} className="text-white/40">No users</td></tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}
