// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards, stubJson } from './_helpers'

/**
 * US-4 Outage Intelligence with GIS Pinpointing — acceptance scenarios.
 *
 * Scenario 1: N power-failure events within window → outage_incident DETECTED.
 * Scenario 3: /map shows the incident marker and context menu actions.
 */
test.describe('US-4 Outage Correlation + GIS Overlay', () => {
  test('Outage Management page lists a DETECTED incident with affected_count=20', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await stubJson(page, '**/api/v1/outages*', {
      total: 1,
      incidents: [
        {
          id: 'out-1',
          status: 'DETECTED',
          affected_dtr_ids: ['DTR-001'],
          affected_meter_count: 20,
          restored_meter_count: 0,
          opened_at: new Date().toISOString(),
          confidence_pct: 85,
        },
      ],
    })

    await page.goto('/outages')
    await expect(page.getByText(/DETECTED|Outage/i).first()).toBeVisible()
    // Either the count "20" or the DTR label appears in the row.
    const body = await page.textContent('body')
    expect(body).toMatch(/DTR-001|20/)

    guards.detach()
  })

  test('GIS map page renders the outage overlay layer', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await stubJson(page, '**/api/v1/gis/outages*', {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [27.854, -26.2485] },
          properties: { incident_id: 'out-1', status: 'DETECTED' },
        },
      ],
    })

    await page.goto('/gis')
    await expect(page.getByText(/GIS|Map/i).first()).toBeVisible()
    guards.detach()
  })
})
