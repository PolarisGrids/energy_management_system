// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /av-control', () => {
  test('Control Room A/V page renders without 404s', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/av-control')
    await expect(page.getByText(/Control Room|A\/V Control/i).first()).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
