/**
 * NTL Detection Dashboard — spec 018 W3.T9 / US-9.
 *
 * Landing surface for Non-Technical-Loss operators. Ranked suspects table
 * (left), energy-balance top-gaps card (right), drill-down detail panel
 * when an operator selects a suspect.
 *
 * Scoring source contract:
 *   { source: "mdms" | "local", scoring_available: bool, items: [...], banner?: string }
 *
 * When `scoring_available === false` a banner is rendered ("Using event
 * correlation only — scoring unavailable") — this is acceptance scenario ②
 * of US-9 and MUST stay visible whenever MDMS NTL is disabled.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle, Zap, Search, RefreshCw, Flag, TrendingUp,
} from 'lucide-react'
import { ntlAPI } from '@/services/api'

function fmtTs(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

function ScorePill({ score }) {
  const color = score >= 80 ? '#E94B4B' : score >= 50 ? '#F97316' : score >= 20 ? '#F59E0B' : '#6B7280'
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: 999, fontSize: 12, fontWeight: 800,
      background: `${color}22`, color, border: `1px solid ${color}40`,
    }}>{score}</span>
  )
}

export default function NTL() {
  const [params, setParams] = useSearchParams()
  const [suspectsResp, setSuspectsResp] = useState({ source: 'local', scoring_available: false, items: [] })
  const [topGaps, setTopGaps] = useState([])
  const [selected, setSelected] = useState(null)
  const [dtrFilter, setDtrFilter] = useState(params.get('dtr') || '')
  const [minScore, setMinScore] = useState(Number(params.get('min') ?? 20))
  const [loading, setLoading] = useState(true)
  const [refreshAt, setRefreshAt] = useState(Date.now())

  const tabFromQuery = params.get('tab') || 'suspects'

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([
      ntlAPI.suspects({
        dtr_id: dtrFilter || undefined,
        min_score: minScore,
        limit: 500,
      }).catch(() => ({ data: { source: 'local', scoring_available: false, items: [], banner: 'Backend unreachable' } })),
      ntlAPI.topGaps({ limit: 10, hours: 24 }).catch(() => ({ data: { rows: [] } })),
    ]).then(([suspects, gaps]) => {
      if (cancelled) return
      setSuspectsResp(suspects.data)
      setTopGaps(gaps.data.rows || [])
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [dtrFilter, minScore, refreshAt])

  const applyFilters = () => {
    const next = new URLSearchParams(params)
    if (dtrFilter) next.set('dtr', dtrFilter); else next.delete('dtr')
    next.set('min', String(minScore))
    setParams(next, { replace: true })
    setRefreshAt(Date.now())
  }

  const items = suspectsResp.items || []
  const totalScore = useMemo(() => items.reduce((a, s) => a + s.score, 0), [items])

  return (
    <div className="flex flex-col gap-3 h-full animate-slide-up" data-testid="ntl-dashboard">
      <div className="glass-card p-4 flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <div style={{
            width: 36, height: 36, borderRadius: 9,
            background: '#F59E0B22', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Flag size={18} style={{ color: '#F59E0B' }} />
          </div>
          <div>
            <div style={{ fontSize: 18, fontWeight: 900, color: '#fff' }}>NTL Detection</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>
              {suspectsResp.source === 'mdms'
                ? 'Source: MDMS NTL scoring engine'
                : 'Source: local event correlation'}
            </div>
          </div>
          <button
            onClick={() => setRefreshAt(Date.now())}
            className="ml-auto flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
            style={{ background: 'rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.7)', border: '1px solid rgba(255,255,255,0.1)' }}
          >
            <RefreshCw size={13} /> Refresh
          </button>
        </div>

        {!suspectsResp.scoring_available && (
          <div data-testid="ntl-banner" style={{
            background: '#F59E0B1A', border: '1px solid #F59E0B55',
            color: '#F59E0B', padding: '10px 12px', borderRadius: 8,
            display: 'flex', alignItems: 'center', gap: 8, fontSize: 13,
          }}>
            <AlertTriangle size={15} />
            <span>{suspectsResp.banner || 'Using event correlation only — scoring unavailable'}</span>
          </div>
        )}

        <div className="flex items-end gap-3 flex-wrap">
          <div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 4, textTransform: 'uppercase' }}>DTR id</div>
            <input
              value={dtrFilter}
              onChange={(e) => setDtrFilter(e.target.value.replace(/\D/g, ''))}
              placeholder="e.g. 42"
              data-testid="ntl-dtr-filter"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#fff', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, padding: '6px 10px', fontSize: 13, width: 120 }}
            />
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 4, textTransform: 'uppercase' }}>Min score ({minScore})</div>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              data-testid="ntl-min-score"
              style={{ width: 180 }}
            />
          </div>
          <button
            onClick={applyFilters}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
            style={{ background: '#F59E0B22', color: '#F59E0B', border: '1px solid #F59E0B55' }}
          >
            <Search size={13} /> Apply
          </button>
          <div className="ml-auto" style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>
            <span data-testid="ntl-suspect-count">{items.length}</span> suspects · total score {totalScore}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 flex-1 min-h-0">
        {/* Suspects table (2 cols) */}
        <div className="glass-card p-3 col-span-2 overflow-hidden flex flex-col">
          <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', marginBottom: 8 }}>Ranked suspects</div>
          <div className="overflow-auto flex-1">
            <table style={{ width: '100%', fontSize: 13 }} data-testid="ntl-suspects-table">
              <thead style={{ position: 'sticky', top: 0, background: 'rgba(10,15,30,0.95)' }}>
                <tr style={{ textAlign: 'left', color: 'rgba(255,255,255,0.45)', fontSize: 11, textTransform: 'uppercase' }}>
                  <th style={{ padding: '8px 6px' }}>Meter</th>
                  <th>Customer</th>
                  <th>DTR</th>
                  <th>Score</th>
                  <th>Events (7d)</th>
                  <th>Last event</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: 20, color: 'rgba(255,255,255,0.35)' }}>Loading…</td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: 20, color: 'rgba(255,255,255,0.35)' }}>No suspects above threshold.</td></tr>
                ) : items.map((s, i) => (
                  <tr
                    key={s.meter_serial}
                    onClick={() => setSelected(s)}
                    style={{
                      cursor: 'pointer',
                      borderTop: '1px solid rgba(255,255,255,0.04)',
                      background: selected?.meter_serial === s.meter_serial ? 'rgba(245,158,11,0.08)' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '8px 6px', fontFamily: 'monospace', color: '#ABC7FF' }}>{s.meter_serial}</td>
                    <td style={{ color: 'rgba(255,255,255,0.8)' }}>{s.customer_name || '—'}</td>
                    <td style={{ color: 'rgba(255,255,255,0.55)' }}>{s.dtr_name || s.dtr_id || '—'}</td>
                    <td><ScorePill score={s.score} /></td>
                    <td style={{ color: 'rgba(255,255,255,0.7)' }}>{s.event_count_7d ?? '—'}</td>
                    <td style={{ color: 'rgba(255,255,255,0.45)' }}>{fmtTs(s.last_event)} {s.last_event_type ? <span style={{ color: '#F59E0B' }}>· {s.last_event_type}</span> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Top-gap DTRs + selected detail */}
        <div className="flex flex-col gap-3 min-h-0">
          <div className="glass-card p-3 flex flex-col min-h-0" data-testid="ntl-top-gaps">
            <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <TrendingUp size={14} style={{ color: '#F59E0B' }} />
              Top 10 DTR energy-balance gaps (24h)
            </div>
            <div className="overflow-auto flex-1">
              <table style={{ width: '100%', fontSize: 12 }}>
                <thead>
                  <tr style={{ color: 'rgba(255,255,255,0.4)', fontSize: 11, textTransform: 'uppercase', textAlign: 'left' }}>
                    <th style={{ padding: '6px 4px' }}>DTR</th>
                    <th>Input kWh</th>
                    <th>Downstream</th>
                    <th>Gap %</th>
                  </tr>
                </thead>
                <tbody>
                  {topGaps.length === 0 && (
                    <tr><td colSpan={4} style={{ padding: 10, color: 'rgba(255,255,255,0.35)', textAlign: 'center' }}>No DTRs with readings.</td></tr>
                  )}
                  {topGaps.map(g => (
                    <tr key={g.dtr_id}
                        onClick={() => setDtrFilter(String(g.dtr_id))}
                        style={{ cursor: 'pointer', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                      <td style={{ padding: '6px 4px', color: '#ABC7FF' }}>{g.dtr_name || `DTR-${g.dtr_id}`}</td>
                      <td style={{ color: 'rgba(255,255,255,0.8)' }}>{g.feeder_input_kwh?.toFixed(1) ?? '—'}</td>
                      <td style={{ color: 'rgba(255,255,255,0.6)' }}>{g.downstream_kwh?.toFixed(1) ?? '—'}</td>
                      <td>
                        <span style={{
                          color: g.gap_pct >= 20 ? '#E94B4B' : g.gap_pct >= 10 ? '#F97316' : '#02C9A8',
                          fontWeight: 800,
                        }}>{g.gap_pct?.toFixed(1)}%</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Selection detail */}
          <div className="glass-card p-3" data-testid="ntl-detail">
            <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', marginBottom: 8 }}>Suspect detail</div>
            {selected ? (
              <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.75)' }}>
                <div style={{ fontFamily: 'monospace', fontSize: 15, color: '#fff' }}>{selected.meter_serial}</div>
                <div style={{ marginTop: 4, fontSize: 12, color: 'rgba(255,255,255,0.5)' }}>
                  {selected.customer_name || 'unknown customer'} · {selected.account_number || 'no account'}
                </div>
                <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                  <div>Score: <ScorePill score={selected.score} /></div>
                  <div>DTR: {selected.dtr_name || selected.dtr_id || '—'}</div>
                  <div>Events (7d): {selected.event_count_7d}</div>
                  <div>Last event: {fmtTs(selected.last_event)} {selected.last_event_type ? `(${selected.last_event_type})` : ''}</div>
                </div>
                {selected.contributions?.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', marginBottom: 4 }}>
                      Event breakdown
                    </div>
                    <ul style={{ fontSize: 12, color: 'rgba(255,255,255,0.7)' }}>
                      {selected.contributions.map((c) => (
                        <li key={c.event_type}>
                          <span style={{ color: '#F59E0B' }}>● </span>
                          {c.event_type} × {c.count}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div style={{ marginTop: 10 }}>
                  <Link to={`/gis?focus=${selected.meter_serial}`} style={{ color: '#56CCF2', fontSize: 12 }}>
                    View on map →
                  </Link>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
                Pick a suspect to see event breakdown + drill-downs.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
