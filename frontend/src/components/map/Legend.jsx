// Legend + OSM attribution, part of spec 014-gis-postgis MVP.

const STATUS_COLOR = {
  online: '#02C9A8', offline: '#6B7280', tamper: '#E94B4B', disconnected: '#F97316',
}

const DER_COLOR = {
  pv: '#F59E0B', bess: '#56CCF2', ev_charger: '#02C9A8', microgrid: '#ABC7FF',
}

export default function Legend({ counts = {} }) {
  return (
    <div className="glass-card p-3 flex flex-wrap gap-4 items-center text-xs">
      <span className="text-white/40 font-bold uppercase">Legend</span>
      {Object.entries(STATUS_COLOR).map(([s, c]) => (
        <div key={s} className="flex items-center gap-2 text-white/60">
          <span className="w-3 h-3 rounded-full" style={{ background: c }} />
          {s}
        </div>
      ))}
      <div className="w-px bg-white/10 self-stretch" />
      {Object.entries(DER_COLOR).map(([t, c]) => (
        <div key={t} className="flex items-center gap-2 text-white/60">
          <span className="w-3 h-3 rounded-full border-2" style={{ borderColor: c, background: `${c}40` }} />
          {t.replace(/_/g, ' ')}
        </div>
      ))}
      <div className="w-px bg-white/10 self-stretch" />
      <div className="text-white/40">
        {Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(' · ') || 'Loading…'}
      </div>
      <div className="ml-auto text-white/30 text-[10px]">© OpenStreetMap contributors</div>
    </div>
  )
}
