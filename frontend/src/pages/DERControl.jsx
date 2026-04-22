// DER Control — Demand Response & Load Control module.
// Embeds the standalone HTML dashboard (/der-control.html) served from public/.
export default function DERControl() {
  return (
    <div className="h-full w-full -m-6">
      <iframe
        src="/der-control.html"
        title="DER Control — Demand Response"
        className="w-full h-full border-0 block"
        style={{ height: 'calc(100vh - 112px)', background: '#0a0e14' }}
      />
    </div>
  )
}
