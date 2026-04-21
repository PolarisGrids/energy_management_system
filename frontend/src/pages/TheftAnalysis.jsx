/**
 * Theft Analysis — NTL scoring dashboard.
 *
 * Backed by /api/v1/theft/* (see endpoints/theft.py). The backend runs a
 * scheduled scorer against MDMS validation_rules (HH + daily + tamper
 * events) and persists a theft_score per meter. This page visualises:
 *
 *   • tier counts (critical / high / medium / low)
 *   • detector fire-rate breakdown
 *   • ranked suspect list with filters (tier, detector, min-score, search)
 *   • drill-down: fired-detector evidence + 7-day HH consumption curve
 *     with tamper-event markers overlaid
 *
 * The "Recompute" button triggers a manual scorer pass (blocking ~1-2 s on
 * the current 174-meter roster). In prod this is kicked off automatically
 * every 15 min by the lifespan background task.
 */
import { useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import {
  AlertTriangle, RefreshCw, Search, ShieldAlert, ShieldCheck, Zap,
  Activity, Clock, Filter, ChevronRight,
} from 'lucide-react'
import { theftAPI } from '@/services/api'

/* ───────────────────── helpers ───────────────────── */

function fmtTs(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

function fmtRel(iso) {
  if (!iso) return '—'
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return iso
  const diff = Date.now() - ts
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)} min ago`
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)} h ago`
  return `${Math.round(diff / 86_400_000)} d ago`
}

const TIER_COLOR = {
  critical: '#E94B4B',
  high:     '#F97316',
  medium:   '#F59E0B',
  low:      '#6B7280',
}

const SEV_COLOR = {
  critical: '#E94B4B',
  high:     '#F97316',
  medium:   '#F59E0B',
  low:      '#6B7280',
}

const DETECTOR_LABEL = {
  tamper_event:         'DLMS tamper event',
  time_tampering:       'Clock tampering',
  flat_line:            'Flat-line kWh',
  sudden_drop:          'Sudden drop',
  reverse_energy:       'Reverse energy',
  peer_zscore:          'Peer z-score',
  week_over_week:       'Week-over-week drop',
  phase_imbalance:      'Phase imbalance',
  md_collapse:          'MD collapse',
  load_factor_collapse: 'Load-factor collapse',
  partial_bypass:       'Partial bypass (30–60% drop)',
  full_bypass:          'Full bypass (>70% drop, meter online)',
}

function ScorePill({ score, tier }) {
  const color = TIER_COLOR[tier] || TIER_COLOR.low
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: 999, fontSize: 12, fontWeight: 800,
      background: `${color}22`, color, border: `1px solid ${color}55`,
    }}>{score?.toFixed?.(1) ?? score}</span>
  )
}

function TierBadge({ tier, count }) {
  const color = TIER_COLOR[tier] || TIER_COLOR.low
  return (
    <div style={{
      background: `${color}14`, border: `1px solid ${color}40`,
      borderRadius: 10, padding: '12px 14px', minWidth: 120, flex: '0 0 auto',
    }}>
      <div style={{ fontSize: 11, color, textTransform: 'uppercase', fontWeight: 700 }}>{tier}</div>
      <div style={{ fontSize: 26, fontWeight: 900, color: '#fff', marginTop: 2 }}>{count ?? 0}</div>
    </div>
  )
}

function EvidenceChip({ chip }) {
  const c = SEV_COLOR[chip.severity] || SEV_COLOR.low
  return (
    <span title={chip.label} style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600,
      background: `${c}1C`, color: c, border: `1px solid ${c}44`,
      marginRight: 4, marginBottom: 2,
    }}>
      <span>{DETECTOR_LABEL[chip.id] || chip.id}</span>
      <span style={{ opacity: 0.6 }}>+{chip.score}</span>
    </span>
  )
}

/* ───────────────────── main component ───────────────────── */

