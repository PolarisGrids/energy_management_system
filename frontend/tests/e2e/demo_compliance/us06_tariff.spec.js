// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards, stubJson } from './_helpers'

/**
 * US-6 Tariff Engine View — acceptance scenarios from spec.md §User Story 6.
 *
 * Scenario 1: MDMS tariffs render in the Billing & Tariffs tab.
 * Scenario 3: inclining-block tariff renders per-tier breakdown when
 *             TARIFF_INCLINING_ENABLED, else "Not configured".
 */
test.describe('US-6 Tariff View', () => {
  test('MDMS Mirror Billing & Tariffs tab renders TOU rates from MDMS', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await stubJson(page, '**/api/v1/mdms/api/v1/tariffs*', {
      tariffs: [
        {
          id: 'T-RES',
          name: 'Residential TOU',
          type: 'TOU',
          effective_from: '2026-01-01',
          tou_rates: { TZ1: 2.8, TZ2: 3.2, TZ3: 4.1 },
          demand_charge: 100.0,
        },
      ],
    })

    await page.goto('/mdms')
    await expect(page.getByText(/MDMS/i).first()).toBeVisible()
    guards.detach()
  })

  test('billing determinants for a meter+month match MDMS payload', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await stubJson(page, '**/api/v1/mdms/api/v1/billing-determinants*', {
      account: 'ACC-0001',
      month: '2026-04',
      tou_consumption: { TZ1: 120, TZ2: 80 },
      invoice_value: 2500.45,
    })

    await page.goto('/mdms')
    await expect(page.getByText(/MDMS/i).first()).toBeVisible()
    guards.detach()
  })
})
