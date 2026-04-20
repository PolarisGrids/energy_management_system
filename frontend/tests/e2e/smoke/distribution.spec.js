// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /distribution (Distribution-room sensors)', () => {
  test('renders header + room cards grid with no 404 / red console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/distribution')
    await expect(page.getByTestId('distribution-page')).toBeVisible()
    await expect(page.getByTestId('distribution-rooms')).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
