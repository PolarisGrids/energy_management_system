// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-15 — DER native dashboards (PV / BESS / EV / Distribution). Demo #15-18.
 *
 * Each sub-page uses the der_telemetry endpoint under the hood. The shell
 * components expose grid + KPI test-ids which we smoke here to catch
 * regressions.
 */
test.describe('US-15: DER dashboards', () => {
  test('PV dashboard renders KPIs + grid', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/der/pv')

    await expect(page.getByTestId('der-pv-page')).toBeVisible()
    await expect(page.getByTestId('der-pv-kpis')).toBeVisible()
    await expect(page.getByTestId('der-pv-grid')).toBeVisible()

    const body = await page.locator('body').innerText()
    expect(body).not.toMatch(/\bNaN\b/)

    guards.assertClean()
    guards.detach()
  })

  test('BESS dashboard renders SoC + cycles surfaces', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/der/bess')

    await expect(page.getByTestId('der-bess-page')).toBeVisible()
    await expect(page.getByTestId('der-bess-kpis')).toBeVisible()
    await expect(page.getByTestId('der-bess-grid')).toBeVisible()

    guards.assertClean()
    guards.detach()
  })

  test('EV dashboard renders piles + sessions surface', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/der/ev')

    await expect(page.getByTestId('der-ev-page')).toBeVisible()
    await expect(page.getByTestId('der-ev-kpis')).toBeVisible()
    await expect(page.getByTestId('der-ev-grid')).toBeVisible()

    guards.assertClean()
    guards.detach()
  })

  test('Distribution room dashboard renders sensor cards', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/distribution')

    await expect(page.getByTestId('distribution-page')).toBeVisible()
    await expect(page.getByTestId('distribution-rooms')).toBeVisible()

    guards.assertClean()
    guards.detach()
  })
})
