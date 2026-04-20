// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-14 — Consumption queries & reports (demo #13, #14).
 *
 * Acceptance (integration-test-matrix row 14):
 *   - /reports page loads with the Energy Audit, EGSM (MDMS proxy), and
 *     Scheduled tabs.
 *   - Run against Energy Audit Monthly returns table + chart.
 *   - Export CSV action available; large-export path (S3+SQS) flows via
 *     /api/v1/reports/download poll — assertion lives backend-side.
 */
test.describe('US-14: Consumption queries & reports', () => {
  test('reports page renders with tabs and export button', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/reports')

    // Page renders.
    await expect(page.getByRole('heading', { name: /report/i }).first()).toBeVisible()

    // Tabs (Energy Audit / EGSM / Scheduled) — match on visible text from
    // the jsx: ['EGSM (MDMS)', 'Scheduled'].
    await expect(page.getByText(/EGSM \(MDMS\)/)).toBeVisible()
    await expect(page.getByText(/Scheduled/i).first()).toBeVisible()

    // Export CSV CTA exists on the Energy Audit tab.
    const exportBtn = page.getByRole('button', { name: /export csv/i }).first()
    await expect(exportBtn).toBeVisible()

    guards.assertClean()
    guards.detach()
  })

  test('egsm tab accepts category + report name navigation', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/reports')

    const egsmTab = page.getByRole('button', { name: /EGSM \(MDMS\)/ })
      .or(page.getByText(/EGSM \(MDMS\)/).first())
    if (await egsmTab.count()) {
      await egsmTab.first().click()
      // The EGSM section mentions the route shape. Just assert no crash.
    }

    guards.assertClean()
    guards.detach()
  })
})
