// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /simulation/ev-fast-charging (US18)', () => {
  test('renders scenario runner with Start button', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/simulation/ev-fast-charging')
    await expect(page.getByTestId('ev-fast-charging-runner')).toBeVisible()
    await expect(page.getByTestId('start-scenario')).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
