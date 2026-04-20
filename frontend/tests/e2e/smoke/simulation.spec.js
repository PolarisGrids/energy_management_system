// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /simulation', () => {
  test('Simulation page renders without console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/simulation')
    await expect(page.getByText(/Simulation/i).first()).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
