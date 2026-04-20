// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

test.describe('Smoke: /showcase', () => {
  test('SMOC Showcase page renders without 404s', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/showcase')
    await expect(page.getByText(/Showcase/i).first()).toBeVisible()
    guards.assertClean()
    guards.detach()
  })
})
