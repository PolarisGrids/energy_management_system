import { Bell, Wifi, Clock } from 'lucide-react'
import { useState, useEffect } from 'react'
import useAuthStore from '@/stores/authStore'

export default function TopBar({ title, activeAlarms = 0, networkHealth = null }) {
  const { user } = useAuthStore()
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const commRate = networkHealth?.comm_success_rate ?? 0

  return (
    <header
      className="flex items-center justify-between px-6 py-3 border-b shrink-0"
      style={{
        background: 'rgba(10,15,30,0.8)',
        backdropFilter: 'blur(20px)',
        borderColor: 'rgba(171,199,255,0.08)',
        minHeight: 56,
      }}
    >
      <h1 className="font-black text-white" style={{ fontSize: 20 }}>{title}</h1>

      <div className="flex items-center gap-5">
        {/* Comm rate */}
        <div className="flex items-center gap-2 text-sm">
          <Wifi size={14} className={commRate >= 95 ? 'text-energy-green' : commRate >= 85 ? 'text-status-medium' : 'text-status-critical'} />
          <span className="text-accent-blue" style={{ fontSize: 12 }}>
            {commRate}% comm
          </span>
        </div>

        {/* Active alarms */}
        <div className="flex items-center gap-2">
          <Bell size={14} className={activeAlarms > 0 ? 'text-status-critical' : 'text-accent-blue'} />
          {activeAlarms > 0 && (
            <span className="badge-critical">{activeAlarms}</span>
          )}
        </div>

        {/* Clock */}
        <div className="flex items-center gap-2 text-accent-blue" style={{ fontSize: 12 }}>
          <Clock size={12} />
          <span className="font-mono">
            {time.toLocaleTimeString('en-ZA', { hour12: false })}
          </span>
          <span className="text-white/40">SAST</span>
        </div>
      </div>
    </header>
  )
}
