// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /energy', () => {
  test('Energy Monitoring page renders loading/error-safe', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/energy')
    await expect(page.getByTestId('energy-monitoring-page')).toBeVisible()
    await expect(page.getByRole('heading', { name: /Energy Monitoring/i })).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
