// @ts-check
import { test, expect } from '@playwright/test'
import { attachConsoleGuards, DEMO_USER, DEMO_PASS } from './_helpers'

test.describe('Smoke: /login', () => {
  test('renders the sign-in form without console errors', async ({ page }) => {
    const guards = attachConsoleGuards(page)
    await page.goto('/login')
    await expect(page.getByText(/Sign in to SMOC/i)).toBeVisible()
    await expect(page.getByPlaceholder('e.g. operator')).toBeVisible()
    await expect(page.getByPlaceholder('Password')).toBeVisible()
    guards.assertClean()
    guards.detach()
  })

  test('valid demo credentials redirect to dashboard', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('e.g. operator').fill(DEMO_USER)
    await page.getByPlaceholder('Password').fill(DEMO_PASS)
    await page.getByRole('button', { name: /sign in/i }).click()
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 10_000 })
    expect(new URL(page.url()).pathname).not.toBe('/login')
  })
})
