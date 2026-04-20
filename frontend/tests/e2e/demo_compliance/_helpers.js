// @ts-check
/**
 * Shared helpers for spec-018 demo-compliance Playwright specs.
 *
 * Re-exports ``login`` / ``attachConsoleGuards`` from the smoke suite so
 * demo-compliance specs don't diverge from the authentication / guard
 * conventions used elsewhere. Also exposes a ``stubJson`` helper that
 * intercepts a backend path and returns a canned JSON body — used by the
 * US-1 through US-8 specs to drive deterministic state without standing up
 * HES / MDMS.
 */
import { login, attachConsoleGuards } from '../smoke/_helpers.js'

export { login, attachConsoleGuards }

/**
 * Register a route handler that responds with canned JSON.
 *
 *   await stubJson(page, '**\/api/v1/mdms/api/v1/vee/summary*', { items: [] })
 */
export async function stubJson(page, pattern, body, { status = 200, headers = {} } = {}) {
  await page.route(pattern, async (route) => {
    await route.fulfill({
      status,
      contentType: 'application/json',
      headers,
      body: JSON.stringify(body),
    })
  })
}

/**
 * Register a route that responds with the given HTTP status and no body.
 * Used by the MDMS-unavailable banner assertion.
 */
export async function stubStatus(page, pattern, status) {
  await page.route(pattern, async (route) => {
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'UPSTREAM_MDMS_UNAVAILABLE', message: 'test' } }),
    })
  })
}
