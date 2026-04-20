import { Component } from 'react'
import { AlertTriangle } from 'lucide-react'

/**
 * Generic error boundary for page-level crashes.
 *
 * Used to catch render-time exceptions (malformed upstream payload, missing
 * fields, etc.) so a single bad tile never wipes an entire dashboard. Renders
 * a red glass-card matching the SSOT-unavailable banner style so operators
 * see the upstream problem in place rather than a white screen.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('polaris-ems error boundary caught:', error, info)
    if (typeof window !== 'undefined' && window.polarisToast?.error) {
      window.polarisToast.error('Render failure', String(error).slice(0, 200))
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="glass-card"
          style={{
            padding: 16,
            borderColor: 'rgba(233,75,75,0.4)',
            background: 'rgba(233,75,75,0.08)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
          }}
        >
          <AlertTriangle size={18} style={{ color: '#E94B4B', flexShrink: 0, marginTop: 2 }} />
          <div style={{ flex: 1 }}>
            <div className="text-white font-bold" style={{ fontSize: 13 }}>
              {this.props.title || 'Something went wrong rendering this view.'}
            </div>
            <div style={{ color: '#ABC7FF', fontSize: 12, marginTop: 4 }}>
              {String(this.state.error).slice(0, 300)}
            </div>
            {this.props.onRetry && (
              <button
                type="button"
                className="btn-secondary"
                style={{ marginTop: 8, fontSize: 12 }}
                onClick={() => {
                  this.setState({ error: null })
                  this.props.onRetry?.()
                }}
              >
                Retry
              </button>
            )}
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
