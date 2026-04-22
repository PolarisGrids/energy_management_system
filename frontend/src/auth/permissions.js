// Frontend RBAC — spec 018 W4.T12.
// Mirrors backend/app/core/rbac.py role → permission matrix so we can
// gate menu items + routes without a round-trip. The authoritative source
// is still the backend; the set returned by /auth/me takes precedence over
// anything computed here. This file is the "offline" fallback when /me has
// not yet been fetched (e.g. the moment after login).

// Read permissions
export const P_DASHBOARD_READ = 'dashboard.read'
export const P_ALARM_READ = 'alarm.read'
export const P_METER_READ = 'meter.read'
export const P_DER_READ = 'der.read'
export const P_SENSOR_READ = 'sensor.read'
export const P_HES_READ = 'hes.read'
export const P_MDMS_READ = 'mdms.read'
export const P_OUTAGE_READ = 'outage.read'
export const P_SIMULATION_READ = 'simulation.read'
export const P_ENERGY_READ = 'energy.read'
export const P_REPORT_READ = 'report.read'
export const P_ENERGY_AUDIT_READ = 'energy_audit.read'
export const P_RELIABILITY_READ = 'reliability.read'
export const P_NTL_READ = 'ntl.read'
export const P_APP_BUILDER_READ = 'app_builder.read'
export const P_AUDIT_READ = 'audit.read'
export const P_DATA_ACCURACY_READ = 'data_accuracy.read'
export const P_DASHBOARD_LAYOUT_READ = 'dashboard_layout.read'

// Write / admin permissions
export const P_METER_COMMAND = 'meter.command'
export const P_DER_COMMAND = 'der.command'
export const P_FOTA_MANAGE = 'fota.manage'
export const P_OUTAGE_FLISR = 'outage.flisr'
export const P_OUTAGE_MANAGE = 'outage.manage'
export const P_ALARM_MANAGE = 'alarm.manage'
export const P_ALARM_CONFIGURE = 'alarm.configure'
export const P_APP_BUILDER_PUBLISH = 'app_builder.publish'
export const P_REPORT_SCHEDULE = 'report.schedule'
export const P_DASHBOARD_ADMIN = 'dashboard.admin'
export const P_DATA_ACCURACY_RECONCILE = 'data_accuracy.reconcile'
export const P_SENSOR_MANAGE = 'sensor.manage'
export const P_SIMULATION_MANAGE = 'simulation.manage'
export const P_ADMIN_ALL = 'admin.all'

const READ_SET = [
  P_DASHBOARD_READ, P_ALARM_READ, P_METER_READ, P_DER_READ, P_SENSOR_READ,
  P_HES_READ, P_MDMS_READ, P_OUTAGE_READ, P_SIMULATION_READ, P_ENERGY_READ,
  P_REPORT_READ, P_ENERGY_AUDIT_READ, P_RELIABILITY_READ, P_NTL_READ,
  P_APP_BUILDER_READ, P_AUDIT_READ, P_DATA_ACCURACY_READ, P_DASHBOARD_LAYOUT_READ,
]

