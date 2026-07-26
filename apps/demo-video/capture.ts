import { chromium, type APIResponse, type Page } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const captureDirectory = resolve(here, 'public/captures')
const baseUrl = (process.env.KOMPONIST_DEMO_WEB_URL || 'http://localhost:3000').replace(/\/$/, '')
const apiUrl = (process.env.KOMPONIST_DEMO_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const isLocal = /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(baseUrl)
const email = process.env.KOMPONIST_DEMO_EMAIL || (isLocal ? 'yc-demo@komponist.local' : '')
const password = process.env.KOMPONIST_DEMO_PASSWORD || (isLocal ? 'komponist-demo-password' : '')
const browserChannel = process.env.KOMPONIST_DEMO_BROWSER_CHANNEL as
  | 'chrome'
  | 'chrome-beta'
  | 'chrome-dev'
  | 'chrome-canary'
  | 'msedge'
  | 'msedge-beta'
  | 'msedge-dev'
  | 'msedge-canary'
  | undefined

if (!email || !password) {
  throw new Error('Set KOMPONIST_DEMO_EMAIL and KOMPONIST_DEMO_PASSWORD for a hosted recording.')
}

async function requestJson(response: APIResponse): Promise<any> {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok()) {
    throw new Error(`${response.status()} ${response.statusText()}: ${JSON.stringify(payload)}`)
  }
  return payload
}

async function ready(page: Page, heading: string) {
  await page.getByRole('heading', { name: heading, exact: true }).waitFor({ state: 'visible' })
  await page.evaluate(() => document.fonts.ready)
}

async function capture(page: Page, name: string) {
  await page.screenshot({
    path: resolve(captureDirectory, `${name}.png`),
    animations: 'disabled',
    scale: 'css',
    style: [
      '[aria-label="Loading GitHub stars"], [aria-label$="GitHub stars"] { display: none !important; }',
      '[data-nextjs-toast], nextjs-portal { display: none !important; }',
      '* { caret-color: transparent !important; }',
    ].join('\n'),
  })
}

await mkdir(captureDirectory, { recursive: true })
const browser = await chromium.launch({
  channel: browserChannel,
  headless: process.env.KOMPONIST_DEMO_HEADFUL !== 'true',
})
const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  colorScheme: 'light',
  reducedMotion: 'reduce',
  locale: 'en-US',
  timezoneId: 'Europe/Berlin',
})
const page = await context.newPage()

try {
  let registration = await context.request.post(`${apiUrl}/auth/register`, {
    data: {
      name: 'Komponist Demo',
      email,
      password,
      organization_name: 'CampusKollektiv',
    },
  })
  if (registration.status() === 409) {
    registration = await context.request.post(`${apiUrl}/auth/login/email`, {
      data: { email, password },
    })
  }
  await requestJson(registration)

  const session = await requestJson(await context.request.get(`${apiUrl}/auth/session`))
  const orgId = session.user?.org_id as string | undefined
  if (!orgId) throw new Error('The demo session did not return an organization.')

  const showcase = await requestJson(await context.request.post(
    `${apiUrl}/demo/workspace?org_id=${encodeURIComponent(orgId)}`,
  ))

  await page.goto(baseUrl)
  await page.evaluate((activeOrgId) => {
    localStorage.setItem('komponist_active_org_id', activeOrgId)
  }, orgId)

  await page.goto(`${baseUrl}/sources`)
  await ready(page, 'Connected Sources')
  const sourceToggle = page.getByRole('button', { name: /Show documents from CampusKollektiv demo documents/i })
  if (await sourceToggle.count() === 1 && await sourceToggle.getAttribute('aria-expanded') !== 'true') {
    await sourceToggle.click()
  }
  await capture(page, 'sources')

  await page.goto(`${baseUrl}/studio`)
  await ready(page, 'Ask Komponist')
  const conversation = page.locator('button').filter({ hasText: showcase.conversation }).first()
  await conversation.click()
  await page.locator('[data-chat-role="assistant"]').waitFor({ state: 'visible' })
  await capture(page, 'chat')

  await page.goto(`${baseUrl}/canvas`)
  await ready(page, 'Canvas')
  const canvas = page.locator('button').filter({ hasText: 'Campus Forum Command Center' }).first()
  await canvas.click()
  await page.getByRole('heading', { name: 'Campus Forum Command Center', exact: true }).waitFor({ state: 'visible' })
  await capture(page, 'canvas')

  await page.goto(`${baseUrl}/workrooms`)
  await ready(page, 'Workrooms')
  const room = page.locator('button').filter({ hasText: 'Campus Forum readiness room' }).first()
  await room.click()
  await page.getByRole('heading', { name: 'Campus Forum readiness room', exact: true }).waitFor({ state: 'visible' })
  await capture(page, 'workrooms')

  await page.goto(`${baseUrl}/create?artifact=${encodeURIComponent(showcase.artifact_id)}`)
  await ready(page, 'Compose')
  await page.getByRole('heading', { name: 'Campus Forum Launch Decision Brief', exact: true }).waitFor({ state: 'visible' })
  await capture(page, 'compose')

  await writeFile(
    resolve(captureDirectory, 'manifest.json'),
    JSON.stringify({
      captured_at: new Date().toISOString(),
      base_url: baseUrl,
      organization: 'CampusKollektiv',
      org_id: orgId,
      showcase,
    }, null, 2),
  )
  console.log(`Captured five YC demo scenes in ${captureDirectory}`)
} finally {
  await browser.close()
}
