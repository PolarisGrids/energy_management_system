import { useState, useEffect } from 'react'
import { ShieldAlert, CheckCircle, XCircle, DollarSign, Zap, Activity, Terminal, Send, RefreshCw } from 'lucide-react'
import { lpuAPI } from '@/services/api'

// ── KPI Card (same as MDMSMirror) ────────────────────────────────────────────
const KPI = ({ icon: Icon, label, value, color = '#02C9A8', sub }) => (
  <div className="metric-card">
    <div style={{ width: 36, height: 36, borderRadius: 10, background: `${color}22`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
      <Icon size={17} style={{ color }} />
    </div>
    <div className="text-white font-black" style={{ fontSize: 24 }}>{value}</div>
    <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 12 }}>{label}</div>
    {sub && <div style={{ color, fontSize: 11, marginTop: 3 }}>{sub}</div>}
  </div>
)

// ── Status Badge ──────────────────────────────────────────────────────────────
const StatusBadge = ({ status }) => {
  const cfg = {
    Connected:    { bg: '#02C9A822', color: '#02C9A8' },
    Disconnected: { bg: '#E94B4B22', color: '#E94B4B' },
    Limited:      { bg: '#F59E0B22', color: '#F59E0B' },
  }[status] ?? { bg: '#ABC7FF22', color: '#ABC7FF' }
  return <span style={{ background: cfg.bg, color: cfg.color, padding: '3px 10px', borderRadius: 5, fontSize: 11, fontWeight: 700 }}>{status}</span>
}

