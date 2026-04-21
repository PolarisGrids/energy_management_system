import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import useAuthStore from '@/stores/authStore'
import AppLayout from '@/components/layout/AppLayout'
import { ToastProvider } from '@/components/ui/Toast'
import ProtectedRoute from '@/auth/ProtectedRoute'
import {
  P_DASHBOARD_READ, P_ALARM_READ, P_DER_READ, P_ENERGY_READ, P_SENSOR_READ,
  P_HES_READ, P_MDMS_READ, P_SIMULATION_READ, P_REPORT_READ,
  P_APP_BUILDER_READ, P_AUDIT_READ, P_OUTAGE_READ, P_NTL_READ,
  P_DATA_ACCURACY_READ, P_ENERGY_AUDIT_READ, P_RELIABILITY_READ,
} from '@/auth/permissions'
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import GISMap from '@/pages/GISMap'
import AlarmConsole from '@/pages/AlarmConsole'
import SimulationPage from '@/pages/SimulationPage'
import DERManagement from '@/pages/DERManagement'
import EnergyMonitoring from '@/pages/EnergyMonitoring'
import HESMirror from '@/pages/HESMirror'
import MDMSMirror from '@/pages/MDMSMirror'
import Reports from '@/pages/Reports'
import EnergyAuditMaster from '@/pages/EnergyAuditMaster'
import ReliabilityIndices from '@/pages/ReliabilityIndices'
import AVControl from '@/pages/AVControl'
import AppBuilder from '@/pages/AppBuilder'
import SMOCShowcase from '@/pages/SMOCShowcase'
import AuditLog from '@/pages/AuditLog'
import SensorMonitoring from '@/pages/SensorMonitoring'
// LV transformer monitoring — rule builder + alerts view scoped to DTR meters
import LVAlertRules from '@/pages/LVAlertRules'
import LVAlerts from '@/pages/LVAlerts'
import OutageManagement from '@/pages/OutageManagement'
import OutageDetail from '@/pages/OutageDetail'
import NTL from '@/pages/NTL'
// Alert Management (2026-04-21) — virtual groups + rules + subscriptions + alerts
import AlertManagement from '@/pages/AlertManagement'
// Spec 018 W3.T11 — DER native dashboards + distribution room.
import DERPv from '@/pages/DERPv'
import DERPvDetail from '@/pages/DERPvDetail'
import DERBess from '@/pages/DERBess'
import DERBessDetail from '@/pages/DERBessDetail'
import DEREv from '@/pages/DEREv'
import DEREvDetail from '@/pages/DEREvDetail'
import DistributionRoom from '@/pages/DistributionRoom'
// Spec 018 W3.T15 — solar-overvoltage scenario round-trip runner.
import SolarOvervoltageRunner from '@/pages/SolarOvervoltageRunner'
// Spec 018 W3.T16 — EV fast-charging scenario round-trip runner.
import EvFastChargingRunner from '@/pages/EvFastChargingRunner'
// Spec 018 W4.T14 — Data Accuracy console.
import DataAccuracy from '@/pages/DataAccuracy'

// Backwards-compatible alias used by legacy code paths.
function PrivateRoute({ children }) {
  const { token } = useAuthStore()
  return token ? children : <Navigate to="/login" replace />
}

function guard(perm, el) {
  return <ProtectedRoute requiredPermission={perm}>{el}</ProtectedRoute>
}

export default function App() {
  const { token, refreshMe } = useAuthStore()
  useEffect(() => {
    // Spec 018 W4.T12 — on reload, refresh permissions from /auth/me so an
    // updated role matrix takes effect without re-login.
    if (token) refreshMe()
  }, [token, refreshMe])

  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<PrivateRoute><AppLayout /></PrivateRoute>}>
            <Route index                                 element={guard(P_DASHBOARD_READ,     <Dashboard />)} />
            <Route path="gis"                            element={guard(P_DASHBOARD_READ,     <GISMap />)} />
            <Route path="alarms"                         element={guard(P_ALARM_READ,         <AlarmConsole />)} />
            <Route path="der"                            element={guard(P_DER_READ,           <DERManagement />)} />
            <Route path="der/pv"                         element={guard(P_DER_READ,           <DERPv />)} />
            <Route path="der/pv/:assetId"                element={guard(P_DER_READ,           <DERPvDetail />)} />
            <Route path="der/bess"                       element={guard(P_DER_READ,           <DERBess />)} />
            <Route path="der/bess/:assetId"              element={guard(P_DER_READ,           <DERBessDetail />)} />
            <Route path="der/ev"                         element={guard(P_DER_READ,           <DEREv />)} />
            <Route path="der/ev/:assetId"                element={guard(P_DER_READ,           <DEREvDetail />)} />
            <Route path="distribution"                   element={guard(P_DER_READ,           <DistributionRoom />)} />
            <Route path="energy"                         element={guard(P_ENERGY_READ,        <EnergyMonitoring />)} />
            <Route path="hes"                            element={guard(P_HES_READ,           <HESMirror />)} />
            <Route path="mdms"                           element={guard(P_MDMS_READ,          <MDMSMirror />)} />
            <Route path="simulation"                     element={guard(P_SIMULATION_READ,    <SimulationPage />)} />
            <Route path="simulation/solar-overvoltage"   element={guard(P_SIMULATION_READ,    <SolarOvervoltageRunner />)} />
            <Route path="simulation/ev-fast-charging"    element={guard(P_SIMULATION_READ,    <EvFastChargingRunner />)} />
            <Route path="reports"                        element={guard(P_REPORT_READ,        <Reports />)} />
            <Route path="reports/energy-audit"           element={guard(P_ENERGY_AUDIT_READ,  <EnergyAuditMaster />)} />
            <Route path="reports/reliability-indices"    element={guard(P_RELIABILITY_READ,   <ReliabilityIndices />)} />
            <Route path="av-control"                     element={guard(P_DASHBOARD_READ,     <AVControl />)} />
            <Route path="app-builder"                    element={guard(P_APP_BUILDER_READ,   <AppBuilder />)} />
            <Route path="showcase"                       element={guard(P_DASHBOARD_READ,     <SMOCShowcase />)} />
            <Route path="sensors"                        element={guard(P_SENSOR_READ,        <SensorMonitoring />)} />
            <Route path="sensors/rules"                  element={guard(P_ALARM_READ,         <LVAlertRules />)} />
            <Route path="sensors/alerts"                 element={guard(P_ALARM_READ,         <LVAlerts />)} />
            <Route path="alerts-mgmt"                    element={guard(P_ALARM_READ,         <AlertManagement />)} />
            <Route path="alerts-mgmt/:tab"               element={guard(P_ALARM_READ,         <AlertManagement />)} />
            <Route path="audit"                          element={guard(P_AUDIT_READ,         <AuditLog />)} />
            <Route path="outages"                        element={guard(P_OUTAGE_READ,        <OutageManagement />)} />
            <Route path="outages/:id"                    element={guard(P_OUTAGE_READ,        <OutageDetail />)} />
            <Route path="ntl"                            element={guard(P_NTL_READ,           <NTL />)} />
            <Route path="data-accuracy"                  element={guard(P_DATA_ACCURACY_READ, <DataAccuracy />)} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  )
}
