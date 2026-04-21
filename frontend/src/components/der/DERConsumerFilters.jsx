// W5 — Filter chips for DER consumer/asset lists.
// Configurable so PV/BESS/EV pages can supply their own option groups.
import { Filter, X } from 'lucide-react'

/**
 * groups: [{ key, label, options: [{ value, label, count? }] }]
 * value:  { [groupKey]: optionValue }
 */
export default function DERConsumerFilters({ groups = [], value = {}, onChange }) {
  const setOne = (key, val) => onChange({ ...value, [key]: val || undefined })
  const clearAll = () =>
    onChange(Object.fromEntries(groups.map((g) => [g.key, undefined])))
  const activeCount = Object.values(value).filter(Boolean).length

  return (
    <div className="flex items-center gap-2 flex-wrap" data-testid="der-consumer-filters">
      <Filter size={13} className="text-white/30" />
      {groups.map((g) => (
        <select
          key={g.key}
          value={value[g.key] ?? ''}
          onChange={(e) => setOne(g.key, e.target.value)}
          className="glass-card text-white"
          style={{
            fontSize: 12,
            padding: '6px 10px',
            borderRadius: 8,
            background: value[g.key]
              ? 'rgba(2,201,168,0.12)'
              : 'rgba(255,255,255,0.03)',
            color: value[g.key] ? '#02C9A8' : 'rgba(255,255,255,0.6)',
          }}
          data-testid={`der-filter-${g.key}`}
        >
          <option value="" style={{ background: '#0A1432' }}>
            {g.label}
          </option>
          {g.options.map((o) => (
            <option key={o.value} value={o.value} style={{ background: '#0A1432' }}>
              {o.label}
              {o.count != null ? ` (${o.count})` : ''}
            </option>
          ))}
        </select>
      ))}
      {activeCount > 0 && (
        <button
          onClick={clearAll}
          className="flex items-center gap-1 text-white/40 hover:text-white/70"
          style={{ fontSize: 12 }}
          data-testid="der-filter-clear"
        >
          <X size={12} /> Clear
        </button>
      )}
    </div>
  )
}
