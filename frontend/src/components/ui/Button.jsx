/**
 * Button — variant/size-aware button over existing Tailwind styles.
 * Spec 015-rbac-ui-lib FR-016 (shared UI library).
 */
const VARIANTS = {
  primary: 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white hover:brightness-110',
  secondary: 'bg-white/10 text-white hover:bg-white/20 border border-white/20',
  danger: 'bg-red-600 text-white hover:bg-red-500',
  ghost: 'bg-transparent text-white/80 hover:bg-white/10',
}

const SIZES = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3.5 py-2 text-sm',
  lg: 'px-5 py-3 text-base',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  className = '',
  children,
  ...rest
}) {
  const disabledCls = (disabled || loading) ? 'opacity-50 cursor-not-allowed' : ''
  const cls = `rounded-lg font-semibold transition-colors inline-flex items-center gap-2 ${VARIANTS[variant] || VARIANTS.primary} ${SIZES[size] || SIZES.md} ${disabledCls} ${className}`
  return (
    <button {...rest} disabled={disabled || loading} className={cls}>
      {loading && <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />}
      {children}
    </button>
  )
}
