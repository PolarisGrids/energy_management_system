// @ts-check
import { test, expect } from '@playwright/test'
import { login, attachConsoleGuards } from './_helpers'

/**
 * Verify the post-7de9395 deploy: rich sim visuals, GIS hierarchy,
 * AppBuilder widget config drawer + live render.
 *
 * Targets the dev URL via E2E_BASE_URL=https://vidyut360.dev.polagram.in.
 */

test.describe('New features verification (post-7de9395)', () => {

  test('Simulations: rich visuals load after start (Solar)', async ({ page, request, baseURL }) => {
    // Drive the lifecycle via the API to avoid sidebar timing flakiness.
    const loginResp = await request.post(`${baseURL}/api/v1/auth/login`, {
      data: { username: 'operator', password: 'Oper@2026' },
    })
    const { access_token } = await loginResp.json()
    const auth = { Authorization: `Bearer ${access_token}` }
    const sims = await (await request.get(`${baseURL}/api/v1/simulation/`, { headers: auth })).json()
    const solar = sims.find((s) => s.scenario_type === 'solar_overvoltage')
    // Reset → start → step once so current_step = 1 (which gates the viz).
    await request.post(`${baseURL}/api/v1/simulation/${solar.id}/reset`, { headers: auth })
    await request.post(`${baseURL}/api/v1/simulation/${solar.id}/start`, { headers: auth, data: {} })
    await request.post(`${baseURL}/api/v1/simulation/${solar.id}/next-step`, { headers: auth })

    // Now load the page and click into Solar — the viz should render.
    await login(page)
    await page.goto('/simulation')
    await page.getByText(/Solar Overvoltage/i).first().click()
    await expect(
      page.getByText(/LV Feeder Droop Curtailment/i)
    ).toBeVisible({ timeout: 12000 })
  })

  test('GIS: 8-level hierarchy drill-down panel renders', async ({ page }) => {
    await login(page)
    await page.goto('/gis')
    // HierarchyPanel always renders "CHILDREN" or "STATS" section labels at
    // the root zone, plus the breadcrumb "Republic of South Africa".
    await expect(
      page.getByText(/Republic of South Africa/i).first()
    ).toBeVisible({ timeout: 15000 })
    // Drill-down children present
    await expect(page.getByText(/Gauteng Circle/i)).toBeVisible()
    await expect(page.getByText(/Coastal Circle/i)).toBeVisible()
  })

  test('AppBuilder: widget-sources catalog API responds', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/app-builder')
    // Catch the widget-sources fetch
    const sourcesResp = await page.waitForResponse(
      (resp) => resp.url().includes('/widget-sources') && resp.status() === 200,
      { timeout: 12000 }
    ).catch(() => null)
    expect(sourcesResp, 'widget-sources catalog should be 200').not.toBeNull()
    guards.assertClean()
    guards.detach()
  })

  test('Backend: hierarchy endpoint returns root zone with stats', async ({ request, baseURL }) => {
    // Login via API to grab the bearer token
    const loginResp = await request.post(`${baseURL}/api/v1/auth/login`, {
      data: { username: 'operator', password: 'Oper@2026' },
    })
    expect(loginResp.ok()).toBeTruthy()
    const { access_token } = await loginResp.json()

    const treeResp = await request.get(`${baseURL}/api/v1/gis/hierarchy/tree`, {
      headers: { Authorization: `Bearer ${access_token}` },
    })
    expect(treeResp.ok()).toBeTruthy()
    const tree = await treeResp.json()
    expect(tree.node?.level).toBe('zone')
    expect(Array.isArray(tree.children)).toBeTruthy()
    expect(tree.children.length).toBeGreaterThan(0)
    expect(tree.stats).toBeDefined()
    expect(tree.commands).toBeDefined()
  })

  test('Backend: /gis/layers/{layer} returns FeatureCollection (lat/lon fallback)', async ({ request, baseURL }) => {
    const loginResp = await request.post(`${baseURL}/api/v1/auth/login`, {
      data: { username: 'operator', password: 'Oper@2026' },
    })
    const { access_token } = await loginResp.json()
    const auth = { Authorization: `Bearer ${access_token}` }
    for (const layer of ['feeders', 'transformers', 'meters', 'der', 'alarms']) {
      const r = await request.get(`${baseURL}/api/v1/gis/layers/${layer}?max_features=200`, { headers: auth })
      expect(r.ok(), `${layer} should be 200`).toBeTruthy()
      const fc = await r.json()
      expect(fc.type, `${layer} should be a FeatureCollection`).toBe('FeatureCollection')
      expect(Array.isArray(fc.features), `${layer} features array`).toBeTruthy()
    }
  })

  test('Backend: simulation /simulation has rich solar/ev/microgrid network_state', async ({ request, baseURL }) => {
    const loginResp = await request.post(`${baseURL}/api/v1/auth/login`, {
      data: { username: 'operator', password: 'Oper@2026' },
    })
    const { access_token } = await loginResp.json()
    const sims = await request.get(`${baseURL}/api/v1/simulation`, {
      headers: { Authorization: `Bearer ${access_token}` },
    })
    expect(sims.ok()).toBeTruthy()
    const list = await sims.json()
    const solar = list.find((s) => s.scenario_type === 'solar_overvoltage')
    expect(solar?.parameters?.topology?.inverters?.length).toBeGreaterThan(0)
    const ev = list.find((s) => s.scenario_type === 'ev_fast_charging')
    expect(ev?.parameters?.bays?.length).toBe(4)
    const mg = list.find((s) => s.scenario_type === 'peaking_microgrid')
    expect(mg?.parameters?.assets?.length).toBe(4)
  })
})
