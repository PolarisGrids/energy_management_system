// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-21 DCU Sensor Assets & Actions (Demo #25).
 *
 * /sensors — operator sees sensor list, can open a sensor and edit its
 * threshold. The edit round-trip hits the backend.
 */
test.describe('US-21: DCU sensor actions', () => {
  test('sensors page lists sensors without console errors', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    const apiHits = []
    page.on('request', (req) => {
      const url = req.url()
      if (/\/api\/v1\/sensors(\/|\?|$)/.test(url)) apiHits.push(url)
    })

    await page.goto('/sensors')
    await expect(page.getByText(/sensor/i).first()).toBeVisible()
    await page.waitForLoadState('networkidle')

    expect(apiHits.length, 'sensors page must call /api/v1/sensors').toBeGreaterThan(0)

    guards.assertClean()
    guards.detach()
  })

  test.fixme(
    'Threshold edit round-trips through EMS → HES + MDMS',
    // Requires MDMS + HES stubs in the Playwright harness; covered in the
    // pytest integration test with xfail, not a UI smoke concern.
    async ({ page }) => {},
  )
})
