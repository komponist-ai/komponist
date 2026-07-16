# `@komponist/sdk`

Typed JavaScript/TypeScript access to reviewed Komponist context. Create an
organization API key in **Studio → Settings → API & MCP**, then use it only in
trusted server-side code.

```ts
import { createKomponistClient } from '@komponist/sdk'

const komponist = createKomponistClient({
  url: process.env.KOMPONIST_URL ?? 'http://localhost:8000',
  apiKey: process.env.KOMPONIST_API_KEY!,
})

const { data, error } = await komponist.context.search(
  'What did we decide about authentication?',
  { types: ['Decision', 'Constraint'], limit: 8 },
)

if (error) throw new Error(error.message)
for (const fact of data.items) {
  console.log(fact.statement, fact.evidence)
}
```

The client also exposes `komponist.brain.info()` and
`komponist.decisions.list({ projectId })`. Results use a predictable
`{ data, error }` contract. Context search and decision listing return only
confirmed facts with organization-scoped evidence.

Do not embed an organization API key in browser bundles or public mobile apps.
