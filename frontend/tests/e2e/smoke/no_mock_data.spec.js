// @ts-check
//
// Automated "no-mock" gate (spec 018 Wave 5).
//
// Loads the Energy, Reports, and DER pages after login and asserts that
// none of the tokens we removed in the audit (mock-data-audit.md §7)
// appear in the rendered DOM. If any resurface, this fails loudly.
//
// It also verifies that the shared DeviceSearch + DateRangePicker
// controls are rendered on the Consumption tab of EnergyMonitoring and
// on the Reports page's Consumption tab.
//
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

// Tokens that must NOT appear anywhere in the rendered page HTML on the
// pages we cleaned up. Keep this list literal — if a token ever legitimately
// belongs in production copy, remove it from here instead of softening
// the match.
const FORBIDDEN_TOKENS = [
  'Polaris Grids',
  'Eskom Dist',
  'City Power',
  'Feeder A',
  'Feeder B',
  'Feeder C',
  'Feeder D',
  'Feeder E',
  'F01 - Soweto Main',
  'F02 - Alexandra A',
  'F03 - Industria',
  'F04 - Tembisa',
  'F05 - Diepsloot',
  'Filters are advisory — simulation data',
]

// Numeric tokens that were hardcoded as KPI / bar-chart fallbacks.
// Wrapped in word boundaries at call-time to avoid accidental substring
// hits against unrelated numbers.
const FORBIDDEN_NUMBERS = ['8200', '1150', '4820', '5130', '4970', '5440', '5080', '5320', '1842', '1374', '1960']

async function assertNoForbidden(page, route) {
  // Wait until the SPA settles before snapshotting the DOM — otherwise
  // `page.content()` can race with in-flight hydration and throw
  // "Unable to retrieve content because the page is navigating".
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})
  const html = await page.content()
  for (const tok of FORBIDDEN_TOKENS) {
    expect(html, `forbidden token "${tok}" found on ${route}`).not.toContain(tok)
  }
  for (const num of FORBIDDEN_NUMBERS) {
    const re = new RegExp(`\\b${num}\\b`)
    expect(html, `forbidden number ${num} found on ${route}`).not.toMatch(re)
  }
}

test.describe('No-mock gate (spec 018 Wave 5)', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('EnergyMonitoring renders no hardcoded demo tokens', async ({ page }) => {
    const guards = attachConsoleGuards(page)
    await page.goto('/energy')
    await expect(page.getByTestId('energy-monitoring-page')).toBeVisible()

    // Switch to Consumption tab — this is where DeviceSearch + DateRangePicker live.
    await page.getByRole('button', { name: /Consumption Analysis/i }).click()
    await expect(page.getByTestId('device-search')).toBeVisible()
    await expect(page.getByTestId('date-range-picker')).toBeVisible()

    await assertNoForbidden(page, '/energy')
    guards.assertClean()
    guards.detach()
  })

  test('Reports renders no hardcoded demo tokens', async ({ page }) => {
    const guards = attachConsoleGuards(page)
    await page.goto('/reports')
    // Reports page shows Consumption Reports tab by default.
    await expect(page.getByTestId('date-range-picker')).toBeVisible()

    await assertNoForbidden(page, '/reports')
    guards.assertClean()
    guards.detach()
  })

  test('DER Management (EV tab) renders no hardcoded port sessions', async ({ page }) => {
    const guards = attachConsoleGuards(page)
    await page.goto('/der')
    // Generic assertion — we are just checking no forbidden demo tokens
    // are rendered. The EV tab is a sub-view but the parent page still
    // mounts the DER asset group cards.
    await assertNoForbidden(page, '/der')
    guards.assertClean()
    guards.detach()
  })

  test('DEREv fees are omitted when no MDMS tariff is configured', async ({ page }) => {
    const guards = attachConsoleGuards(page)
    await page.goto('/der/ev')
    // Either a real rate is present (no banner) or the banner is shown and
    // fees render em-dash. Either way no "R 8" hardcoded fallback is
    // accepted.
    const html = await page.content()
    // Explicit check for the old narrative.
    expect(html, 'DEREv still shows R8/kWh hardcoded').not.toMatch(/R\s*8\s*(\/|per)\s*kWh/i)
    guards.assertClean()
    guards.detach()
  })

  test('AuditLog default date range is not stale hardcoded 2026-04-02', async ({ page }) => {
    const guards = attachConsoleGuards(page)
    await page.goto('/audit')
    // The from/to inputs are <input type="date">; grab their values.
    const dateInputs = page.locator('input[type="date"]')
    await expect(dateInputs.first()).toBeVisible()
    const values = await dateInputs.evaluateAll(
      /** @param {HTMLInputElement[]} els */
      (els) => els.map((e) => e.value),
    )
    for (const v of values) {
      expect(v, 'AuditLog default date still hardcoded to 2026-04-02').not.toBe('2026-04-02')
    }
    guards.assertClean()
    guards.detach()
  })
})
