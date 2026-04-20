// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: / (Dashboard)', () => {
  test('renders KPI row with no 404s and no red console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/')
    await expect(page.getByTestId('dashboard-page')).toBeVisible()
    await expect(page.getByTestId('dashboard-kpi-row')).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
