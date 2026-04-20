import { Outlet, useLocation } from 'react-router-dom'
import { useState } from 'react'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import UpstreamBanner from './UpstreamBanner'
import { useSSE } from '@/hooks/useSSE'
import { useNetworkSummary } from '@/hooks/useNetworkSummary'

const TITLES = {
  '/':             'Dashboard',
  '/gis':          'GIS Network Map',
  '/alarms':       'Alarm Console',
  '/der':          'DER Management',
  '/energy':       'Energy Monitoring',
  '/hes':          'HES Mirror Panel',
  '/mdms':         'MDMS Mirror Panel',
  '/simulation':   'DER Simulations',
  '/reports':      'Reports & Audit',
  '/av-control':   'Control Room A/V',
  '/app-builder':  'App Builder',
  '/showcase':     'SMOC Showcase',
  '/audit':        'Audit Log',
}

export default function AppLayout() {
  const { pathname } = useLocation()
  const [liveAlarms, setLiveAlarms] = useState([])
  const { summary, loading: summaryLoading, error: summaryError, refetch } = useNetworkSummary()

  useSSE({
    alarm: (data) => {
      setLiveAlarms((prev) => [data, ...prev].slice(0, 50))
      refetch()
    },
    network_health: (data) => {
      // Summary auto-refreshes, but we can use this for instant updates
    },
  })

  const activeAlarms = summary?.active_alarms ?? liveAlarms.length
  const title = TITLES[pathname] || 'SMOC EMS'

  return (
    <div className="flex h-screen overflow-hidden bg-[#0A0F1E]">
      {/* Ambient background blobs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/4 -left-32 w-96 h-96 rounded-full power-blur"
          style={{ background: 'radial-gradient(circle, #0A3690, transparent)' }} />
        <div className="absolute bottom-1/4 right-0 w-80 h-80 rounded-full power-blur"
          style={{ background: 'radial-gradient(circle, #02C9A8, transparent)' }} />
      </div>

      <Sidebar />

      <div className="flex flex-col flex-1 overflow-hidden relative">
        <UpstreamBanner />
        <TopBar title={title} activeAlarms={activeAlarms} networkHealth={summary} />
        <main className="flex-1 overflow-auto p-6">
          <Outlet context={{ summary, summaryLoading, summaryError, refetch, liveAlarms }} />
        </main>
      </div>
    </div>
  )
}