export const ROLE_PERMISSIONS = {
  admin: [
    ...READ_SET,
    P_METER_COMMAND, P_DER_COMMAND, P_FOTA_MANAGE, P_OUTAGE_FLISR,
    P_OUTAGE_MANAGE, P_ALARM_MANAGE, P_ALARM_CONFIGURE,
    P_APP_BUILDER_PUBLISH, P_REPORT_SCHEDULE, P_DASHBOARD_ADMIN,
    P_DATA_ACCURACY_RECONCILE, P_SENSOR_MANAGE, P_SIMULATION_MANAGE,
    P_ADMIN_ALL,
  ],
  supervisor: [
    ...READ_SET,
    P_METER_COMMAND, P_DER_COMMAND, P_FOTA_MANAGE, P_OUTAGE_FLISR,
    P_OUTAGE_MANAGE, P_ALARM_MANAGE, P_ALARM_CONFIGURE,
    P_APP_BUILDER_PUBLISH, P_REPORT_SCHEDULE, P_DASHBOARD_ADMIN,
    P_DATA_ACCURACY_RECONCILE, P_SENSOR_MANAGE, P_SIMULATION_MANAGE,
  ],
  operator: [
    P_DASHBOARD_READ, P_ALARM_READ, P_METER_READ, P_DER_READ, P_SENSOR_READ,
    P_HES_READ, P_OUTAGE_READ, P_SIMULATION_READ, P_APP_BUILDER_READ,
    P_DASHBOARD_LAYOUT_READ, P_DATA_ACCURACY_READ,
    P_METER_COMMAND, P_DER_COMMAND, P_OUTAGE_FLISR, P_OUTAGE_MANAGE,
    P_ALARM_MANAGE, P_SIMULATION_MANAGE, P_SENSOR_MANAGE,
    P_DATA_ACCURACY_RECONCILE,
  ],
  analyst: [
    P_DASHBOARD_READ, P_ENERGY_READ, P_REPORT_READ, P_MDMS_READ, P_NTL_READ,
    P_ENERGY_AUDIT_READ, P_RELIABILITY_READ,
    P_APP_BUILDER_READ, P_AUDIT_READ, P_DASHBOARD_LAYOUT_READ,
    P_DATA_ACCURACY_READ, P_REPORT_SCHEDULE,
  ],
  viewer: [
    P_DASHBOARD_READ, P_ALARM_READ, P_REPORT_READ,
    P_ENERGY_AUDIT_READ, P_RELIABILITY_READ, P_DASHBOARD_LAYOUT_READ,
  ],
}

// Map frontend routes → required permission. Routes not listed here are
// treated as authenticated-only (any logged-in user may visit).
export const ROUTE_PERMISSIONS = {
  '/':                P_DASHBOARD_READ,
  '/alarms':          P_ALARM_READ,
  '/der':             P_DER_READ,
  '/der/pv':          P_DER_READ,
  '/der/bess':        P_DER_READ,
  '/der/ev':          P_DER_READ,
  '/der/bess/:assetId': P_DER_READ,
  '/der/ev/:assetId':   P_DER_READ,
  '/der/control':     P_DER_READ,
  '/distribution':    P_DER_READ,
  '/energy':          P_ENERGY_READ,
  '/sensors':         P_SENSOR_READ,
  '/sensors/rules':   P_ALARM_READ,
  '/sensors/alerts':  P_ALARM_READ,
  '/alerts-mgmt':                P_ALARM_READ,
  '/alerts-mgmt/groups':         P_ALARM_READ,
  '/alerts-mgmt/rules':          P_ALARM_READ,
  '/alerts-mgmt/subscriptions':  P_ALARM_READ,
  '/alerts-mgmt/alerts':         P_ALARM_READ,
  '/hes':             P_HES_READ,
  '/mdms':            P_MDMS_READ,
  '/simulation':      P_SIMULATION_READ,
  '/simulation/solar-overvoltage': P_SIMULATION_READ,
  '/simulation/ev-fast-charging':  P_SIMULATION_READ,
  '/reports':         P_REPORT_READ,
  '/reports/energy-audit':        P_ENERGY_AUDIT_READ,
  '/reports/reliability-indices': P_RELIABILITY_READ,
  '/av-control':      P_DASHBOARD_READ,
  '/app-builder':     P_APP_BUILDER_READ,
  '/showcase':        P_DASHBOARD_READ,
  '/audit':           P_AUDIT_READ,
  '/outages':         P_OUTAGE_READ,
  '/ntl':             P_NTL_READ,
  '/gis':             P_DASHBOARD_READ,
  '/data-accuracy':   P_DATA_ACCURACY_READ,
  '/admin':           P_ADMIN_ALL,
}

export function hasPermission(permissions, required) {
  if (!permissions) return false
  if (permissions.includes(P_ADMIN_ALL)) return true
  return permissions.includes(required)
}

export function permissionsForRole(role) {
  if (!role) return []
  return ROLE_PERMISSIONS[String(role).toLowerCase()] || []
}

export function canAccessRoute(permissions, path) {
  const required = ROUTE_PERMISSIONS[path]
  if (!required) return true // authenticated-only
  return hasPermission(permissions, required)
}
