// Spec 018 W4.T11 — saved dashboard layouts UI.
// A small modal that lets the user list / create / rename / delete / set
// default on their saved layouts. The Dashboard page mounts this modal
// behind a "Manage layouts" button.

import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { X, Plus, Trash2, Star, Edit2, Copy, Check } from 'lucide-react'
import { dashboardsAPI } from '@/services/api'

export default function LayoutManager({ open, onClose, onLayoutChanged }) {
  const [layouts, setLayouts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editName, setEditName] = useState('')

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const { data } = await dashboardsAPI.list()
      setLayouts(data || [])
    } catch (err) {
      setError(err?.response?.data?.detail ?? err?.message ?? 'Failed to load layouts')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) load()
  }, [open])

  if (!open) return null

  async function create() {
    if (!newName.trim()) return
    try {
      await dashboardsAPI.create({ name: newName.trim(), widgets: [], is_default: layouts.length === 0 })
      setNewName('')
      setCreating(false)
      await load()
      onLayoutChanged?.()
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Create failed')
    }
  }

  async function rename(id) {
    if (!editName.trim()) return
    try {
      await dashboardsAPI.update(id, { name: editName.trim() })
      setEditingId(null)
      await load()
      onLayoutChanged?.()
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Rename failed')
    }
  }

  async function remove(id) {
    if (!confirm('Delete this layout?')) return
    try {
      await dashboardsAPI.remove(id)
      await load()
      onLayoutChanged?.()
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Delete failed')
    }
  }

  async function makeDefault(id) {
    try {
      await dashboardsAPI.update(id, { is_default: true })
      await load()
      onLayoutChanged?.()
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Update failed')
    }
  }

  async function duplicate(id) {
    try {
      await dashboardsAPI.duplicate(id)
      await load()
      onLayoutChanged?.()
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Duplicate failed')
    }
  }

  // Render via portal so the modal escapes any ancestor that establishes a
  // containing block (e.g. the dashboard page's animate-slide-up transform),
  // which would otherwise clip `position: fixed`.
  return createPortal(
    <div
      className="fixed inset-0 z-[9999] bg-black/60 flex items-center justify-center"
      data-testid="layout-manager-modal"
      onClick={onClose}
    >
      <div
        className="glass-card p-6 w-[520px] max-w-[90vw]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-white font-black text-lg">Dashboard layouts</div>
            <div className="text-white/50 text-xs">Saved layouts you own or that were shared with your role.</div>
          </div>
          <button onClick={onClose} className="text-white/40 hover:text-white" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {error && (
          <div className="mb-3 text-status-critical text-sm" role="alert">{error}</div>
        )}

        <div className="space-y-2">
          {loading && <div className="text-white/40 text-sm">Loading…</div>}
          {!loading && layouts.length === 0 && (
            <div className="text-white/50 text-sm py-4 text-center">No saved layouts yet.</div>
          )}
          {layouts.map((l) => (
            <div
              key={l.id}
              className="flex items-center gap-2 p-2 rounded border border-white/5 bg-white/5"
              data-testid={`layout-row-${l.id}`}
            >
              {editingId === l.id ? (
                <>
                  <input
                    className="flex-1 bg-transparent text-white text-sm border-b border-white/20 focus:outline-none"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && rename(l.id)}
                  />
                  <button onClick={() => rename(l.id)} className="text-energy-green" title="Save">
                    <Check size={14} />
                  </button>
                  <button onClick={() => setEditingId(null)} className="text-white/40" title="Cancel">
                    <X size={14} />
                  </button>
                </>
              ) : (
                <>
                  <div className="flex-1 truncate">
                    <span className="text-white text-sm">{l.name}</span>
                    {l.is_default && (
                      <span className="ml-2 text-accent-blue" style={{ fontSize: 10 }}>DEFAULT</span>
                    )}
                    {l.shared && (
                      <span className="ml-2 text-white/40" style={{ fontSize: 10 }}>SHARED</span>
                    )}
                  </div>
                  {!l.is_default && !l.shared && (
                    <button onClick={() => makeDefault(l.id)} className="text-white/50 hover:text-accent-blue" title="Set default">
                      <Star size={14} />
                    </button>
                  )}
                  {!l.shared && (
                    <button
                      onClick={() => {
                        setEditingId(l.id)
                        setEditName(l.name)
                      }}
                      className="text-white/50 hover:text-white"
                      title="Rename"
                    >
                      <Edit2 size={14} />
                    </button>
                  )}
                  <button onClick={() => duplicate(l.id)} className="text-white/50 hover:text-white" title="Duplicate">
                    <Copy size={14} />
                  </button>
                  {!l.shared && (
                    <button onClick={() => remove(l.id)} className="text-white/50 hover:text-status-critical" title="Delete">
                      <Trash2 size={14} />
                    </button>
                  )}
                </>
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 border-t border-white/10 pt-3">
          {creating ? (
            <div className="flex gap-2">
              <input
                className="flex-1 bg-white/5 border border-white/10 rounded px-3 py-1.5 text-white text-sm"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Layout name"
                onKeyDown={(e) => e.key === 'Enter' && create()}
                autoFocus
              />
              <button onClick={create} className="btn-primary" style={{ padding: '6px 12px', fontSize: 12 }}>
                Create
              </button>
              <button
                onClick={() => { setCreating(false); setNewName('') }}
                className="btn-secondary"
                style={{ padding: '6px 12px', fontSize: 12 }}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setCreating(true)}
              className="btn-secondary flex items-center gap-2"
              style={{ padding: '6px 12px', fontSize: 12 }}
              data-testid="new-layout-btn"
            >
              <Plus size={12} /> New layout
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}
