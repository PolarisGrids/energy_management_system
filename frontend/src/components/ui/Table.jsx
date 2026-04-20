import Skeleton from './Skeleton'
import EmptyState from './EmptyState'

/**
 * Table — columns + rows + loading/empty states.
 * columns: [{ key, header, render? }]
 */
export default function Table({ columns = [], rows = [], loading = false, empty = null }) {
  if (loading) return <Skeleton lines={4} height={18} />
  if (!rows || rows.length === 0) {
    return empty || <EmptyState title="No rows" />
  }
  return (
    <table className="data-table w-full">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key}>{c.header ?? c.key}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={row.id ?? i}>
            {columns.map((c) => (
              <td key={c.key}>{c.render ? c.render(row) : row[c.key]}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
