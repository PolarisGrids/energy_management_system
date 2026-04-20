/**
 * Skeleton — placeholder while data loads.
 */
export default function Skeleton({ width = '100%', height = 16, lines = 1, className = '' }) {
  const rows = Array.from({ length: lines })
  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      {rows.map((_, i) => (
        <div
          key={i}
          className="bg-white/10 rounded animate-pulse"
          style={{ width, height }}
        />
      ))}
    </div>
  )
}
