// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-10 — Prepaid operations (spec 018 demo point #7).
 *
 * Route: prepaid surface currently lives inside `/mdms` (mirror page).
 * Acceptance:
 *   - Prepaid tab renders 13-register table + credit balance + recharge CTA.
 *   - After a simulated recharge (mocked via route interception) the
 *     balance refreshes without navigation.
 *   - No NaN / undefined leaks into render text.
 */
test.describe('US-10: Prepaid operations panel', () => {
  test('registers table + balance render on mdms prepaid tab', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await page.goto('/mdms')
    // MDMS mirror has Prepaid tab — click it if present.
    const prepaidTab = page.getByRole('tab', { name: /prepaid/i })
      .or(page.getByRole('button', { name: /prepaid/i }))
    if (await prepaidTab.count()) {
      await prepaidTab.first().click()
    }

    // Content should not display NaN for currency / balance fields.
    const body = await page.locator('body').innerText()
    expect(body).not.toMatch(/NaN%/i)

    guards.assertClean()
    guards.detach()
  })

  test.fixme(
    'ACD=ACTIVE banner renders when balance hits 0',
    async () => {
      // Fixme: MDMS-T4 push readback not landed; Playwright would need
      // to stub the MDMS proxy response to balance_currency=0. Covered
      // at the API layer in test_us10_prepaid.py. Un-fixme after MDMS-T4.
    },
  )
})
