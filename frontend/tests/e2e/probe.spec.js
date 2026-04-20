import { test } from '@playwright/test'
import { login } from './smoke/_helpers'
const probe = (route) => test(`probe ${route}`, async ({ page }) => {
  const errs = []
  page.on('pageerror', e => errs.push(`PAGEERROR: ${e.message}\n${e.stack?.split('\n').slice(0,4).join('\n') || ''}`))
  page.on('console', m => { if (m.type() === 'error') errs.push(`CONSOLE: ${m.text()}`) })
  page.on('response', r => { if (r.status() >= 400) errs.push(`HTTP ${r.status()}: ${r.url()}`) })
  await login(page)
  await page.goto(route)
  await page.waitForTimeout(7000)
  console.log(`--- ${route} ERRORS ---`)
  errs.slice(0, 50).forEach(e => console.log(e))
  console.log(`--- END ${route} ---`)
})
probe('/gis')
