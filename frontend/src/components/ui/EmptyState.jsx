import { Inbox } from 'lucide-react'

/**
 * EmptyState — used when there's no data (instead of hardcoded fallback
 * numbers). Spec 015 FR-020 regression for HESMirror.
 */
export default function EmptyState({
  icon: Icon = Inbox,
  title = 'No data',
  message = '',
  action = null,
  className = '',
}) {
  return (
    <div className={`flex flex-col items-center justify-center py-10 text-center ${className}`}>
      <Icon size={36} className="text-white/30 mb-2" />
      <div className="text-white/80 font-semibold text-sm">{title}</div>
      {message && <div className="text-white/50 text-xs mt-1 max-w-sm">{message}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
