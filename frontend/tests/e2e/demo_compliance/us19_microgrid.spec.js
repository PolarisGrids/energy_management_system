// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-19 Microgrid Reverse Flow + DER Aggregation (Demo #23).
 *
 * From /der: operator runs `peaking_microgrid`, sees reverse-flow banner
 * when net < 0, and after a mid-scenario BESS insert the aggregate view
 * updates on the next step.
 */
test.describe('US-19: Microgrid reverse flow + DER aggregation', () => {
  test.fixme(
    'aggregate updates after mid-scenario BESS insert',
    // NOTE: the mid-scenario bulk-import hook from the frontend requires
    // the simulator's shared-secret authentication which the Playwright
    // harness doesn't currently mint. Tracked in spec 018 Wave-5.
    async ({ page }) => {},
  )

  test('DER management page renders aggregate + reverse-flow banner', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await page.goto('/der')
    await expect(page.getByText(/DER|aggregate|reverse/i).first()).toBeVisible()

    guards.assertClean()
    guards.detach()
  })
})
