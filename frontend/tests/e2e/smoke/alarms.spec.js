// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /alarms', () => {
  test('Alarm Console renders filter controls cleanly', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/alarms')
    await expect(page.getByText(/Alarm Console/i)).toBeVisible()
    // The filter strip contains All Status + All Severity selects.
    await expect(page.getByRole('combobox').first()).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
