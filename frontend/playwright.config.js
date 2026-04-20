// @ts-check
import { defineConfig, devices } from '@playwright/test'

/**
 * Polaris SMOC EMS — Playwright config.
 *
 * Smoke suite: `npm run test:e2e:smoke` drives Chromium against a
 * locally-running preview server (or against BASE_URL in CI). Each spec
 * performs a scripted login then hits a single registered route,
 * asserting no 404 and no red console errors.
 */
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:4173'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // CI spins up the preview server externally; locally we assume the
  // caller has `npm run preview` running. Tests that need a backend
  // should be run with backend reachable on BASE_URL's API path.
})
