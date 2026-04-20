// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /der/pv (PV Solar fleet)', () => {
  test('renders header and KPI row with no 404 / red console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/der/pv')
    await expect(page.getByTestId('der-pv-page')).toBeVisible()
    await expect(page.getByTestId('der-pv-kpis')).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
