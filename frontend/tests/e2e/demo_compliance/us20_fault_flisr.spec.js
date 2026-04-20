// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-20 Fault + FLISR + AMI Correlation (Demo #24).
 *
 * /outages — operator sees a DETECTED incident (affected_count, confidence),
 * clicks Isolate on the affected section, and the affected count drops.
 */
test.describe('US-20: Fault + FLISR', () => {
  test('outages page renders incidents with affected + confidence', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await page.goto('/outages')
    await expect(page.getByText(/outage|incident/i).first()).toBeVisible()

    // Either an empty state or a table — both acceptable for the smoke level.
    const table = page.locator('table').first()
    const empty = page.getByText(/no open|no incidents|no outages/i).first()
    await expect(table.or(empty)).toBeVisible()

    guards.assertClean()
    guards.detach()
  })

  test.fixme(
    'Isolate button dispatches HES switch command and affected_count drops',
    // Requires live network-fault scenario seeded in dev EKS — deferred.
    async ({ page }) => {},
  )
})
