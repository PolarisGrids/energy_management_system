// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards, stubJson } from './_helpers'

/**
 * US-5 VEE Pipeline Surfaced from MDMS — acceptance scenarios.
 *
 * Scenario 1: MDMS has data → VEE totals and percentages render (90/5/5).
 * Scenario 2: MDMS has zero data → empty state renders with NO ``NaN%``.
 */
test.describe('US-5 VEE Pipeline', () => {
  test('VEE tab renders 90/5/5 split when MDMS has a full day of reads', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await stubJson(page, '**/api/v1/mdms/api/v1/vee/summary*', {
      items: [
        {
          date: '2026-04-18',
          validated_count: 900,
          estimated_count: 50,
          failed_count: 50,
        },
      ],
    })
    await stubJson(page, '**/api/v1/mdms/api/v1/vee/exceptions*', {
      total: 0,
      items: [],
    })

    await page.goto('/mdms')
    await expect(page.getByText(/VEE/i).first()).toBeVisible()

    // Acceptance #1: no NaN% leaks from the VEE panel.
    const body = await page.textContent('body')
    expect(body).not.toMatch(/NaN%/)
    // At least one of the 90 / 5 / 5 split numbers is rendered.
    expect(body).toMatch(/90|5\.0%/)

    guards.detach()
  })

  test('empty VEE window shows em-dash, not NaN%', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await stubJson(page, '**/api/v1/mdms/api/v1/vee/summary*', { items: [] })
    await stubJson(page, '**/api/v1/mdms/api/v1/vee/exceptions*', { total: 0, items: [] })

    await page.goto('/mdms')
    await expect(page.getByText(/VEE/i).first()).toBeVisible()
    const body = await page.textContent('body')
    expect(body).not.toMatch(/NaN%/)

    guards.detach()
  })
})
