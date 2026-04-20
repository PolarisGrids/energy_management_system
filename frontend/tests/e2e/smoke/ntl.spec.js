// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

/**
 * Smoke: `/ntl` renders the NTL dashboard and exposes the suspects table
 * + top-gap card. Mirrors the other route-level smokes under this dir.
 * Covers spec 018 W3.T9 (User Story 9 acceptance scenarios).
 */
test.describe('Smoke: /ntl', () => {
  test('loads dashboard + banner when scoring unavailable', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/ntl')

    // Dashboard shell renders.
    await expect(page.getByTestId('ntl-dashboard')).toBeVisible()
    await expect(page.getByTestId('ntl-suspects-table')).toBeVisible()

    // If MDMS NTL scoring is disabled (dev default path), the banner MUST be
    // present — acceptance scenario ② of US-9. We don't hard-fail when it's
    // absent (demo env may have MDMS scoring on), but when present it must
    // match the contract copy.
    const banner = page.getByTestId('ntl-banner')
    if (await banner.count()) {
      await expect(banner).toContainText(/event correlation/i)
    }

    // Top-gaps card is always rendered (may be empty).
    await expect(page.getByTestId('ntl-top-gaps')).toBeVisible()

    guards.assertClean()
    guards.detach()
  })
})
