import { AlertTriangle, RefreshCw } from 'lucide-react'

/**
 * Inline red panel shown when an SSOT upstream (MDMS / HES) is unreachable.
 *
 * Spec 018 §Data-Consistency Contract: in `SSOT_MODE=strict` EMS MUST render
 * an explicit "<upstream> unavailable — last refresh at HH:MM:SS" banner with
 * NO hardcoded fallback numbers below it. Pages should place this component
 * where the data grid / chart would live.
 */
export default function UpstreamErrorPanel({ upstream = 'upstream', detail, lastRefresh, onRetry }) {
  return (
    <div
      role="alert"
      className="glass-card"
      style={{
        padding: 20,
        borderColor: 'rgba(233,75,75,0.45)',
        background: 'rgba(233,75,75,0.08)',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
      }}
      data-testid={`upstream-error-${upstream}`}
    >
      <AlertTriangle size={20} style={{ color: '#E94B4B', flexShrink: 0 }} />
      <div style={{ flex: 1 }}>
        <div className="text-white font-bold" style={{ fontSize: 14 }}>
          {upstream.toUpperCase()} unavailable
        </div>
        <div style={{ color: '#ABC7FF', fontSize: 12, marginTop: 4 }}>
          {detail || 'Upstream did not respond in time. Showing no data rather than a fallback.'}
          {lastRefresh && (
            <>
              {' '}
              Last successful refresh {new Date(lastRefresh).toLocaleTimeString()}.
            </>
          )}
        </div>
      </div>
      {onRetry && (
        <button type="button" className="btn-secondary" onClick={onRetry} style={{ fontSize: 12 }}>
          <RefreshCw size={13} style={{ marginRight: 4 }} />
          Retry
        </button>
      )}
    </div>
  )
}
