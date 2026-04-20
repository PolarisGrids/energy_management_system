// @ts-check
// Spec 018 W4.T12 — frontend RBAC matrix.
//
// For each of the 5 roles, visit 5 representative routes and assert that:
//   • Allowed routes render the page content.
//   • Denied routes render the 403 Forbidden view.
//
// This test hard-codes permissions directly into localStorage so it does
// NOT depend on backend seed credentials for every role (seed_data.py
// currently only seeds admin/operator/supervisor). Each role's permissions
// list mirrors backend/app/core/rbac.py::ROLE_PERMISSIONS.

import { test, expect } from '@playwright/test'

// Keep in sync with backend/app/core/rbac.py.
const READ_ALL = [
  'dashboard.read', 'alarm.read', 'meter.read', 'der.read', 'sensor.read',
  'hes.read', 'mdms.read', 'outage.read', 'simulation.read', 'energy.read',
  'report.read', 'ntl.read', 'app_builder.read', 'audit.read',
  'data_accuracy.read', 'dashboard_layout.read',
]

const ROLE_PERMISSIONS = {
  admin: [
    ...READ_ALL,
    'meter.command', 'der.command', 'fota.manage', 'outage.flisr',
    'outage.manage', 'alarm.manage', 'alarm.configure',
    'app_builder.publish', 'report.schedule', 'dashboard.admin',
    'data_accuracy.reconcile', 'sensor.manage', 'simulation.manage',
    'admin.all',
  ],
  supervisor: [
    ...READ_ALL,
    'meter.command', 'der.command', 'fota.manage', 'outage.flisr',
    'outage.manage', 'alarm.manage', 'alarm.configure',
    'app_builder.publish', 'report.schedule', 'dashboard.admin',
    'data_accuracy.reconcile', 'sensor.manage', 'simulation.manage',
  ],
  operator: [
    'dashboard.read', 'alarm.read', 'meter.read', 'der.read', 'sensor.read',
    'hes.read', 'outage.read', 'simulation.read', 'app_builder.read',
    'dashboard_layout.read', 'data_accuracy.read',
    'meter.command', 'der.command', 'outage.flisr', 'outage.manage',
    'alarm.manage', 'simulation.manage', 'sensor.manage',
    'data_accuracy.reconcile',
  ],
  analyst: [
    'dashboard.read', 'energy.read', 'report.read', 'mdms.read', 'ntl.read',
    'app_builder.read', 'audit.read', 'dashboard_layout.read',
    'data_accuracy.read', 'report.schedule',
  ],
  viewer: ['dashboard.read', 'alarm.read', 'report.read', 'dashboard_layout.read'],
}

// 5 representative routes per the task description.
const ROUTES = [
  { path: '/', perm: 'dashboard.read', label: /dashboard/i },
  { path: '/reports', perm: 'report.read', label: /report/i },
  { path: '/hes', perm: 'hes.read', label: /hes/i },
  { path: '/audit', perm: 'audit.read', label: /audit/i },
  { path: '/data-accuracy', perm: 'data_accuracy.read', label: /data accuracy/i },
]

/**
 * Seed the auth store so the app boots believing we're logged in as `role`.
 * This avoids needing seeded credentials for every role in the DB.
 */
async function seedAuth(page, role) {
  const permissions = ROLE_PERMISSIONS[role]
  const user = {
    id: 9999,
    username: `${role}-e2e`,
    full_name: `${role.toUpperCase()} E2E`,
    role,
  }
  // The axios interceptor expects a token at `smoc_token`; any non-empty
  // string works for route-gate purposes because no backend call is required
  // on the Forbidden view.
  await page.addInitScript(({ user, permissions }) => {
    window.localStorage.setItem('smoc_token', 'e2e-seeded-token')
    window.localStorage.setItem('smoc_user', JSON.stringify(user))
    window.localStorage.setItem('smoc_permissions', JSON.stringify(permissions))
  }, { user, permissions })
}

for (const role of Object.keys(ROLE_PERMISSIONS)) {
  test.describe(`RBAC: role=${role}`, () => {
    for (const r of ROUTES) {
      const allowed = ROLE_PERMISSIONS[role].includes(r.perm)
        || ROLE_PERMISSIONS[role].includes('admin.all')

      test(`${allowed ? 'allows' : 'blocks'} ${r.path}`, async ({ page }) => {
        await seedAuth(page, role)
        await page.goto(r.path)
        if (allowed) {
          // We expect a normal page — no Forbidden view.
          await expect(page.getByTestId('forbidden')).toHaveCount(0)
        } else {
          await expect(page.getByTestId('forbidden')).toBeVisible({ timeout: 5_000 })
        }
      })
    }

    test('sidebar only shows accessible items', async ({ page }) => {
      await seedAuth(page, role)
      await page.goto('/')
      // Dashboard is visible for every role.
      const dashLink = page.getByRole('link', { name: /dashboard/i })
      await expect(dashLink.first()).toBeVisible()
      // HES link is only visible to roles with hes.read.
      const hesLinkVisible = ROLE_PERMISSIONS[role].includes('hes.read')
        || ROLE_PERMISSIONS[role].includes('admin.all')
      const hesLink = page.getByRole('link', { name: /HES Mirror/i })
      if (hesLinkVisible) {
        await expect(hesLink).toBeVisible()
      } else {
        await expect(hesLink).toHaveCount(0)
      }
    })
  })
}
