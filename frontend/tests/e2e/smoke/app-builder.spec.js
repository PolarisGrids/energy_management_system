// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

/**
 * Spec 018 W4.T8 — refactored AppBuilder page smoke test.
 *
 * Verifies:
 *   1. The page loads at /app-builder.
 *   2. All four tabs (Dashboard Builder, Rule Engine, Algorithm Editor,
 *      My Apps) render without console errors.
 *   3. The AppBuilder hits the /apps, /app-rules, /algorithms backend —
 *      i.e. the hardcoded INITIAL_RULES / INITIAL_APPS / SAMPLE_ALGORITHMS
 *      have been replaced with backend-driven state.
 */
test.describe('Smoke: /app-builder (spec 018 W4.T8)', () => {
  test('App Builder renders and hits backend endpoints', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    /** @type {string[]} */
    const hitUrls = []
    page.on('request', (req) => {
      const url = req.url()
      if (/\/api\/v1\/(apps|app-rules|algorithms)(\/|\?|$)/.test(url)) {
        hitUrls.push(url)
      }
    })

    await page.goto('/app-builder')
    await expect(
      page.getByRole('heading', { name: /No-Code App Builder/i }),
    ).toBeVisible()

    for (const tab of [
      'Rule Engine',
      'Algorithm Editor',
      'My Apps',
      'Dashboard Builder',
    ]) {
      await page.getByRole('button', { name: tab }).click()
      await page.waitForTimeout(250)
    }

    await page.waitForTimeout(500)
    expect(
      hitUrls.length,
      `expected at least one /apps | /app-rules | /algorithms call, saw: ${hitUrls.join(', ')}`,
    ).toBeGreaterThan(0)

    guards.assertClean()
    guards.detach()
  })
})