export default function TheftAnalysis() {
  const [summary, setSummary] = useState(null)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [recomputing, setRecomputing] = useState(false)
  const [banner, setBanner] = useState('')
  const [refreshAt, setRefreshAt] = useState(Date.now())

  // filters
  const [tier, setTier] = useState('')          // '' | critical | high | medium | low
  const [detector, setDetector] = useState('')
  const [q, setQ] = useState('')
  const [minScore, setMinScore] = useState(0)

  // drill-down
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  /* load summary + list */
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setBanner('')
    Promise.all([
      theftAPI.summary().catch(() => ({ data: null })),
      theftAPI.meters({
        page: 1,
        page_size: 200,
        risk_tier: tier || undefined,
        detector: detector || undefined,
        q: q || undefined,
        min_score: minScore > 0 ? minScore : undefined,
      }).catch((err) => {
        setBanner(err?.response?.data?.detail || 'Failed to load suspects')
        return { data: { items: [], total: 0 } }
      }),
    ]).then(([sum, list]) => {
      if (cancelled) return
      setSummary(sum.data)
      setItems(list.data.items || [])
      setTotal(list.data.total || 0)
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [tier, detector, q, minScore, refreshAt])

  /* drill-down fetch on selection */
  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    let cancelled = false
    setDetailLoading(true)
    theftAPI.meter(selectedId, { hh_days: 7, events_days: 30 })
      .then(({ data }) => { if (!cancelled) setDetail(data) })
      .catch((err) => {
        if (!cancelled) {
          setDetail(null)
          setBanner(`Drill-down failed: ${err?.response?.data?.detail || err.message}`)
        }
      })
      .finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [selectedId, refreshAt])

  const handleRecompute = async () => {
    setRecomputing(true)
    setBanner('')
    try {
      const { data } = await theftAPI.recompute()
      setBanner(
        `Re-scored ${data.meters_scored} meters in ${data.duration_ms} ms · ` +
        `${data.critical} critical, ${data.high} high, ${data.medium} medium, ${data.low} low`
      )
      setRefreshAt(Date.now())
    } catch (err) {
      setBanner(`Recompute failed: ${err?.response?.data?.detail || err.message}`)
    } finally {
      setRecomputing(false)
    }
  }

  /* detector fire chart */
  const detectorChart = useMemo(() => {
    const ds = summary?.detectors || []
    return {
      grid: { left: 140, right: 20, top: 10, bottom: 20 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'value', axisLabel: { color: 'rgba(255,255,255,0.45)' } },
      yAxis: {
        type: 'category',
        data: ds.map(d => DETECTOR_LABEL[d.detector_id] || d.detector_id),
        axisLabel: { color: 'rgba(255,255,255,0.75)', fontSize: 11 },
      },
      series: [{
        type: 'bar',
        data: ds.map(d => d.count),
        itemStyle: { color: '#F59E0B' },
        barMaxWidth: 16,
        label: { show: true, position: 'right', color: '#fff', fontSize: 11 },
      }],
    }
  }, [summary])

  /* HH consumption chart for drill-down */
  const hhChart = useMemo(() => {
    if (!detail?.hh_series?.length) return null
    const points = detail.hh_series.map(p => [p.ts, (p.import_wh || 0) / 1000])
    const exports_ = detail.hh_series.map(p => [p.ts, -((p.export_wh || 0) / 1000)])
    const events = (detail.tamper_events || [])
      .filter(e => e.event_ts)
      .map(e => ({
        xAxis: e.event_ts,
        lineStyle: { color: SEV_COLOR[e.event_code >= 200 && e.event_code < 300 ? 'high' : 'medium'], type: 'dashed' },
        label: {
          formatter: `${e.event_code}`, position: 'insideEndTop',
          color: '#fff', fontSize: 10, fontWeight: 700,
          backgroundColor: '#F9731688', padding: [2, 4], borderRadius: 3,
        },
      }))
    return {
      grid: { left: 48, right: 18, top: 30, bottom: 32 },
      tooltip: { trigger: 'axis' },
      legend: {
        data: ['Import kWh', 'Export kWh'],
        textStyle: { color: 'rgba(255,255,255,0.7)' },
        top: 0, right: 0,
      },
      xAxis: {
        type: 'time',
        axisLabel: { color: 'rgba(255,255,255,0.45)', fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        name: 'kWh / 30-min',
        nameTextStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 10 },
        axisLabel: { color: 'rgba(255,255,255,0.45)' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      },
      series: [
        {
          name: 'Import kWh',
          type: 'line',
          data: points,
          smooth: 0.2,
          symbol: 'none',
          lineStyle: { color: '#56CCF2', width: 1.4 },
          areaStyle: { color: 'rgba(86,204,242,0.12)' },
          markLine: events.length ? { silent: true, symbol: 'none', data: events } : undefined,
        },
        {
          name: 'Export kWh',
          type: 'line',
          data: exports_,
          smooth: 0.2,
          symbol: 'none',
          lineStyle: { color: '#E94B4B', width: 1.2 },
        },
      ],
    }
  }, [detail])

  const lastRun = summary?.last_run

  /* ───────────────────── render ───────────────────── */

  return (
    <div className="flex flex-col gap-3 h-full animate-slide-up" data-testid="theft-dashboard">
      {/* Header */}
      <div className="glass-card p-4 flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <div style={{
            width: 36, height: 36, borderRadius: 9,
            background: '#E94B4B22', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <ShieldAlert size={18} style={{ color: '#E94B4B' }} />
          </div>
          <div>
            <div style={{ fontSize: 18, fontWeight: 900, color: '#fff' }}>Theft Analysis</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>
              MDMS validation_rules · rule + statistical detectors · per-meter risk score
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {lastRun?.started_at && (
              <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <Clock size={11} /> last run {fmtRel(lastRun.started_at)} · {lastRun.duration_ms}ms
              </span>
            )}
            <button
              onClick={() => setRefreshAt(Date.now())}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
              style={{ background: 'rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.7)', border: '1px solid rgba(255,255,255,0.1)' }}
            >
              <RefreshCw size={13} /> Refresh
            </button>
            <button
              onClick={handleRecompute}
              disabled={recomputing}
              data-testid="theft-recompute"
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
              style={{
                background: '#E94B4B22', color: '#E94B4B', border: '1px solid #E94B4B55',
                opacity: recomputing ? 0.5 : 1,
              }}
            >
              <Zap size={13} /> {recomputing ? 'Scoring…' : 'Recompute now'}
            </button>
          </div>
        </div>

        {banner && (
          <div style={{
            background: '#F59E0B1A', border: '1px solid #F59E0B55',
            color: '#F59E0B', padding: '8px 12px', borderRadius: 8,
            fontSize: 12, display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <AlertTriangle size={14} />
            <span>{banner}</span>
          </div>
        )}

        {/* Tier counters */}
        <div className="flex gap-3 flex-wrap">
          <TierBadge tier="critical" count={summary?.tiers?.critical} />
          <TierBadge tier="high"     count={summary?.tiers?.high} />
          <TierBadge tier="medium"   count={summary?.tiers?.medium} />
          <TierBadge tier="low"      count={summary?.tiers?.low} />
          <div style={{
            background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 10, padding: '12px 14px', minWidth: 140,
          }}>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', fontWeight: 700 }}>Total scored</div>
            <div style={{ fontSize: 26, fontWeight: 900, color: '#fff', marginTop: 2 }}>{summary?.total_meters ?? 0}</div>
          </div>
        </div>

        {/* Filter row */}
        <div className="flex items-end gap-3 flex-wrap">
          <div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 4, textTransform: 'uppercase' }}>Search</div>
            <div style={{ position: 'relative' }}>
              <Search size={13} style={{ position: 'absolute', left: 8, top: 8, color: 'rgba(255,255,255,0.4)' }} />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="meter id / account"
                data-testid="theft-search"
                style={{
                  background: 'rgba(255,255,255,0.06)', color: '#fff',
                  border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
                  padding: '6px 10px 6px 26px', fontSize: 13, width: 190,
                }}
              />
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 4, textTransform: 'uppercase' }}>Risk tier</div>
            <select
              value={tier}
              onChange={(e) => setTier(e.target.value)}
              data-testid="theft-tier"
              style={{
                background: 'rgba(255,255,255,0.06)', color: '#fff',
                border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
                padding: '6px 10px', fontSize: 13,
              }}
            >
              <option value="">All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 4, textTransform: 'uppercase' }}>Detector</div>
            <select
              value={detector}
              onChange={(e) => setDetector(e.target.value)}
              data-testid="theft-detector"
              style={{
                background: 'rgba(255,255,255,0.06)', color: '#fff',
                border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
                padding: '6px 10px', fontSize: 13, minWidth: 170,
              }}
            >
              <option value="">All</option>
              {Object.keys(DETECTOR_LABEL).map(id => (
                <option key={id} value={id}>{DETECTOR_LABEL[id]}</option>
              ))}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 4, textTransform: 'uppercase' }}>
              Min score ({minScore})
            </div>
            <input
              type="range" min={0} max={100} step={5}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              data-testid="theft-min-score"
              style={{ width: 180 }}
            />
          </div>
          <div className="ml-auto" style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>
            <Filter size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
            <span data-testid="theft-count">{items.length}</span> / {total} shown
          </div>
        </div>
      </div>

      {/* Body: suspects + right column (detector chart + drill-down) */}
      <div className="grid grid-cols-3 gap-3 flex-1 min-h-0">
        {/* Suspect table */}
        <div className="glass-card p-3 col-span-2 overflow-hidden flex flex-col">
          <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', marginBottom: 8 }}>
            Ranked suspects
          </div>
          <div className="overflow-auto flex-1">
            <table style={{ width: '100%', fontSize: 13 }} data-testid="theft-table">
              <thead style={{ position: 'sticky', top: 0, background: 'rgba(10,15,30,0.95)', zIndex: 1 }}>
                <tr style={{ textAlign: 'left', color: 'rgba(255,255,255,0.45)', fontSize: 11, textTransform: 'uppercase' }}>
                  <th style={{ padding: '8px 6px' }}>#</th>
                  <th>Meter</th>
                  <th>Type</th>
                  <th>Account</th>
                  <th>Score</th>
                  <th>Tier</th>
                  <th>Evidence</th>
                  <th style={{ width: 28 }}></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', padding: 24, color: 'rgba(255,255,255,0.35)' }}>Loading…</td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', padding: 24, color: 'rgba(255,255,255,0.35)' }}>No suspects match current filters.</td></tr>
                ) : items.map((s, i) => (
                  <tr
                    key={s.device_identifier}
                    onClick={() => setSelectedId(s.device_identifier)}
                    style={{
                      cursor: 'pointer',
                      borderTop: '1px solid rgba(255,255,255,0.04)',
                      background: selectedId === s.device_identifier ? 'rgba(233,75,75,0.08)' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '8px 6px', color: 'rgba(255,255,255,0.35)', fontSize: 11 }}>{i + 1}</td>
                    <td style={{ fontFamily: 'monospace', color: '#ABC7FF' }}>{s.device_identifier}</td>
                    <td style={{ color: 'rgba(255,255,255,0.6)' }}>{s.meter_type || '—'}</td>
                    <td style={{ color: 'rgba(255,255,255,0.6)' }}>{s.account_id || '—'}</td>
                    <td><ScorePill score={s.score} tier={s.risk_tier} /></td>
                    <td style={{ textTransform: 'capitalize', color: TIER_COLOR[s.risk_tier] || '#ccc', fontWeight: 700, fontSize: 12 }}>{s.risk_tier}</td>
                    <td>
                      {(s.top_evidence || []).slice(0, 3).map(ch => (
                        <EvidenceChip key={ch.id} chip={ch} />
                      ))}
                    </td>
                    <td>
                      <ChevronRight size={14} style={{ color: 'rgba(255,255,255,0.3)' }} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-3 min-h-0">
          {/* Detector fire chart */}
          <div className="glass-card p-3" data-testid="theft-detector-chart">
            <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Activity size={14} style={{ color: '#F59E0B' }} />
              Detector fire-rate
            </div>
            {summary?.detectors?.length ? (
              <ReactECharts option={detectorChart} style={{ height: 240 }} notMerge />
            ) : (
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', padding: 20 }}>
                No detectors have fired in the current dataset.
              </div>
            )}
          </div>

          {/* Drill-down */}
          <div className="glass-card p-3 flex-1 min-h-0 overflow-auto" data-testid="theft-detail">
            <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <ShieldCheck size={14} style={{ color: '#56CCF2' }} />
              Meter drill-down
            </div>
            {!selectedId ? (
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
                Click a row to see the evidence trail + half-hourly consumption with tamper markers.
              </div>
            ) : detailLoading ? (
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>Loading…</div>
            ) : !detail ? (
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>No detail available.</div>
            ) : (
              <>
                <div style={{ fontFamily: 'monospace', fontSize: 15, color: '#fff' }}>{detail.device_identifier}</div>
                <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 2 }}>
                  {detail.meter_type || 'unknown type'} · {detail.account_id || 'no account'}
                  {detail.manufacturer ? ` · ${detail.manufacturer}` : ''}
                </div>

                <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
                  <ScorePill score={detail.score} tier={detail.risk_tier} />
                  <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>
                    computed {fmtRel(detail.computed_at)}
                  </span>
                </div>

                {/* Evidence list */}
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', marginBottom: 6 }}>
                    Why flagged
                  </div>
                  {(detail.detector_results || [])
                    .filter(d => d.fired)
                    .sort((a, b) => (b.weight * b.score) - (a.weight * a.score))
                    .map(d => {
                      const c = SEV_COLOR[d.severity] || SEV_COLOR.low
                      const contrib = (d.weight * d.score).toFixed(1)
                      return (
                        <div key={d.detector_id} style={{
                          borderLeft: `3px solid ${c}`, paddingLeft: 8, marginBottom: 8,
                        }}>
                          <div style={{ fontSize: 12, color: '#fff', fontWeight: 600 }}>
                            {d.label} <span style={{ color: c, fontWeight: 700 }}>+{contrib}</span>
                          </div>
                          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', marginTop: 2 }}>
                            {renderEvidence(d.evidence)}
                          </div>
                        </div>
                      )
                    })
                  }
                </div>

                {/* HH curve with tamper markers */}
                {hhChart && (
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', marginBottom: 4 }}>
                      7-day consumption (markers = DLMS tamper events)
                    </div>
                    <ReactECharts option={hhChart} style={{ height: 220 }} notMerge />
                  </div>
                )}

                {/* Tamper timeline */}
                {detail.tamper_events?.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', marginBottom: 4 }}>
                      Tamper events (30 days)
                    </div>
                    <ul style={{ fontSize: 12, color: 'rgba(255,255,255,0.75)', listStyle: 'none', padding: 0 }}>
                      {detail.tamper_events.slice(0, 10).map((e, i) => (
                        <li key={i} style={{ display: 'flex', gap: 8, padding: '3px 0' }}>
                          <span style={{ color: '#F97316', fontFamily: 'monospace' }}>[{e.event_code}]</span>
                          <span>{e.event_label}</span>
                          <span style={{ color: 'rgba(255,255,255,0.4)', marginLeft: 'auto' }}>
                            {e.event_source} · {fmtTs(e.event_ts)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/* pretty-print the compact evidence payload without dumping raw JSON */
function renderEvidence(ev) {
  if (!ev || typeof ev !== 'object') return null
  const pick = (k) => ev[k]
  const pieces = []
  if (pick('event_count') !== undefined) pieces.push(`${pick('event_count')} events`)
  if (pick('distinct_codes')) pieces.push(`codes ${pick('distinct_codes').join(',')}`)
  if (pick('mean_wh_per_slot') !== undefined) pieces.push(`μ ${pick('mean_wh_per_slot')} Wh`)
  if (pick('coeff_of_variation') !== undefined) pieces.push(`CV ${pick('coeff_of_variation')}`)
  if (pick('ratio') !== undefined) pieces.push(`ratio ${pick('ratio')}`)
  if (pick('drop_fraction') !== undefined) pieces.push(`drop ${(pick('drop_fraction') * 100).toFixed(1)}%`)
  if (pick('total_export_wh_7d') !== undefined) pieces.push(`export ${pick('total_export_wh_7d')} Wh/7d`)
  if (pick('z_score') !== undefined) pieces.push(`z ${pick('z_score')}`)
  if (pick('worst_ratio') !== undefined) pieces.push(`max/min ${pick('worst_ratio')}`)
  if (pick('historical_max_md_w') !== undefined) pieces.push(
    `MD ${pick('historical_max_md_w')}→${pick('recent_max_md_w')} W`
  )
  if (pick('load_factor') !== undefined) pieces.push(`LF ${pick('load_factor')}`)
  if (pick('reason')) pieces.push(pick('reason'))
  return pieces.join(' · ') || JSON.stringify(ev).slice(0, 80)
}
