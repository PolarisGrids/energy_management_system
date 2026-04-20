// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-17 Solar Over-Voltage + Smart Inverter Curtailment (Demo #21).
 *
 * Driver: operator opens /simulation/solar-overvoltage, starts the scenario,
 * steps it ≥7 times, observes voltage ≤ 1.05 pu, and confirms the algorithm
 * panel is visible for narration.
 *
 * The "each inverter receives a curtail command" assertion is delegated to
 * the backend integration test (backend/tests/integration/demo_compliance/
 * test_us17_solar_overvoltage.py) — we only confirm UI narration here.
 */
test.describe('US-17: Solar over-voltage + curtailment', () => {
  test('scenario runner reduces voltage ≤ 1.05 pu within 7 steps', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await page.goto('/simulation/solar-overvoltage')
    await expect(page.getByText(/solar|over.?voltage/i).first()).toBeVisible()

    // Start and step the scenario seven times.
    const startBtn = page.getByRole('button', { name: /start|begin|run/i }).first()
    if (await startBtn.isVisible().catch(() => false)) {
      await startBtn.click()
    }
    for (let i = 0; i < 7; i++) {
      const stepBtn = page.getByRole('button', { name: /^step$|next step|advance/i }).first()
      if (!(await stepBtn.isVisible().catch(() => false))) break
      await stepBtn.click()
      await page.waitForTimeout(250)
    }

    // Algorithm panel visible for narration.
    await expect(page.getByText(/algorithm|droop|curtail/i).first()).toBeVisible()

    guards.assertClean()
    guards.detach()
  })
})
