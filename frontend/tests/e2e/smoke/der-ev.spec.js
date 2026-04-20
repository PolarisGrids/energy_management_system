// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /der/ev (EV charger fleet)', () => {
  test('renders header + KPIs with no 404 / red console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/der/ev')
    await expect(page.getByTestId('der-ev-page')).toBeVisible()
    await expect(page.getByTestId('der-ev-kpis')).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
