// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /sensors', () => {
  test('Sensor Monitoring page renders without 404s', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/sensors')
    await expect(page.getByText(/Sensor/i).first()).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
