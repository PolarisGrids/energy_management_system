// W5 — Debounced search input for DER consumer/asset lists.
import { useEffect, useState } from 'react'
import { Search, X } from 'lucide-react'

export default function DERConsumerSearch({
  value,
  onChange,
  placeholder = 'Search by name, account, asset id…',
  debounceMs = 300,
}) {
  const [local, setLocal] = useState(value || '')

  // Sync inbound prop changes (eg. clear-all from parent).
  useEffect(() => {
    setLocal(value || '')
  }, [value])

  // Debounce outbound onChange.
  useEffect(() => {
    const id = setTimeout(() => {
      if (local !== (value || '')) onChange(local)
    }, debounceMs)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local])

  return (
    <div
      className="glass-card flex items-center gap-2"
      style={{ padding: '0 10px', minWidth: 260 }}
      data-testid="der-consumer-search"
    >
      <Search size={13} className="text-white/40 shrink-0" />
      <input
        type="text"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder={placeholder}
        className="bg-transparent border-0 text-white outline-none flex-1"
        style={{ fontSize: 13, padding: '8px 0' }}
      />
      {local && (
        <button
          onClick={() => setLocal('')}
          className="text-white/40 hover:text-white/70 shrink-0"
          aria-label="clear search"
        >
          <X size={13} />
        </button>
      )}
    </div>
  )
}
