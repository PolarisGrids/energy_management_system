/**
 * Outage Detail — spec 018 W3.T4.
 *
 * Shows a single `outage_incident` with its timeline plus action buttons:
 *   * Acknowledge
 *   * Dispatch crew  (requires WFM_ENABLED server-side)
 *   * Add note
 *   * FLISR isolate / restore (requires SMART_INVERTER_COMMANDS_ENABLED)
 *
 * All actions are gated client-side by RBAC role. Operators see reads and
 * acknowledge/note. Supervisors & Admins can dispatch crews. FLISR is
 * restricted to Admins (network switching is dangerous).
 */
import { useState, useEffect, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, RefreshCw, AlertTriangle, CheckCheck, Truck,
  MessageSquarePlus, Power, PowerOff, Activity,
} from 'lucide-react'
import { outagesAPI } from '@/services/api'
import useAuthStore from '@/stores/authStore'
import { useToast } from '@/components/ui/Toast'

const STATUS_BADGE = {
  DETECTED: 'badge-critical',
  INVESTIGATING: 'badge-high',
  DISPATCHED: 'badge-medium',
  RESTORED: 'badge-ok',
  CLOSED: 'badge-low',
}

const fmtTime = (v) => (v ? new Date(v).toLocaleString('en-ZA') : '—')

// Role gates — mirrors ProtectedRoute semantics from spec 015.
const canAckOrNote = (role) => !!role  // any authenticated user
const canDispatch = (role) => ['admin', 'supervisor', 'operator'].includes(role)
const canFlisr = (role) => role === 'admin'


function Section({ title, children, right }) {
  return (
    <div className="glass-card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-white font-semibold" style={{ fontSize: 14 }}>{title}</div>
        {right}
      </div>
      {children}
    </div>
  )
}

