// W5 — Generic, sortable, paginated consumer/asset table for DER pages.
//
// columns: [{ key, label, align?, render?(row) }]
// rows:    array of asset rows (DERAssetLatest shape from /der/telemetry)
// onRowClick(row) — invoked when a row or its arrow button is clicked.
import { useMemo, useState } from 'react'
import { ChevronRight, ArrowUp, ArrowDown } from 'lucide-react'

export default function DERConsumerTable({
  columns,
  rows,
  onRowClick,
  emptyLabel = 'No matching consumers.',
  totalCount,
  page,
  pageSize,
  onPageChange,
}) {
  const [sort, setSort] = useState({ key: null, dir: 'asc' })

  const sorted = useMemo(() => {
    if (!sort.key) return rows
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = a[sort.key]
      const bv = b[sort.key]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'number') return (av - bv) * dir
      return String(av).localeCompare(String(bv)) * dir
    })
  }, [rows, sort])

  const toggle = (key) =>
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' },
    )

  const totalPages =
    totalCount != null && pageSize ? Math.max(1, Math.ceil(totalCount / pageSize)) : null

  return (
    <div className="glass-card overflow-hidden" data-testid="der-consumer-table">
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 40 }}>#</th>
              {columns.map((c) => (
                <th
                  key={c.key}
                  onClick={c.sortable !== false ? () => toggle(c.key) : undefined}
                  style={{
                    cursor: c.sortable !== false ? 'pointer' : 'default',
                    textAlign: c.align || 'left',
                    userSelect: 'none',
                  }}
                >
                  <span className="inline-flex items-center gap-1">
                    {c.label}
                    {sort.key === c.key &&
                      (sort.dir === 'asc' ? (
                        <ArrowUp size={11} />
                      ) : (
                        <ArrowDown size={11} />
                      ))}
                  </span>
                </th>
              ))}
              <th style={{ width: 40 }} />
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + 2}
                  className="text-center py-10 text-white/30"
                  style={{ fontSize: 13 }}
                >
                  {emptyLabel}
                </td>
              </tr>
            ) : (
              sorted.map((row, idx) => {
                const baseIdx =
                  page != null && pageSize ? (page - 1) * pageSize + idx + 1 : idx + 1
                return (
                  <tr
                    key={row.id ?? idx}
                    onClick={() => onRowClick?.(row)}
                    style={{ cursor: onRowClick ? 'pointer' : 'default' }}
                    data-testid={`der-consumer-row-${row.id ?? idx}`}
                  >
                    <td className="text-white/30 font-mono text-xs">{baseIdx}</td>
                    {columns.map((c) => (
                      <td
                        key={c.key}
                        style={{ textAlign: c.align || 'left' }}
                      >
                        {c.render ? c.render(row) : row[c.key] ?? '—'}
                      </td>
                    ))}
                    <td>
                      {onRowClick && (
                        <button
                          className="text-white/40 hover:text-[#02C9A8]"
                          onClick={(e) => {
                            e.stopPropagation()
                            onRowClick(row)
                          }}
                          aria-label="open detail"
                        >
                          <ChevronRight size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {totalPages && totalPages > 1 && (
        <div
          className="flex items-center justify-between px-4 py-3 border-t border-white/5"
          style={{ fontSize: 12 }}
          data-testid="der-consumer-pagination"
        >
          <div className="text-white/40">
            Showing {(page - 1) * pageSize + 1}–
            {Math.min(page * pageSize, totalCount)} of {totalCount}
          </div>
          <div className="flex items-center gap-2">
            <button
              className="btn-secondary"
              style={{ padding: '4px 10px', fontSize: 12 }}
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              Prev
            </button>
            <span className="text-white/50">
              {page} / {totalPages}
            </span>
            <button
              className="btn-secondary"
              style={{ padding: '4px 10px', fontSize: 12 }}
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
