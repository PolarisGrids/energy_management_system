import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { CheckCircle, AlertTriangle, Info, XCircle, X } from 'lucide-react'

/**
 * Stateless toast component library.
 *
 * Usage:
 *   // 1. Mount provider once (e.g. in App.jsx / main.jsx):
 *   <ToastProvider>...app...</ToastProvider>
 *
 *   // 2. Call via hook in any component:
 *   const toast = useToast()
 *   toast.success('Saved')
 *   toast.error('Failed', 'Upstream timed out')
 *
 *   // 3. Or fire-and-forget from a non-hook callsite:
 *   window.polarisToast?.show({ kind: 'info', title: 'Hi' })
 *
 * Styling follows the polaris_ems `glass-card` conventions; no extra deps.
 */

const ToastContext = createContext(null)

const KIND_STYLES = {
  success: {
    border: 'rgba(2,201,168,0.35)',
    glow: 'rgba(2,201,168,0.08)',
    accent: '#02C9A8',
    Icon: CheckCircle,
  },
  error: {
    border: 'rgba(233,75,75,0.35)',
    glow: 'rgba(233,75,75,0.08)',
    accent: '#E94B4B',
    Icon: XCircle,
  },
  warning: {
    border: 'rgba(245,158,11,0.35)',
    glow: 'rgba(245,158,11,0.08)',
    accent: '#F59E0B',
    Icon: AlertTriangle,
  },
  info: {
    border: 'rgba(86,204,242,0.35)',
    glow: 'rgba(86,204,242,0.08)',
    accent: '#56CCF2',
    Icon: Info,
  },
}

const DEFAULT_DURATION_MS = 4000

let nextId = 1

export function Toast({ toast, onDismiss }) {
  const style = KIND_STYLES[toast.kind] ?? KIND_STYLES.info
  const { Icon } = style

  return (
    <div
      role={toast.kind === 'error' ? 'alert' : 'status'}
      className="glass-card p-4 flex items-start gap-3 shadow-lg animate-slide-up"
      style={{
        borderColor: style.border,
        background: style.glow,
        minWidth: 280,
        maxWidth: 380,
      }}
      data-toast-kind={toast.kind}
    >
      <Icon size={18} style={{ color: style.accent, flexShrink: 0, marginTop: 2 }} />
      <div className="flex-1 min-w-0">
        {toast.title && (
          <div
            className="font-bold text-white"
            style={{ fontSize: 13, lineHeight: 1.3 }}
          >
            {toast.title}
          </div>
        )}
        {toast.message && (
          <div
            className="text-white/70 mt-0.5"
            style={{ fontSize: 12, lineHeight: 1.4 }}
          >
            {toast.message}
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className="text-white/40 hover:text-white/80 transition-colors shrink-0"
        aria-label="Dismiss notification"
      >
        <X size={14} />
      </button>
    </div>
  )
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timersRef = useRef(new Map())

  const dismiss = useCallback((id) => {
    const timer = timersRef.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timersRef.current.delete(id)
    }
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const show = useCallback(
    ({ kind = 'info', title, message, duration = DEFAULT_DURATION_MS } = {}) => {
      const id = nextId++
      setToasts((list) => [...list, { id, kind, title, message }])
      if (duration > 0) {
        const timer = setTimeout(() => dismiss(id), duration)
        timersRef.current.set(id, timer)
      }
      return id
    },
    [dismiss],
  )

  const api = useMemo(
    () => ({
      show,
      dismiss,
      success: (title, message, opts) =>
        show({ kind: 'success', title, message, ...opts }),
      error: (title, message, opts) =>
        show({ kind: 'error', title, message, ...opts }),
      warning: (title, message, opts) =>
        show({ kind: 'warning', title, message, ...opts }),
      info: (title, message, opts) =>
        show({ kind: 'info', title, message, ...opts }),
    }),
    [show, dismiss],
  )

  // Window bridge — lets non-hook callsites (axios interceptors,
  // ProtectedRoute guards, error boundaries) fire toasts without the
  // React tree.
  useEffect(() => {
    if (typeof window === 'undefined') return
    window.polarisToast = api
    return () => {
      if (window.polarisToast === api) delete window.polarisToast
    }
  }, [api])

  // Clear any pending timers on unmount.
  useEffect(() => {
    const timers = timersRef.current
    return () => {
      timers.forEach((t) => clearTimeout(t))
      timers.clear()
    }
  }, [])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="fixed z-[9999] flex flex-col gap-2 pointer-events-none"
        style={{ top: 16, right: 16 }}
      >
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto">
            <Toast toast={t} onDismiss={dismiss} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    // Fall back to the window bridge so `useToast()` never throws at
    // render time if the provider hasn't mounted yet (e.g. during tests).
    return (
      (typeof window !== 'undefined' && window.polarisToast) ||
      noopToastApi
    )
  }
  return ctx
}

const noopToastApi = {
  show: () => null,
  dismiss: () => null,
  success: () => null,
  error: () => null,
  warning: () => null,
  info: () => null,
}

export default Toast
