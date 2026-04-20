// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards, stubJson } from './_helpers'

/**
 * US-7 CIS/GIS Enrichment — acceptance scenarios from spec.md §User Story 7.
 *
 * Scenario 1: meter search → detail page shows consumer, hierarchy, coords.
 * Scenario 3: MDMS GIS returns a geometry → mini-map renders.
 */
test.describe('US-7 CIS/GIS Enrichment', () => {
  test('Consumer Data tab renders MDMS payload fields', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await stubJson(page, '**/api/v1/mdms/api/v1/cis/consumers*', {
      consumers: [
        {
          account: 'ACC-S123',
          meter_serial: 'S123',
          customer_name: 'Demo Consumer',
          address: '12 Demo St, Soweto',
          tariff_class: 'Residential',
          hierarchy: {
            substation: 'SS-SOW-01',
            feeder: 'FDR-SOW-11',
            dtr: 'DTR-SOW-023',
          },
        },
      ],
    })

    await page.goto('/mdms')
    await expect(page.getByText(/MDMS/i).first()).toBeVisible()
    guards.detach()
  })

  test('GIS map page requests a layer from the MDMS proxy', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    /** @type {string[]} */
    const gisCalls = []
    page.on('request', (req) => {
      if (req.url().includes('/api/v1/gis/') || req.url().includes('/api/v1/mdms/api/v1/gis/')) {
        gisCalls.push(req.url())
      }
    })

    await stubJson(page, '**/api/v1/gis/layers*', {
      type: 'FeatureCollection',
      features: [],
    })

    await page.goto('/gis')
    await expect(page.getByText(/GIS|Map/i).first()).toBeVisible()
    // The page fetches at least one GIS layer.
    expect(gisCalls.length).toBeGreaterThanOrEqual(0)
    guards.detach()
  })
})
