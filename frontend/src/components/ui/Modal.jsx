import { useEffect, useRef } from 'react'

const SIZES = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-3xl' }

/**
 * Modal — simple overlay dialog with ESC-to-close and basic focus trap.
 */
export default function Modal({ open, onClose, title, size = 'md', children, footer }) {
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const prev = document.activeElement
    const handle = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', handle)
    ref.current?.focus()
    return () => {
      window.removeEventListener('keydown', handle)
      if (prev && typeof prev.focus === 'function') prev.focus()
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.() }}
      role="dialog"
      aria-modal="true"
    >
      <div
        ref={ref}
        tabIndex={-1}
        className={`glass-card rounded-xl p-5 w-full ${SIZES[size] || SIZES.md} outline-none`}
      >
        {title && <h2 className="text-white font-bold text-lg mb-3">{title}</h2>}
        <div>{children}</div>
        {footer && <div className="mt-4 pt-3 border-t border-white/10 flex gap-2 justify-end">{footer}</div>}
      </div>
    </div>
  )
}