// ── Tab 1: LPU Consumers ──────────────────────────────────────────────────────
function ConsumersTab({ accounts, onCommand, cmdFeedback }) {
  const connected = accounts.filter(a => a.connection_status === 'Connected').length
  const disconnected = accounts.filter(a => a.connection_status === 'Disconnected').length
  const totalCredit = accounts.reduce((s, a) => s + (a.credit_balance_zar || 0), 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14 }}>
        <KPI icon={Zap}         label="LPU Accounts"      value={accounts.length}   color="#56CCF2" />
        <KPI icon={CheckCircle} label="Connected"          value={connected}          color="#02C9A8" />
        <KPI icon={XCircle}     label="Disconnected"       value={disconnected}       color="#E94B4B" />
        <KPI icon={DollarSign}  label="Total Credit"       value={`R ${(totalCredit/1000).toFixed(0)}k`} color="#F59E0B" />
      </div>

      {cmdFeedback && (
        <div style={{ padding: '10px 16px', borderRadius: 8, background: cmdFeedback.ok ? '#02C9A822' : '#E94B4B22', border: `1px solid ${cmdFeedback.ok ? '#02C9A844' : '#E94B4B44'}`, color: cmdFeedback.ok ? '#02C9A8' : '#E94B4B', fontSize: 13 }}>
          {cmdFeedback.msg}
        </div>
      )}

      <div className="glass-card" style={{ padding: 20 }}>
        <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>LPU Account Register</div>
        <table className="data-table" style={{ width: '100%' }}>
          <thead><tr>{['Account','Customer','Meter','Sanctioned kVA','Demand Limit','Credit (ZAR)','Tariff','Status','Actions'].map(h => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>
            {accounts.map(a => (
              <tr key={a.account_number}>
                <td style={{ color: '#56CCF2', fontFamily: 'monospace', fontSize: 12 }}>{a.account_number}</td>
                <td style={{ fontSize: 12, fontWeight: 600 }}>{a.customer_name}</td>
                <td style={{ fontFamily: 'monospace', fontSize: 11, color: '#ABC7FF' }}>{a.meter_serial}</td>
                <td style={{ color: '#02C9A8', fontWeight: 700 }}>{a.sanctioned_kva} kVA</td>
                <td style={{ color: a.demand_limit_kva ? '#F59E0B' : '#ABC7FF' }}>{a.demand_limit_kva ? `${a.demand_limit_kva} kVA` : '—'}</td>
                <td style={{ color: a.credit_balance_zar > 1000 ? '#02C9A8' : '#E94B4B', fontWeight: 700 }}>R {a.credit_balance_zar?.toLocaleString('en-ZA', { minimumFractionDigits: 2 })}</td>
                <td style={{ fontSize: 11, color: '#ABC7FF' }}>{a.tariff_name}</td>
                <td><StatusBadge status={a.connection_status} /></td>
                <td>
                  <div style={{ display: 'flex', gap: 5 }}>
                    <button className="btn-secondary" style={{ fontSize: 10, padding: '3px 8px' }} onClick={() => onCommand(a, 'DISCONNECT')} disabled={a.connection_status === 'Disconnected'}>Disc.</button>
                    <button className="btn-secondary" style={{ fontSize: 10, padding: '3px 8px', color: '#02C9A8' }} onClick={() => onCommand(a, 'RECONNECT')} disabled={a.connection_status === 'Connected'}>Recon.</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Tab 2: Tariff Structure ───────────────────────────────────────────────────
function TariffTab({ tariffs }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="glass-card" style={{ padding: 14, borderLeft: '3px solid #56CCF2' }}>
        <div style={{ color: '#56CCF2', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>Eskom LPU Tariff Components (IEC 62056 / NRS 057)</div>
        <div style={{ color: '#ABC7FF', fontSize: 12 }}>LPU tariffs include four charge components: <strong style={{ color: '#fff' }}>Energy (ToU)</strong>, <strong style={{ color: '#fff' }}>Demand (R/kVA/month)</strong>, <strong style={{ color: '#fff' }}>Network Access (R/kWh)</strong>, and <strong style={{ color: '#fff' }}>Reactive Energy (R/kVArh, PF &lt; 0.95)</strong>.</div>
      </div>
      {tariffs.map(t => (
        <div key={t.id} className="glass-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <div className="text-white font-black" style={{ fontSize: 16 }}>{t.name}</div>
              <div style={{ color: '#ABC7FF', fontSize: 12 }}>Class: {t.tariff_class} · Min: {t.applicable_min_kva} kVA · From: {t.effective_from}</div>
            </div>
            <span style={{ background: '#0A369022', color: '#56CCF2', padding: '4px 12px', borderRadius: 6, fontSize: 12, fontWeight: 700 }}>{t.tariff_class}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
            <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: 14 }}>
              <div style={{ color: '#ABC7FF', fontSize: 10, marginBottom: 6 }}>ENERGY (ToU)</div>
              {[['Off-Peak', t.energy_rates?.offpeak_per_kwh, '#02C9A8'], ['Standard', t.energy_rates?.standard_per_kwh, '#56CCF2'], ['Peak', t.energy_rates?.peak_per_kwh, '#E94B4B']].map(([l, r, c]) => (
                <div key={l} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ color: '#ABC7FF', fontSize: 11 }}>{l}</span>
                  <span style={{ color: c, fontSize: 11, fontFamily: 'monospace', fontWeight: 700 }}>{r}</span>
                </div>
              ))}
            </div>
            {[
              ['DEMAND CHARGE', t.demand_charge_per_kva, 'per kVA / month', '#F59E0B'],
              ['NETWORK ACCESS', t.network_charge_per_kwh, 'per kWh', '#56CCF2'],
              ['REACTIVE ENERGY', t.reactive_charge_per_kvarh, 'per kVArh (PF < 0.95)', '#F59E0B'],
            ].map(([label, val, unit, color]) => (
              <div key={label} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: 14 }}>
                <div style={{ color: '#ABC7FF', fontSize: 10, marginBottom: 6 }}>{label}</div>
                <div className="text-white font-black" style={{ fontSize: 20 }}>{val}</div>
                <div style={{ color, fontSize: 11 }}>{unit}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 10, padding: '8px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 6 }}>
            <span style={{ color: '#ABC7FF', fontSize: 12 }}>Monthly Service: <strong style={{ color: '#fff' }}>{t.monthly_service_charge}</strong> · Currency: <strong style={{ color: '#fff' }}>{t.currency}</strong></span>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Tab 3: SCADA Interface ────────────────────────────────────────────────────
function SCADATab({ commandLog, onRefreshLog }) {
  const [form, setForm] = useState({ mRID: `urn:uuid:edc-${Date.now()}`, domain: 'prepaid', eventOrAction: 'disconnect', meterSerial: '', limitKva: '' })
  const [sending, setSending] = useState(false)
  const [lastResp, setLastResp] = useState(null)

  const handleSend = async () => {
    setSending(true); setLastResp(null)
    try {
      const body = {
        mRID: form.mRID,
        type: { domain: form.domain, eventOrAction: form.eventOrAction, subDomain: 'LPU' },
        EndDevices: [{ mRID: form.meterSerial }],
        value: form.eventOrAction === 'setLoadLimit' && form.limitKva ? { limit_kva: parseFloat(form.limitKva) } : undefined,
      }
      const res = await lpuAPI.scadaControl(body)
      setLastResp({ ok: true, data: res.data })
      setForm(f => ({ ...f, mRID: `urn:uuid:edc-${Date.now()}` }))
      onRefreshLog()
    } catch (e) {
      setLastResp({ ok: false, data: e.response?.data ?? { detail: e.message } })
    } finally { setSending(false) }
  }

  const statusColor = s => ({ EXECUTED: '#02C9A8', ACCEPTED: '#56CCF2', PENDING: '#F59E0B' }[s] ?? '#E94B4B')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="glass-card" style={{ padding: 14, borderLeft: '3px solid #F59E0B' }}>
        <div style={{ color: '#F59E0B', fontSize: 12, fontWeight: 700, marginBottom: 2 }}>IEC 61968-9 AMI Integration Profile — EndDeviceControl</div>
        <div style={{ color: '#ABC7FF', fontSize: 11 }}>SCADA northbound interface allowing ABB Network Manager, GE ENEGIS, and Siemens SICAM to send commands to LPU metering points via CIM EndDeviceControl message pattern.</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="glass-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Terminal size={16} color="#56CCF2" />
            <span className="text-white font-semibold" style={{ fontSize: 14 }}>Send EndDeviceControl</span>
          </div>
          {[['Control mRID', 'mRID', 'text'], ['Meter Serial (EndDevice mRID)', 'meterSerial', 'text']].map(([label, key, type]) => (
            <div key={key} style={{ marginBottom: 12 }}>
              <div style={{ color: '#ABC7FF', fontSize: 11, marginBottom: 4 }}>{label}</div>
              <input type={type} value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                style={{ width: '100%', padding: '8px 10px', background: 'rgba(255,255,255,0.05)', border: '1px solid #ABC7FF22', borderRadius: 6, color: '#fff', fontSize: 12, outline: 'none' }} />
            </div>
          ))}
          {[['Domain', 'domain', ['prepaid','demandResponse','powerQuality']], ['Event / Action', 'eventOrAction', ['disconnect','reconnect','setLoadLimit','readMeter']]].map(([label, key, opts]) => (
            <div key={key} style={{ marginBottom: 12 }}>
              <div style={{ color: '#ABC7FF', fontSize: 11, marginBottom: 4 }}>{label}</div>
              <select value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                style={{ width: '100%', padding: '8px 10px', background: '#0A1628', border: '1px solid #ABC7FF22', borderRadius: 6, color: '#fff', fontSize: 12 }}>
                {opts.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          ))}
          {form.eventOrAction === 'setLoadLimit' && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ color: '#ABC7FF', fontSize: 11, marginBottom: 4 }}>Demand Limit (kVA)</div>
              <input type="number" value={form.limitKva} onChange={e => setForm(f => ({ ...f, limitKva: e.target.value }))} placeholder="e.g. 450"
                style={{ width: '100%', padding: '8px 10px', background: 'rgba(255,255,255,0.05)', border: '1px solid #ABC7FF22', borderRadius: 6, color: '#fff', fontSize: 12, outline: 'none' }} />
            </div>
          )}
          <button onClick={handleSend} disabled={sending || !form.meterSerial}
            style={{ width: '100%', padding: 10, background: 'linear-gradient(135deg,#0A3690,#56CCF2)', border: 'none', borderRadius: 8, color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, opacity: (sending || !form.meterSerial) ? 0.5 : 1 }}>
            {sending ? <><RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> Sending…</> : <><Send size={14} /> Send EndDeviceControl</>}
          </button>
          {lastResp && (
            <div style={{ marginTop: 12, padding: 12, background: lastResp.ok ? '#02C9A822' : '#E94B4B22', borderRadius: 6, border: `1px solid ${lastResp.ok ? '#02C9A844' : '#E94B4B44'}` }}>
              <div style={{ color: lastResp.ok ? '#02C9A8' : '#E94B4B', fontSize: 11, fontWeight: 700, marginBottom: 6 }}>{lastResp.ok ? 'ACCEPTED' : 'Error'}</div>
              <pre style={{ color: '#ABC7FF', fontSize: 10, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{JSON.stringify(lastResp.data, null, 2)}</pre>
            </div>
          )}
        </div>
        <div className="glass-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Activity size={16} color="#56CCF2" />
              <span className="text-white font-semibold" style={{ fontSize: 14 }}>Command Audit Log</span>
            </div>
            <button onClick={onRefreshLog} className="btn-secondary" style={{ fontSize: 11, padding: '4px 10px' }}><RefreshCw size={11} /></button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 380, overflowY: 'auto' }}>
            {commandLog.length === 0 && <div style={{ color: '#ABC7FF', fontSize: 12, textAlign: 'center', padding: 24 }}>No commands yet.</div>}
            {commandLog.map(l => (
              <div key={l.id} style={{ padding: '10px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 6, borderLeft: `3px solid ${statusColor(l.status)}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                  <span style={{ color: '#fff', fontSize: 12, fontWeight: 700 }}>{l.command_type}</span>
                  <span style={{ color: statusColor(l.status), fontSize: 10, fontWeight: 700 }}>{l.status}</span>
                </div>
                <div style={{ color: '#ABC7FF', fontSize: 10 }}>Meter: {l.meter_serial}</div>
                {l.mrrid && <div style={{ color: '#ABC7FF', fontSize: 10, fontFamily: 'monospace' }}>{l.mrrid}</div>}
                <div style={{ color: '#ABC7FF', fontSize: 10 }}>{l.operator} · {l.created_at?.slice(0, 19)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
const TABS = ['LPU Consumers', 'Tariff Structure', 'SCADA Interface']

export default function LPUPrepayment() {
  const [tab, setTab] = useState(0)
  const [accounts, setAccounts] = useState([])
  const [tariffs, setTariffs] = useState([])
  const [commandLog, setCommandLog] = useState([])
  const [loading, setLoading] = useState(true)
  const [cmdFeedback, setCmdFeedback] = useState(null)

  const loadData = async () => {
    try {
      const [accRes, tarRes, logRes] = await Promise.all([
        lpuAPI.accounts({ limit: 50 }),
        lpuAPI.tariffs(),
        lpuAPI.commandLog({ limit: 20 }),
      ])
      setAccounts(accRes.data.accounts)
      setTariffs(tarRes.data.tariffs)
      setCommandLog(logRes.data.logs)
    } catch (e) { console.error('LPU data load failed', e) }
    finally { setLoading(false) }
  }

  useEffect(() => { loadData() }, [])

  const handleCommand = async (account, cmdType) => {
    setCmdFeedback(null)
    try {
      await lpuAPI.sendCommand({ account_number: account.account_number, meter_serial: account.meter_serial, command_type: cmdType })
      setCmdFeedback({ ok: true, msg: `${cmdType} dispatched to ${account.meter_serial}` })
      loadData()
    } catch (e) {
      setCmdFeedback({ ok: false, msg: `Failed: ${e.response?.data?.detail ?? e.message}` })
    }
  }

  return (
    <div style={{ padding: '24px 28px', minHeight: '100vh', background: '#0A0F1E' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: '#F59E0B22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <ShieldAlert size={18} color="#F59E0B" />
          </div>
          <div>
            <h1 className="text-white font-black" style={{ fontSize: 22, lineHeight: 1 }}>LPU Prepayment Tool</h1>
            <p style={{ color: '#ABC7FF', fontSize: 12, marginTop: 2 }}>Large Power User Prepaid Management · IEC 61968-9 SCADA Interface · Eskom Tender E2136DXLP</p>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 22, background: 'rgba(255,255,255,0.04)', padding: 4, borderRadius: 12, width: 'fit-content' }}>
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)}
            style={{ padding: '7px 18px', borderRadius: 9, fontSize: 13, fontWeight: 600, cursor: 'pointer', border: 'none', transition: 'all 0.2s', background: tab === i ? 'linear-gradient(135deg,#0A3690,#F59E0B)' : 'transparent', color: tab === i ? '#fff' : '#ABC7FF' }}>
            {t}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', color: '#ABC7FF', padding: 60 }}>
          <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 12px' }} />
          <div>Loading LPU data…</div>
        </div>
      ) : (
        <>
          {tab === 0 && <ConsumersTab accounts={accounts} onCommand={handleCommand} cmdFeedback={cmdFeedback} />}
          {tab === 1 && <TariffTab tariffs={tariffs} />}
          {tab === 2 && <SCADATab commandLog={commandLog} onRefreshLog={loadData} />}
        </>
      )}
    </div>
  )
}
