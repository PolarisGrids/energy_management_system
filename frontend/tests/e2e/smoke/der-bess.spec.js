// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /der/bess (BESS fleet)', () => {
  test('renders header + KPIs with no 404 / red console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/der/bess')
    await expect(page.getByTestId('der-bess-page')).toBeVisible()
    await expect(page.getByTestId('der-bess-kpis')).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
