// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /reports/reliability-indices', () => {
  test('Reliability Indices page renders and fires the stats endpoint', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    const reqPromise = page.waitForRequest((r) =>
      r.url().includes('/reports/egsm-analytics/reliability-indices/stats'),
    )

    await page.goto('/reports/reliability-indices')
    await expect(page.getByRole('heading', { name: /Reliability Indices/i })).toBeVisible()
    await expect(page.getByText('Hierarchy Filter')).toBeVisible()
    await expect(page.getByText('Monthly Reliability Indices')).toBeVisible()
    await expect(page.getByText('Feeder Reliability Indices Summary')).toBeVisible()
    await expect(page.getByText('Power Outages')).toBeVisible()
    // ConsumerType filter is shown for this page but not for Energy Audit.
    await expect(page.getByText('Consumer Type')).toBeVisible()

    const req = await reqPromise
    expect(req.url()).toMatch(/from=\d{4}-\d{2}-\d{2}/)

    guards.assertClean()
    guards.detach()
  })
})
