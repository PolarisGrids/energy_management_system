const SIZES = { sm: 'w-3 h-3 border-2', md: 'w-5 h-5 border-2', lg: 'w-8 h-8 border-4' }

export default function Spinner({ size = 'md', className = '' }) {
  return (
    <span
      className={`inline-block rounded-full border-white border-t-transparent animate-spin ${SIZES[size] || SIZES.md} ${className}`}
      role="status"
      aria-label="loading"
    />
  )
}
