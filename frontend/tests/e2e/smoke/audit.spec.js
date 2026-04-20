// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /audit', () => {
  test('Audit Log page renders without 404s', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/audit')
    await expect(page.getByText(/Audit/i).first()).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
