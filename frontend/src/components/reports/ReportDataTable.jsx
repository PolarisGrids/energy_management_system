import { useMemo, useState } from 'react'

// Backed by the mdms-analytics envelope:
//   { data: { reportName, columns: [{field,label,visible}], records: [] } }
// Columns with visible === false are hidden by default but selectable via
// the column-picker toggle (top-right of the table).
export default function ReportDataTable({ columns = [], records = [], emptyMessage = 'No records' }) {
  const [showHidden, setShowHidden] = useState(false)
  const visibleFields = useMemo(() => {
    return columns.filter((c) => showHidden || c.visible !== false).map((c) => c.field)
  }, [columns, showHidden])

  const visibleColumns = useMemo(() => {
    return columns.filter((c) => visibleFields.includes(c.field))
  }, [columns, visibleFields])

  if (!columns.length) {
    return (
      <div className="glass-card" style={{ padding: 32, textAlign: 'center', color: '#ABC7FF' }}>
        {emptyMessage}
      </div>
    )
  }

  const anyHidden = columns.some((c) => c.visible === false)

  return (
    <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
      {anyHidden && (
        <div style={{
          display: 'flex', justifyContent: 'flex-end', padding: '8px 14px',
          borderBottom: '1px solid #ABC7FF22',
        }}>
          <button
            type="button"
            onClick={() => setShowHidden((p) => !p)}
            className="btn-secondary"
            style={{ fontSize: 11, padding: '4px 10px' }}
          >
            {showHidden ? 'Hide internal columns' : 'Show all columns'}
          </button>
        </div>
      )}
      <div style={{ overflowX: 'auto', maxHeight: 560 }}>
        <table className="data-table" style={{ width: '100%', fontSize: 12 }}>
          <thead>
            <tr>
              {visibleColumns.map((c) => (
                <th key={c.field} style={{ whiteSpace: 'nowrap' }}>{c.label || c.field}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.length === 0 ? (
              <tr>
                <td colSpan={visibleColumns.length} style={{ textAlign: 'center', color: '#ABC7FF', padding: 24 }}>
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              records.map((row, i) => (
                <tr key={i}>
                  {visibleColumns.map((c) => (
                    <td key={c.field} style={{
                      whiteSpace: 'nowrap',
                      fontFamily: isNumericLike(row[c.field]) ? 'monospace' : 'inherit',
                    }}>
                      {formatCell(row[c.field])}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function isNumericLike(v) {
  if (v == null) return false
  if (typeof v === 'number') return true
  if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) return true
  return false
}

function formatCell(v) {
  if (v == null) return '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  return String(v)
}
