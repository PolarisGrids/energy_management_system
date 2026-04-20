// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-11 — Alert rules, virtual object groups, subscriptions (demo #10).
 *
 * Backend CRUD + quiet-hours + escalation tests live in
 * `test_us11_alerts.py`. The UI side is today served through the Alarm
 * Console route; the dedicated `AlarmRules` page is not yet registered
 * in App.jsx (tracked under W4.T17). This spec smoke-checks that the
 * alarm console at least renders, so alerts-related front-end regressions
 * surface immediately.
 */
test.describe('US-11: Alert rules & notifications', () => {
  test('alarm console renders without console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/alarms')

    // Alarm Console must always render — alarm_rule firings bubble up here.
    const pageTitle = page.getByRole('heading', { name: /alarm/i }).first()
    await expect(pageTitle).toBeVisible()

    guards.assertClean()
    guards.detach()
  })

  test.fixme(
    'rule creation wizard end-to-end',
    async () => {
      // Fixme: dedicated /alerts / /alarm-rules page not yet registered
      // in App.jsx (spec 018 W4.T17). Backend CRUD is covered; once the
      // React page lands, replace this with:
      //   1. Navigate to /alarm-rules
      //   2. Create group "Soweto-South"
      //   3. Create rule "DTR load > 80%" priority=2, channels=[SMS,email,push]
      //   4. Verify row in table
    },
  )
})
