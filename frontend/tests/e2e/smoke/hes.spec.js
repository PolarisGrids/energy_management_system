// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /hes', () => {
  test('HES Mirror page renders without 404s', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/hes')
    await expect(page.getByText(/HES Mirror/i)).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
