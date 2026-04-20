// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /gis', () => {
  test('loads without 404 or red console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/gis')
    // The topbar title updates when the GIS route is active.
    await expect(page.getByText(/GIS Network Map/i)).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
