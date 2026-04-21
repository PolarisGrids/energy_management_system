// W5 — Reusable time-range picker for DER pages.
// Windows: 1h | 24h | 7d | 30d. Custom range can be added later.
import { Clock } from 'lucide-react'

const DEFAULT_WINDOWS = [
  { id: '1h', label: '1 h' },
  { id: '24h', label: '24 h' },
  { id: '7d', label: '7 d' },
  { id: '30d', label: '30 d' },
]

export default function DERTimeRangePicker({
  value,
  onChange,
  windows = DEFAULT_WINDOWS,
  accent = '#02C9A8',
  size = 'md',
}) {
  const px = size === 'sm' ? 'px-2 py-1' : 'px-3 py-1.5'
  return (
    <div
      className="glass-card p-1 inline-flex gap-1 items-center"
      data-testid="der-time-range"
    >
      <Clock size={11} className="ml-1 text-white/30" />
      {windows.map((w) => {
        const active = value === w.id
        return (
          <button
            key={w.id}
            onClick={() => onChange(w.id)}
            className={`${px} rounded-md font-semibold whitespace-nowrap`}
            style={{
              fontSize: 12,
              background: active ? `${accent}26` : 'transparent',
              color: active ? accent : 'rgba(255,255,255,0.5)',
            }}
            data-testid={`der-time-range-${w.id}`}
          >
            {w.label}
          </button>
        )
      })}
    </div>
  )
}
