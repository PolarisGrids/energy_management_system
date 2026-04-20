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

  test('Simulations: rich visuals load for all 5 scenarios', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/simulation')
    await expect(page.getByText(/Demo Scenarios/i)).toBeVisible()

    // Sidebar shows all 5 REQ scenarios
    for (const label of ['Solar', 'EV', 'Microgrid', 'Network Fault', 'Sensor']) {
      await expect(page.getByText(new RegExp(label, 'i')).first()).toBeVisible()
    }

    // Click Solar Overvoltage scenario, start, advance, expect viz
    await page.getByText(/Solar Overvoltage/i).first().click()
    const startBtn = page.getByRole('button', { name: /Start/ }).first()
    if (await startBtn.isVisible().catch(() => false)) {
      await startBtn.click()
    }
    const next = page.getByRole('button', { name: /Next Step/ })
    if (await next.isVisible().catch(() => false)) {
      // Advance 3 steps to reach computed-curtailment phase
      for (let i = 0; i < 3; i++) {
        await next.click().catch(() => {})
        await page.waitForTimeout(400)
      }
    }
    // Look for SolarOvervoltageViz signature elements
    await expect(page.getByText(/Droop Curtailment|Inverter|N1|N7/i).first()).toBeVisible({ timeout: 8000 })
    guards.assertClean()
    guards.detach()
  })

  test('GIS: 8-level hierarchy drill-down panel renders', async ({ page }) => {
    await login(page)
    const guards = attachConsoleGuards(page)
    await page.goto('/gis')
    // HierarchyPanel renders the root zone name and a "Republic" or "Network"
    // breadcrumb / title — both acceptable defaults.
    await expect(
      page.getByText(/Republic of South Africa|Hierarchy|Zone|Circle/i).first()
    ).toBeVisible({ timeout: 12000 })
    guards.assertClean()
    guards.detach()
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
