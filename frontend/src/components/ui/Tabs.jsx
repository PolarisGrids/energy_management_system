/**
 * Tabs — controlled tab bar.
 * items: [{ id, label, disabled? }]
 */
export default function Tabs({ items = [], activeId, onChange, className = '' }) {
  return (
    <div className={`flex gap-2 border-b border-white/10 ${className}`}>
      {items.map((t) => {
        const active = t.id === activeId
        return (
          <button
            key={t.id}
            type="button"
            disabled={t.disabled}
            onClick={() => !t.disabled && onChange?.(t.id)}
            className={`px-3 py-2 text-sm font-semibold -mb-px border-b-2 transition-colors ${active ? 'border-cyan-400 text-white' : 'border-transparent text-white/60 hover:text-white'} ${t.disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}
