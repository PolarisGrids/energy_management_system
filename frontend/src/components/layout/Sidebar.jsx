import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Map, Bell, Zap, Activity, BarChart2,
  Settings, LogOut, Radio, Cpu, FileText, Clapperboard,
  Building2, ChevronLeft, ChevronRight, Layers, BotMessageSquare,
  Thermometer, ShieldCheck, AlertOctagon,
  ShieldAlert, AlertTriangle, Gauge,
} from 'lucide-react'
import useAuthStore from '@/stores/authStore'
import { canAccessRoute } from '@/auth/permissions'
import { useState } from 'react'

// Spec 018 W4.T12 — each entry declares its target route; visibility is
// derived from the user's permission list via canAccessRoute().
const NAV = [
  { label: 'Dashboard',         icon: LayoutDashboard,  path: '/' },
  { label: 'GIS Map',           icon: Map,              path: '/gis' },
  { label: 'Alarms',            icon: Bell,             path: '/alarms' },
  { label: 'Outages',           icon: AlertOctagon,     path: '/outages' },
  { label: 'DER Management',    icon: Zap,              path: '/der' },
  { label: 'Energy Monitoring', icon: Activity,         path: '/energy' },
  { label: 'Sensor Monitoring', icon: Thermometer,      path: '/sensors' },
  {
    label: 'Alert Management', icon: ShieldAlert,       path: '/alerts-mgmt',
    children: [
      { label: 'Groups',        icon: Layers,          path: '/alerts-mgmt/groups' },
      { label: 'Rules',         icon: Zap,             path: '/alerts-mgmt/rules' },
      { label: 'Subscriptions', icon: Bell,            path: '/alerts-mgmt/subscriptions' },
      { label: 'Alerts',        icon: AlertTriangle,   path: '/alerts-mgmt/alerts' },
    ],
  },
  { label: 'HES Mirror',        icon: Radio,            path: '/hes' },
  { label: 'MDMS Mirror',       icon: Cpu,              path: '/mdms' },
  { label: 'NTL',               icon: ShieldCheck,      path: '/ntl' },
  { label: 'Data Accuracy',     icon: ShieldCheck,      path: '/data-accuracy' },
  { label: 'Simulations',       icon: Clapperboard,     path: '/simulation' },
  { label: 'Reports',           icon: BarChart2,        path: '/reports' },
  { label: 'Control Room A/V',  icon: Layers,           path: '/av-control' },
  { label: 'App Builder',       icon: BotMessageSquare, path: '/app-builder' },
  { label: 'SMOC Showcase',     icon: Building2,        path: '/showcase' },
  { label: 'Audit Log',         icon: FileText,         path: '/audit' },
]

export default function Sidebar() {
  const { user, logout, permissions } = useAuthStore()
  const [collapsed, setCollapsed] = useState(false)

  // Spec 018 W4.T12 — hide menu items the user cannot reach. Items that are
  // merely read-restricted (e.g. /hes for analyst) disappear entirely.
  const visibleNav = NAV.filter((item) => canAccessRoute(permissions, item.path))

  return (
    <aside
      className="flex flex-col h-screen sticky top-0 transition-all duration-300 border-r shrink-0"
      style={{
        width: collapsed ? 64 : 240,
        background: 'linear-gradient(180deg, #0A1A4A 0%, #050D2A 100%)',
        borderColor: 'rgba(171,199,255,0.08)',
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b" style={{ borderColor: 'rgba(171,199,255,0.08)' }}>
        <div className="w-8 h-8 rounded-lg shrink-0 flex items-center justify-center"
          style={{ background: 'linear-gradient(45deg, #11ABBE, #3C63FF)' }}>
          <Zap size={16} className="text-white" />
        </div>
        {!collapsed && (
          <div>
            <div className="font-black text-white text-sm leading-tight">POLARIS</div>
            <div className="text-sky-blue font-medium" style={{ fontSize: 10 }}>SMOC EMS</div>
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="ml-auto text-accent-blue hover:text-white transition-colors"
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 flex flex-col gap-0.5">
        {visibleNav.map(({ label, icon: Icon, path }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
            title={collapsed ? label : undefined}
          >
            <Icon size={16} className="shrink-0" />
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* User */}
      <div className="p-3 border-t" style={{ borderColor: 'rgba(171,199,255,0.08)' }}>
        {!collapsed && (
          <div className="px-2 py-2 mb-2">
            <div className="text-white font-bold text-sm truncate">{user?.full_name}</div>
            <div className="text-sky-blue capitalize" style={{ fontSize: 11 }}>{user?.role}</div>
          </div>
        )}
        <button
          onClick={logout}
          className="nav-item w-full hover:text-status-critical"
          title={collapsed ? 'Logout' : undefined}
        >
          <LogOut size={16} className="shrink-0" />
          {!collapsed && <span>Logout</span>}
        </button>
      </div>
    </aside>
  )
}
