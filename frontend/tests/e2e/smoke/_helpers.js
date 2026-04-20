// @ts-check
import { expect } from '@playwright/test'

/**
 * Demo credentials (seeded by `backend/scripts/seed_data.py`). Override via env
 * if a different deploy uses different fixtures.
 */
export const DEMO_USER = process.env.E2E_USER || 'operator'
export const DEMO_PASS = process.env.E2E_PASS || 'Oper@2026'

/** Routes registered in `src/App.jsx` — keep in sync when adding new ones. */
export const REGISTERED_ROUTES = [
  { path: '/',             label: 'Dashboard',         expect: 'Dashboard' },
  { path: '/gis',          label: 'GIS Map',           expect: 'GIS' },
  { path: '/alarms',       label: 'Alarm Console',     expect: 'Alarm' },
  { path: '/der',          label: 'DER Management',    expect: 'DER' },
  { path: '/energy',       label: 'Energy Monitoring', expect: 'Energy' },
  { path: '/hes',          label: 'HES Mirror',        expect: 'HES' },
  { path: '/mdms',         label: 'MDMS Mirror',       expect: 'MDMS' },
  { path: '/simulation',   label: 'Simulation',        expect: 'Simulation' },
  { path: '/reports',      label: 'Reports',           expect: 'Report' },
  { path: '/av-control',   label: 'A/V Control',       expect: 'Control' },
  { path: '/app-builder',  label: 'App Builder',       expect: 'App' },
  { path: '/showcase',     label: 'SMOC Showcase',     expect: 'Showcase' },
  { path: '/sensors',      label: 'Sensor Monitoring', expect: 'Sensor' },
  { path: '/audit',        label: 'Audit Log',         expect: 'Audit' },
  { path: '/ntl',          label: 'NTL Detection',     expect: 'NTL' },
]

/**
 * Perform the login flow via the `/login` form. Uses the demo credentials
 * unless overridden by env vars. Returns after the first authenticated
 * route has rendered.
 */
export async function login(page, { user = DEMO_USER, pass = DEMO_PASS } = {}) {
  await page.goto('/login')
  await page.getByPlaceholder('e.g. operator').fill(user)
  await page.getByPlaceholder('Password').fill(pass)
  await page.getByRole('button', { name: /sign in/i }).click()
  // After login we should end up at `/` (Dashboard). Wait for the
  // sidebar/topbar shell to render so subsequent navigations are stable.
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 10_000 })
}

/**
 * Set up console + network listeners that fail the test when the
 * navigation encounters a 404 or a red console error.
 *
 * Returns a cleanup function; callers should call it after assertions.
 */
export function attachConsoleGuards(page) {
  /** @type {string[]} */
  const consoleErrors = []
  /** @type {string[]} */
  const bad404s = []

  const onConsole = (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      // Filter out noise that is unrelated to route integrity.
      if (text.includes('favicon.ico')) return
      if (text.includes('ResizeObserver loop')) return
      // Upstream 401s from the SSOT proxy are expected when a specific MDMS
      // endpoint requires auth or isn't exposed. The frontend already treats
      // these as soft failures (see commit dd11b79 "don't logout on upstream
      // proxy 401s") so they must not fail the test either.
      if (/Failed to load resource.*status of 401/.test(text) && /\/api\/v1\/(mdms|hes)\//.test(text)) return
      consoleErrors.push(text)
    }
  }
  const onResponse = (resp) => {
    if (resp.status() === 404) {
      const url = resp.url()
      // Static-asset 404s (unrelated to the route under test) are ignored
      // — we only care about the main document + API calls.
      if (url.endsWith('.svg') || url.endsWith('.png') || url.endsWith('.ico')) return
      // Upstream MDMS / HES 404s are similarly expected when the requested
      // report path isn't yet exposed on the upstream. The UI falls through
      // to the empty-state banner, which is the intended product behaviour.
      if (/\/api\/v1\/(mdms|hes)\//.test(url)) return
      bad404s.push(`${resp.status()} ${url}`)
    }
  }

  page.on('console', onConsole)
  page.on('response', onResponse)

  return {
    consoleErrors,
    bad404s,
    detach() {
      page.off('console', onConsole)
      page.off('response', onResponse)
    },
    /** Throw if anything bad was captured. */
    assertClean() {
      expect(bad404s, `404 responses on route: ${bad404s.join(', ')}`).toEqual([])
      expect(
        consoleErrors,
        `red console errors on route: ${consoleErrors.join('\n---\n')}`,
      ).toEqual([])
    },
  }
}
