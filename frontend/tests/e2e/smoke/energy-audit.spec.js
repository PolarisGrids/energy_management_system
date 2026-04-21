// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /reports/energy-audit', () => {
  test('Energy Audit Master page renders and fires the monthly endpoint', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    // Capture the first call to the analytics proxy so we can assert it's wired.
    const reqPromise = page.waitForRequest((r) =>
      r.url().includes('/reports/egsm-analytics/energy-audit/monthly-consumption'),
    )

    await page.goto('/reports/energy-audit')
    await expect(page.getByRole('heading', { name: /Energy Audit Master/i })).toBeVisible()
    await expect(page.getByText('Hierarchy Filter')).toBeVisible()
    await expect(page.getByText('Monthly Energy Audit')).toBeVisible()
    await expect(page.getByText('Top Performing Feeders')).toBeVisible()
    await expect(page.getByText('Worst Performing Feeders')).toBeVisible()
    await expect(page.getByText('Anomaly Feeders')).toBeVisible()
    await expect(page.getByText('All Feeders')).toBeVisible()

    const req = await reqPromise
    expect(req.url()).toMatch(/from=\d{4}-\d{2}-\d{2}/)
    expect(req.url()).toMatch(/to=\d{4}-\d{2}-\d{2}/)

    guards.assertClean()
    guards.detach()
  })
})
