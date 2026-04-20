// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /reports', () => {
  test('Reports page renders without 404s', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/reports')
    await expect(page.getByText(/Reports/i).first()).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
