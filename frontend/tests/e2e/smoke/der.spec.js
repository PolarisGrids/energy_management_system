// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /der', () => {
  test('DER Management page renders without console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/der')
    await expect(page.getByText(/DER Management/i)).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
