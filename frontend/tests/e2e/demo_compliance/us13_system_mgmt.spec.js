// @ts-check
import { test } from '@playwright/test'

/**
 * US-13 — System Management (supplier + product registry, demo #12).
 *
 * Frontend route `/system-mgmt` is not yet registered in App.jsx
 * (spec 018 W4.T15/T16 pending). The Playwright coverage is fixme'd
 * until the page lands; backend contract is asserted in
 * test_us13_system_mgmt.py with an xfail module-level guard.
 */
test.describe('US-13: System Management', () => {
  test.fixme(
    'supplier registry page renders metrics',
    async () => {
      // Fixme: route /system-mgmt not registered (W4.T15). Once the page
      // ships, assert:
      //   - table has rows with name, meter_count, failure_rate %, MTBF
      //   - clicking a supplier opens detail drawer with CSV-import button
    },
  )

  test.fixme(
    'csv import of 50 meters completes',
    async () => {
      // Fixme: upload flow pending W4.T16 (CSV import handler + FE form).
    },
  )
})
