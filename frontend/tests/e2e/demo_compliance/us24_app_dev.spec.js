// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from '../smoke/_helpers'

/**
 * US-24 App Development (Demo #27).
 *
 * Author a rule → preview → publish (role-gated) → rule evaluates in prod
 * → version history shown → old version keeps running until Promote.
 *
 * We smoke the /app-builder surface + drive the backend directly for the
 * end-to-end author → preview → version-history loop.
 */
test.describe('US-24: App development', () => {
  test('AppBuilder rule preview fires and action is simulated', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    await page.goto('/app-builder')
    await expect(page.getByText(/Rule|App|Algorithm/i).first()).toBeVisible()

    const slug = `rule-e2e-${Date.now()}`
    const created = await page.request.post('/api/v1/app-rules', {
      data: {
        slug,
        name: 'E2E rule',
        condition: 'x > 10',
        action: { type: 'log', message: 'fired' },
      },
    })
    expect(created.ok(), `create rule: ${created.status()} ${await created.text()}`).toBeTruthy()

    const preview = await page.request.post(`/api/v1/app-rules/${slug}/preview`, {
      data: { input: { x: 42 } },
    })
    expect(preview.ok()).toBeTruthy()
    const body = await preview.json()
    expect(body.fired).toBeTruthy()

    guards.assertClean()
    guards.detach()
  })

  test('App version history is visible via /apps/{slug}/versions', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)

    const slug = `app-e2e-${Date.now()}`
    await page.request.post('/api/v1/apps', {
      data: { slug, name: 'v1', spec: { widget_type: 'kpi' } },
    })
    await page.request.put(`/api/v1/apps/${slug}`, {
      data: { name: 'v2', spec: { widget_type: 'kpi', config: { threshold: 90 } } },
    })
    const versions = await page.request.get(`/api/v1/apps/${slug}/versions`)
    expect(versions.ok()).toBeTruthy()
    const list = await versions.json()
    const items = Array.isArray(list) ? list : list.versions || []
    expect(items.length).toBeGreaterThanOrEqual(2)

    guards.assertClean()
    guards.detach()
  })

  test.fixme(
    'Old version keeps running until Promote is clicked',
    // Hot-reload runtime swap on publish — xfailed in backend test for
    // the same reason; deferred to spec 018 Wave-5 T17.
    async ({ page }) => {},
  )
})
