/**
 * KPI — metric tile with built-in empty/NaN guard (spec 015 FR-019).
 *
 * Props:
 *   - title (required)  — label
 *   - value              — numeric or string value
 *   - unit               — e.g. "%", "kW"
 *   - denom              — optional denominator; when 0 or null, falls back to "—"
 *   - numer              — optional numerator for percent computation (with denom)
 *   - trend              — +/- number (shown with arrow)
 *   - loading            — show skeleton
 *   - empty              — force empty state
 *   - icon               — lucide-react icon component
 *   - color              — accent colour (CSS string)
 */
export default function KPI({
  title,
  value,
  unit = '',
  denom = null,
  numer = null,
  trend = null,
  loading = false,
  empty = false,
  icon: Icon = null,
  color = '#02C9A8',
  sub = null,
}) {
  // NaN / empty-denominator guard — the regression-safe fix for MDMSMirror.
  let display
  if (loading) {
    display = null
  } else if (empty) {
    display = '—'
  } else if (denom !== null && denom !== undefined) {
    if (!denom || Number.isNaN(Number(denom))) {
      display = '—'
    } else if (numer !== null && numer !== undefined) {
      const pct = (Number(numer) / Number(denom)) * 100
      display = Number.isFinite(pct) ? pct.toFixed(1) + (unit || '%') : '—'
    } else {
      display = value ?? '—'
    }
  } else if (value === null || value === undefined || value === '') {
    display = '—'
  } else if (typeof value === 'number' && !Number.isFinite(value)) {
    display = '—'
  } else {
    display = `${value}${unit || ''}`
  }

  return (
    <div className="metric-card">
      <div className="flex items-start justify-between">
        {Icon && (
          <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: `${color}22` }}>
            <Icon size={18} style={{ color }} />
          </div>
        )}
        {trend !== null && trend !== undefined && (
          <span className="text-xs" style={{ color: trend >= 0 ? '#02C9A8' : '#E94B4B' }}>
            {trend >= 0 ? '▲' : '▼'} {Math.abs(trend)}
          </span>
        )}
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 26 }}>
          {loading
            ? <span className="inline-block w-16 h-6 bg-white/10 rounded animate-pulse" />
            : display}
        </div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 12 }}>{title}</div>
        {sub && <div style={{ color, fontSize: 11, marginTop: 3 }}>{sub}</div>}
      </div>
    </div>
  )
}
