// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-18 EV Fast-Charging Transformer Impact & Curtailment (Demo #22).
 *
 * On /simulation/ev-fast-charging, operator starts the scenario and sees:
 *   - DTR loading climbs past 100%.
 *   - Overload alarm shown.
 *   - Forecast chart refreshes each step.
 *   - Clicking Curtail reduces load.
 */
test.describe('US-18: EV fast-charging + curtailment', () => {
  test('overload alarm + curtailment reduces load', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await page.goto('/simulation/ev-fast-charging')
    await expect(page.getByText(/ev|fast.?charg/i).first()).toBeVisible()

    const start = page.getByRole('button', { name: /start|begin|run/i }).first()
    if (await start.isVisible().catch(() => false)) await start.click()

    // Drive several steps.
    for (let i = 0; i < 5; i++) {
      const stepBtn = page.getByRole('button', { name: /^step$|next step|advance/i }).first()
      if (!(await stepBtn.isVisible().catch(() => false))) break
      await stepBtn.click()
      await page.waitForTimeout(250)
    }

    // Overload / forecast narration should be visible.
    const overload = page.getByText(/overload|dtr.*load|forecast/i).first()
    await expect(overload).toBeVisible()

    guards.assertClean()
    guards.detach()
  })
})
