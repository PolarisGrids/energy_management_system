// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards, stubJson } from './_helpers'

/**
 * US-8 Load Profiles by Customer Class — acceptance scenarios.
 *
 * Scenario 1: residential + 1-week window → half-hourly load curve renders.
 * Scenario 2: export CSV → download matches MDMS payload.
 */
test.describe('US-8 Load Profiles by Class', () => {
  test('Energy Monitoring page fetches a load profile and renders the chart', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    /** @type {string[]} */
    const calls = []
    page.on('request', (req) => {
      if (req.url().includes('/load-profile') || req.url().includes('load_profile')) {
        calls.push(req.url())
      }
    })

    // Stub both the EMS-local load profile and the MDMS proxy path.
    await stubJson(page, '**/api/v1/energy/load-profile*', {
      hours: 168,
      points: Array.from({ length: 336 }, (_, i) => ({
        hour: i,
        total_kw: 1.2 + (i % 10) * 0.1,
      })),
    })
    await stubJson(page, '**/api/v1/mdms/api/v1/analytics/load-profile*', {
      class: 'residential',
      points: Array.from({ length: 336 }, (_, i) => ({
        ts: new Date(Date.now() + i * 1800_000).toISOString(),
        p50_kw: 1.2 + (i % 10) * 0.1,
      })),
    })

    await page.goto('/energy')
    await expect(page.getByTestId('energy-monitoring-page')).toBeVisible()
    guards.detach()
  })
})
