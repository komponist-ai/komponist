import assert from 'node:assert/strict'
import test from 'node:test'

import { createKomponistClient } from '../dist/index.js'

test('context.search sends scoped bearer request and repeated type filters', async () => {
  let request
  const client = createKomponistClient({
    url: 'http://localhost:8000/',
    apiKey: 'komponist_sk_test',
    fetch: async (url, options) => {
      request = { url: String(url), options }
      return new Response(JSON.stringify({ items: [], total: 0, query: 'auth' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    },
  })

  const result = await client.context.search(' auth ', {
    types: ['Decision', 'Constraint'],
    limit: 4,
  })

  assert.equal(result.error, null)
  assert.equal(result.data?.query, 'auth')
  assert.match(request.url, /^http:\/\/localhost:8000\/v1\/context\?/)
  const url = new URL(request.url)
  assert.deepEqual(url.searchParams.getAll('types'), ['Decision', 'Constraint'])
  assert.equal(url.searchParams.get('limit'), '4')
  assert.equal(request.options.headers.Authorization, 'Bearer komponist_sk_test')
})

test('returns Supabase-style data/error results for API failures', async () => {
  const client = createKomponistClient({
    url: 'http://localhost:8000',
    apiKey: 'revoked',
    fetch: async () => new Response(JSON.stringify({ detail: 'Valid Bearer API key required' }), {
      status: 401,
      headers: { 'content-type': 'application/json' },
    }),
  })

  const result = await client.brain.info()
  assert.equal(result.data, null)
  assert.deepEqual(result.error, {
    message: 'Valid Bearer API key required',
    status: 401,
  })
})

test('decisions.list encodes project scope and validates limits', async () => {
  let requestedUrl = ''
  const client = createKomponistClient({
    url: 'http://localhost:8000',
    apiKey: 'test',
    fetch: async (url) => {
      requestedUrl = String(url)
      return new Response(JSON.stringify({ decisions: [], total: 0 }))
    },
  })

  await client.decisions.list({ projectId: 'pilot project', limit: 5 })
  const url = new URL(requestedUrl)
  assert.equal(url.searchParams.get('project_id'), 'pilot project')
  assert.equal(url.searchParams.get('limit'), '5')
  await assert.rejects(
    client.context.search('query', { limit: 21 }),
    /between 1 and 20/,
  )
})
