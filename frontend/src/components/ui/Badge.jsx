const VARIANTS = {
  neutral: 'bg-white/10 text-white/80',
  success: 'bg-emerald-500/20 text-emerald-300',
  warn:    'bg-amber-500/20 text-amber-300',
  danger:  'bg-red-500/20 text-red-300',
  info:    'bg-blue-500/20 text-blue-300',
}

export default function Badge({ variant = 'neutral', children, className = '' }) {
  const cls = `inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${VARIANTS[variant] || VARIANTS.neutral} ${className}`
  return <span className={cls}>{children}</span>
}