function TimelineList({ events }) {
  if (!events?.length) {
    return <div className="text-white/40 text-sm">No timeline events yet.</div>
  }
  return (
    <ul className="space-y-3">
      {events.map((e, idx) => (
        <li key={idx} className="flex items-start gap-3">
          <div
            className="w-2 h-2 rounded-full mt-2 shrink-0"
            style={{ background: e.event_type?.includes('restored') ? '#02C9A8' : '#F59E0B' }}
          />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-white font-medium text-sm">
                {e.event_type?.replace(/_/g, ' ')}
              </span>
              <span className="text-white/40 text-xs">{fmtTime(e.at)}</span>
              {e.actor_user_id && (
                <span className="text-accent-blue text-xs">by user {e.actor_user_id}</span>
              )}
            </div>
            {e.details && (
              <pre
                className="mt-1 text-white/60 text-xs overflow-x-auto"
                style={{ whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, monospace' }}
              >
                {JSON.stringify(e.details, null, 2)}
              </pre>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}


export default function OutageDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const toast = useToast()
  const [incident, setIncident] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)  // which action is running
  const [noteText, setNoteText] = useState('')
  const [crewId, setCrewId] = useState('')
  const [eta, setEta] = useState('')

  const role = user?.role ?? ''

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await outagesAPI.get(id)
      setIncident(data)
    } catch (err) {
      setError(err?.response?.data?.detail ?? err?.message ?? 'Failed to load incident')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const runAction = async (label, fn, onSuccess) => {
    setBusy(label)
    try {
      await fn()
      toast.success(`${label} succeeded`)
      onSuccess?.()
      await load()
    } catch (err) {
      toast.error(
        `${label} failed`,
        err?.response?.data?.detail ?? err?.message ?? 'Unknown error',
      )
    } finally {
      setBusy(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-white/40">
        <RefreshCw size={16} className="animate-spin mr-3" />
        Loading outage…
      </div>
    )
  }
  if (error || !incident) {
    return (
      <div className="glass-card p-5 flex items-center gap-3"
        style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}>
        <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
        <span className="text-white/80 text-sm">{error ?? 'Incident not found'}</span>
        <Link to="/outages" className="ml-auto btn-secondary" style={{ padding: '6px 14px', fontSize: 12 }}>
          Back
        </Link>
      </div>
    )
  }

  const closed = ['RESTORED', 'CLOSED'].includes(incident.status)
  const durationS = incident.closed_at
    ? Math.round((new Date(incident.closed_at) - new Date(incident.opened_at)) / 1000)
    : Math.round((Date.now() - new Date(incident.opened_at)) / 1000)

  return (
    <div className="space-y-5 animate-slide-up">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/outages')} className="text-white/60 hover:text-white">
          <ArrowLeft size={16} />
        </button>
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>Outage {incident.id.slice(0, 8)}</h1>
          <div className="text-white/50 text-xs">Opened {fmtTime(incident.opened_at)}</div>
        </div>
        <span className={`ml-auto ${STATUS_BADGE[incident.status] ?? 'badge-info'}`}>
          {incident.status}
        </span>
      </div>

      {/* Summary tiles */}
      <div className="grid grid-cols-4 gap-4">
        <Section title="Meters affected">
          <div className="text-white font-black" style={{ fontSize: 28 }}>
            {incident.affected_meter_count ?? 0}
          </div>
          <div className="text-white/40 text-xs">restored: {incident.restored_meter_count ?? 0}</div>
        </Section>
        <Section title="Confidence">
          <div className="text-white font-black" style={{ fontSize: 28 }}>
            {incident.confidence_pct != null ? `${Number(incident.confidence_pct).toFixed(1)}%` : '—'}
          </div>
          <div className="text-white/40 text-xs">DTR coverage estimate</div>
        </Section>
        <Section title="Duration">
          <div className="text-white font-black" style={{ fontSize: 28 }}>
            {Math.floor(durationS / 60)}m {durationS % 60}s
          </div>
          <div className="text-white/40 text-xs">{closed ? 'closed' : 'open'}</div>
        </Section>
        <Section title="Affected DTRs">
          <div className="text-white font-bold text-sm">
            {(incident.affected_dtr_ids ?? []).join(', ') || '—'}
          </div>
        </Section>
      </div>

      {/* Actions */}
      <Section title="Actions">
        <div className="flex flex-wrap gap-3">
          {canAckOrNote(role) && !closed && (
            <button
              className="btn-primary flex items-center gap-2"
              style={{ padding: '8px 14px', fontSize: 12 }}
              disabled={busy === 'Acknowledge'}
              onClick={() =>
                runAction('Acknowledge', () =>
                  outagesAPI.acknowledge(incident.id, { note: 'acknowledged' })
                )
              }
            >
              <CheckCheck size={12} /> Acknowledge
            </button>
          )}
          {canDispatch(role) && !closed && (
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Crew ID"
                value={crewId}
                onChange={(e) => setCrewId(e.target.value)}
                className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
                style={{ width: 120 }}
              />
              <input
                type="number"
                placeholder="ETA min"
                value={eta}
                onChange={(e) => setEta(e.target.value)}
                className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm"
                style={{ width: 100 }}
              />
              <button
                className="btn-secondary flex items-center gap-2"
                style={{ padding: '8px 14px', fontSize: 12 }}
                disabled={!crewId || busy === 'Dispatch crew'}
                onClick={() =>
                  runAction('Dispatch crew', () =>
                    outagesAPI.dispatchCrew(incident.id, {
                      crew_id: crewId,
                      eta_minutes: eta ? Number(eta) : null,
                    })
                  )
                }
              >
                <Truck size={12} /> Dispatch
              </button>
            </div>
          )}
          {canFlisr(role) && !closed && (
            <>
              <button
                className="btn-secondary flex items-center gap-2"
                style={{ padding: '8px 14px', fontSize: 12 }}
                disabled={busy === 'FLISR isolate'}
                onClick={() =>
                  runAction('FLISR isolate', () => outagesAPI.flisrIsolate(incident.id, {}))
                }
              >
                <PowerOff size={12} /> FLISR isolate
              </button>
              <button
                className="btn-secondary flex items-center gap-2"
                style={{ padding: '8px 14px', fontSize: 12 }}
                disabled={busy === 'FLISR restore'}
                onClick={() =>
                  runAction('FLISR restore', () => outagesAPI.flisrRestore(incident.id, {}))
                }
              >
                <Power size={12} /> FLISR restore
              </button>
            </>
          )}
          {closed && (
            <div className="text-white/50 text-sm flex items-center gap-2">
              <Activity size={12} /> Incident closed — no further actions.
            </div>
          )}
        </div>

        {canAckOrNote(role) && (
          <div className="flex items-center gap-2 mt-3">
            <input
              type="text"
              placeholder="Add note…"
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm flex-1"
            />
            <button
              className="btn-secondary flex items-center gap-2"
              style={{ padding: '8px 14px', fontSize: 12 }}
              disabled={!noteText.trim() || busy === 'Add note'}
              onClick={() =>
                runAction('Add note', () => outagesAPI.addNote(incident.id, noteText.trim()), () =>
                  setNoteText(''),
                )
              }
            >
              <MessageSquarePlus size={12} /> Add
            </button>
          </div>
        )}
      </Section>

      {/* Timeline */}
      <Section title="Timeline">
        <TimelineList events={incident.timeline} />
      </Section>
    </div>
  )
}
