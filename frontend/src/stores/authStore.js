import { create } from 'zustand'
import { authAPI } from '@/services/api'
import { permissionsForRole } from '@/auth/permissions'

// Spec 018 W4.T12 — persist the user's permission list so the menu / routes
// can gate themselves without a round-trip. Login seeds it; /auth/me refreshes
// it on reload.

const stored = () => {
  try {
    const u = localStorage.getItem('smoc_user')
    return u ? JSON.parse(u) : null
  } catch { return null }
}

const storedPermissions = () => {
  try {
    const raw = localStorage.getItem('smoc_permissions')
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

const useAuthStore = create((set) => ({
  user: stored(),
  token: localStorage.getItem('smoc_token'),
  // Effective permission list — comes from the backend (/auth/login or /auth/me)
  // and falls back to the role-matrix mirror if the backend returned nothing.
  permissions: storedPermissions(),
  loading: false,
  error: null,

  login: async (username, password) => {
    set({ loading: true, error: null })
    try {
      const { data } = await authAPI.login(username, password)
      const permissions = (Array.isArray(data.permissions) && data.permissions.length)
        ? data.permissions
        : permissionsForRole(data.role)
      localStorage.setItem('smoc_token', data.access_token)
      localStorage.setItem('smoc_user', JSON.stringify({
        id: data.user_id,
        username: data.username,
        full_name: data.full_name,
        role: data.role,
      }))
      localStorage.setItem('smoc_permissions', JSON.stringify(permissions))
      set({
        token: data.access_token,
        user: {
          id: data.user_id,
          username: data.username,
          full_name: data.full_name,
          role: data.role,
        },
        permissions,
        loading: false,
      })
      return true
    } catch (err) {
      set({ error: err.response?.data?.detail || 'Login failed', loading: false })
      return false
    }
  },

  refreshMe: async () => {
    try {
      const { data } = await authAPI.me()
      const permissions = (Array.isArray(data.permissions) && data.permissions.length)
        ? data.permissions
        : permissionsForRole(data.role)
      localStorage.setItem('smoc_user', JSON.stringify({
        id: data.id,
        username: data.username,
        full_name: data.full_name,
        role: data.role,
      }))
      localStorage.setItem('smoc_permissions', JSON.stringify(permissions))
      set({
        user: {
          id: data.id,
          username: data.username,
          full_name: data.full_name,
          role: data.role,
        },
        permissions,
      })
    } catch {
      // 401 is handled globally by the axios interceptor (redirects to /login).
      // Anything else we swallow — the cached permissions keep the UI usable.
    }
  },

  logout: () => {
    localStorage.removeItem('smoc_token')
    localStorage.removeItem('smoc_user')
    localStorage.removeItem('smoc_permissions')
    set({ user: null, token: null, permissions: [] })
  },
}))

export default useAuthStore
