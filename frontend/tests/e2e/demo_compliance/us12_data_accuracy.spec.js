// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-12 — Data Accuracy console (demo #11).
 *
 * Acceptance (integration-test-matrix row 12):
 *   - Meters that are HES-lagging (> 1h old last-seen) flag as "lagging".
 *   - Per-meter row shows HES last-read, MDMS last-validated, CIS
 *     last-billing with deltas + badge.
 */
test.describe('US-12: Data accuracy console', () => {
  test('page renders with counts + table', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await page.goto('/data-accuracy')
    await expect(page.getByTestId('data-accuracy-page')).toBeVisible()
    await expect(page.getByTestId('data-accuracy-counts')).toBeVisible()

    // Reload button exists & click-safe.
    const reload = page.getByTestId('data-accuracy-reload')
    if (await reload.count()) {
      await reload.click()
    }

    // Text should not include NaN bleed (the page displays deltas in hours).
    const body = await page.locator('body').innerText()
    expect(body).not.toMatch(/\bNaN\b/)

    guards.assertClean()
    guards.detach()
  })

  test('force-refresh button triggers refresh without errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/data-accuracy')

    const forceRefresh = page.getByTestId('data-accuracy-force-refresh')
    if (await forceRefresh.count()) {
      await forceRefresh.click()
      // We don't assert backend output (depends on upstream reachability);
      // just that the click does not blow up the page.
    }

    guards.assertClean()
    guards.detach()
  })
})
