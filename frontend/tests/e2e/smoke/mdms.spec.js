// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /mdms', () => {
  test('MDMS Mirror page renders without 404s', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/mdms')
    await expect(page.getByText(/MDMS Mirror/i)).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
