// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /simulation/solar-overvoltage (US17)', () => {
  test('renders scenario runner with Start button', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/simulation/solar-overvoltage')
    await expect(page.getByTestId('solar-overvoltage-runner')).toBeVisible()
    await expect(page.getByTestId('start-scenario')).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
